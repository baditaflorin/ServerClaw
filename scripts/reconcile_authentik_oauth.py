#!/usr/bin/env python3
"""Reconcile Authentik OAuth2 providers and applications without rotating secrets.

The manifest is intentionally non-secret. Client secrets are adopted into the
shared ignored ``.local`` overlay and are never included in command output.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import secrets
import stat
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Protocol

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
existing_platform = sys.modules.get("platform")
if existing_platform is not None and not hasattr(existing_platform, "__path__"):
    del sys.modules["platform"]

import yaml

from platform.repo import local_overlay_root, validate_repo_relative_path
from validation_toolkit import (
    require_bool,
    require_enum,
    require_http_url,
    require_identifier,
    require_list,
    require_mapping,
    require_str,
    require_unique_string_list,
    resolve_jinja2_vars,
)


DEFAULT_MANIFEST = REPO_ROOT / "config" / "authentik" / "oauth-clients.yaml"
PROVIDERS_PATH = "/api/v3/providers/oauth2/"
APPLICATIONS_PATH = "/api/v3/core/applications/"
FLOWS_PATH = "/api/v3/flows/instances/"
SCOPE_MAPPINGS_PATH = "/api/v3/propertymappings/provider/scope/"
CERTIFICATE_KEYS_PATH = "/api/v3/crypto/certificatekeypairs/"
DEFAULT_SIGNING_KEY_NAME = "authentik Self-signed Certificate"
MANAGED_PROVIDER_FIELDS = (
    "name",
    "authorization_flow",
    "invalidation_flow",
    "property_mappings",
    "client_type",
    "grant_types",
    "client_id",
    "signing_key",
    "include_claims_in_id_token",
    "redirect_uris",
    "sub_mode",
    "issuer_mode",
)
MANAGED_APPLICATION_FIELDS = (
    "name",
    "slug",
    "provider",
    "meta_launch_url",
    "policy_engine_mode",
)
ORDER_INSENSITIVE_FIELDS = {"property_mappings", "grant_types", "redirect_uris"}


class ReconcileError(RuntimeError):
    """Raised when safe reconciliation cannot continue."""


class AuthentikAPI(Protocol):
    def list_all(self, path: str) -> list[dict[str, Any]]: ...

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    def patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class HTTPAuthentikAPI:
    """Minimal Authentik API client whose errors never echo response bodies."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "serverclaw-authentik-reconciler/1",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                return {} if not body else require_mapping(json.loads(body), f"{method} {path} response")
        except urllib.error.HTTPError as exc:
            exc.read()
            raise ReconcileError(f"Authentik {method} {path} returned HTTP {exc.code}") from None
        except urllib.error.URLError as exc:
            raise ReconcileError(f"Authentik {method} {path} failed: {exc.reason}") from None

    def list_all(self, path: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        page = 1
        while True:
            query = urllib.parse.urlencode({"page": page, "page_size": 100})
            payload = self._request("GET", f"{path}?{query}")
            page_results = require_list(payload.get("results"), f"GET {path}.results")
            for index, item in enumerate(page_results):
                results.append(require_mapping(item, f"GET {path}.results[{index}]"))
            pagination = require_mapping(payload.get("pagination"), f"GET {path}.pagination")
            next_page = pagination.get("next")
            if not next_page:
                return results
            if isinstance(next_page, bool) or not isinstance(next_page, int) or next_page <= page:
                raise ReconcileError(f"Authentik pagination for {path} returned an invalid next page")
            page = next_page

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, payload)

    def patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", path, payload)


def _validate_secret_file(value: Any, path: str) -> str:
    normalized = validate_repo_relative_path(require_str(value, path), label=path)
    if normalized.startswith(".local/"):
        raise ValueError(f"{path} must be relative to the shared .local root")
    return normalized


def _validate_client(raw: Any, index: int) -> dict[str, Any]:
    path = f"clients[{index}]"
    client = require_mapping(raw, path)
    application = require_mapping(client.get("application"), f"{path}.application")
    provider = require_mapping(client.get("provider"), f"{path}.provider")
    client_id = require_identifier(client.get("id"), f"{path}.id")
    enabled = require_bool(client.get("enabled", True), f"{path}.enabled")
    secret_file = _validate_secret_file(client.get("client_secret_file"), f"{path}.client_secret_file")
    app_slug = require_identifier(application.get("slug"), f"{path}.application.slug")
    app_name = require_str(application.get("name"), f"{path}.application.name")
    launch_url = require_http_url(application.get("launch_url"), f"{path}.application.launch_url").rstrip("/")
    provider_name = require_str(provider.get("name"), f"{path}.provider.name")
    oauth_client_id = require_str(provider.get("client_id"), f"{path}.provider.client_id")
    client_type = require_enum(
        provider.get("client_type"),
        f"{path}.provider.client_type",
        {"confidential", "public"},
    )
    grant_types = require_unique_string_list(provider.get("grant_types"), f"{path}.provider.grant_types", min_length=1)
    allowed_grants = {
        "authorization_code",
        "implicit",
        "hybrid",
        "refresh_token",
        "client_credentials",
        "password",
        "urn:ietf:params:oauth:grant-type:device_code",
    }
    if invalid_grants := sorted(set(grant_types) - allowed_grants):
        raise ValueError(f"{path}.provider.grant_types contains unsupported values: {', '.join(invalid_grants)}")
    scopes = require_unique_string_list(provider.get("scopes"), f"{path}.provider.scopes", min_length=1)
    if "openid" not in scopes:
        raise ValueError(f"{path}.provider.scopes must include openid")
    redirects = require_unique_string_list(
        provider.get("redirect_uris"),
        f"{path}.provider.redirect_uris",
        min_length=1,
    )
    for redirect_index, redirect in enumerate(redirects):
        require_http_url(redirect, f"{path}.provider.redirect_uris[{redirect_index}]")
    return {
        "id": client_id,
        "enabled": enabled,
        "client_secret_file": secret_file,
        "application": {
            "name": app_name,
            "slug": app_slug,
            "launch_url": launch_url,
        },
        "provider": {
            "name": provider_name,
            "client_id": oauth_client_id,
            "client_type": client_type,
            "grant_types": grant_types,
            "authorization_flow": require_identifier(
                provider.get("authorization_flow"),
                f"{path}.provider.authorization_flow",
            ),
            "invalidation_flow": require_identifier(
                provider.get("invalidation_flow"),
                f"{path}.provider.invalidation_flow",
            ),
            "scopes": scopes,
            "redirect_uris": redirects,
            "include_claims_in_id_token": require_bool(
                provider.get("include_claims_in_id_token"),
                f"{path}.provider.include_claims_in_id_token",
            ),
            "sub_mode": require_enum(
                provider.get("sub_mode"),
                f"{path}.provider.sub_mode",
                {"hashed_user_id", "user_id", "user_uuid", "user_username", "user_email", "user_upn"},
            ),
            "issuer_mode": require_enum(
                provider.get("issuer_mode"),
                f"{path}.provider.issuer_mode",
                {"global", "per_provider"},
            ),
        },
    }


def load_manifest(path: Path, *, variables: dict[str, str] | None = None) -> dict[str, Any]:
    rendered_variables = dict(variables or {})
    # The default stays useful for local validation while a deployment can pass
    # an explicitly overridden config prefix through the Ansible role.
    platform_domain = rendered_variables.get("platform_domain")
    if platform_domain and not rendered_variables.get("platform_config_prefix"):
        rendered_variables["platform_config_prefix"] = platform_domain.split(".", 1)[0]
    rendered = resolve_jinja2_vars(path.read_text(encoding="utf-8"), rendered_variables)
    payload = require_mapping(yaml.safe_load(rendered), str(path))
    if payload.get("version") != 1:
        raise ValueError(f"{path}.version must be 1")
    clients = [
        _validate_client(item, index) for index, item in enumerate(require_list(payload.get("clients"), "clients"))
    ]
    ids = [client["id"] for client in clients]
    slugs = [client["application"]["slug"] for client in clients]
    oauth_client_ids = [client["provider"]["client_id"] for client in clients]
    for label, values in (("id", ids), ("application slug", slugs), ("OAuth client_id", oauth_client_ids)):
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            raise ValueError(f"clients must use unique {label} values: {', '.join(duplicates)}")
    return {"version": 1, "clients": clients}


def _find_unique(items: list[dict[str, Any]], field: str, value: Any, label: str) -> dict[str, Any] | None:
    matches = [item for item in items if item.get(field) == value]
    if len(matches) > 1:
        raise ReconcileError(f"Multiple Authentik {label} objects match {field}={value!r}")
    return matches[0] if matches else None


def _normalize_redirects(value: Any) -> list[tuple[str, str, str]]:
    redirects = require_list(value, "redirect_uris")
    normalized: list[tuple[str, str, str]] = []
    for index, item in enumerate(redirects):
        redirect = require_mapping(item, f"redirect_uris[{index}]")
        normalized.append(
            (
                str(redirect.get("matching_mode", "")),
                str(redirect.get("url", "")),
                str(redirect.get("redirect_uri_type", "authorization")),
            )
        )
    return sorted(normalized)


def _values_equal(field: str, current: Any, desired: Any) -> bool:
    if field == "redirect_uris":
        return _normalize_redirects(current or []) == _normalize_redirects(desired or [])
    if field in ORDER_INSENSITIVE_FIELDS:
        return sorted(current or []) == sorted(desired or [])
    return current == desired


def _changed_fields(current: dict[str, Any], desired: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    return [field for field in fields if not _values_equal(field, current.get(field), desired.get(field))]


def _resolve_named_pk(items: list[dict[str, Any]], *, field: str, value: str, label: str) -> Any:
    item = _find_unique(items, field, value, label)
    if item is None or item.get("pk") is None:
        raise ReconcileError(f"Required Authentik {label} {value!r} does not exist")
    return item["pk"]


def _safe_secret_path(local_secret_root: Path, relative_path: str) -> Path:
    root = local_secret_root.resolve()
    destination = (root / relative_path).resolve()
    if destination != root and root not in destination.parents:
        raise ReconcileError("Client secret path escapes the shared .local root")
    return destination


def _write_secret_atomic(path: Path, secret: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    file_descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"{secret}\n")
        try:
            # Linking a fully written same-filesystem temporary file provides
            # exclusive final creation. Unlike os.replace(), it cannot silently
            # overwrite a credential created by a concurrent reconciler.
            os.link(temporary_name, path)
        except FileExistsError:
            existing = path.read_text(encoding="utf-8").strip()
            if not existing or not hmac.compare_digest(existing, secret):
                raise ReconcileError(f"Client secret file {path} appeared concurrently; refusing overwrite") from None
        path.chmod(0o600)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _reconcile_secret_file(
    path: Path,
    provider_secret: Any,
    *,
    apply: bool,
) -> list[str]:
    secret = provider_secret if isinstance(provider_secret, str) else ""
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if not existing:
            raise ReconcileError(f"Client secret file {path} is empty")
        if secret and not hmac.compare_digest(existing, secret):
            raise ReconcileError(f"Client secret file {path} does not match Authentik; refusing rotation")
        changes: list[str] = []
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            changes.append("client_secret_file_mode")
            if apply:
                path.chmod(0o600)
        return changes
    if not secret and apply:
        raise ReconcileError("Authentik did not return a client secret; refusing to create an unusable local artifact")
    if apply:
        _write_secret_atomic(path, secret)
    return ["client_secret_file"]


def _change(client_id: str, object_type: str, action: str, pk: Any, fields: list[str]) -> dict[str, Any]:
    return {
        "client": client_id,
        "object": object_type,
        "action": action,
        "pk": pk,
        "fields": sorted(fields),
    }


def reconcile_manifest(
    manifest: dict[str, Any],
    api: AuthentikAPI,
    *,
    apply: bool,
    local_secret_root: Path,
    selected_clients: set[str] | None = None,
) -> dict[str, Any]:
    providers = api.list_all(PROVIDERS_PATH)
    applications = api.list_all(APPLICATIONS_PATH)
    flows = api.list_all(FLOWS_PATH)
    scope_mappings = api.list_all(SCOPE_MAPPINGS_PATH)
    certificate_keys = api.list_all(CERTIFICATE_KEYS_PATH)
    changes: list[dict[str, Any]] = []
    plans: list[dict[str, Any]] = []

    configured_ids = {str(client["id"]) for client in manifest["clients"]}
    if selected_clients is not None and (unknown := sorted(selected_clients - configured_ids)):
        raise ReconcileError(f"Unknown manifest client(s): {', '.join(unknown)}")

    # Build and validate every selected client plan before changing either the
    # controller-local secret store or Authentik. This prevents a later secret,
    # ownership, or linkage conflict from leaving an earlier client half-applied.
    for client_index, client in enumerate(manifest["clients"]):
        client_id = str(client["id"])
        if not client["enabled"] or (selected_clients is not None and client_id not in selected_clients):
            continue
        app_config = client["application"]
        provider_config = client["provider"]
        signing_key_name = require_str(
            provider_config.get("signing_key_name", DEFAULT_SIGNING_KEY_NAME),
            f"clients[{client_index}].provider.signing_key_name",
        )
        application = _find_unique(applications, "slug", app_config["slug"], "application")
        provider = _find_unique(providers, "client_id", provider_config["client_id"], "OAuth provider")
        if provider is None and application is not None and application.get("provider") is not None:
            provider = _find_unique(providers, "pk", application["provider"], "OAuth provider")
            if provider is None:
                raise ReconcileError(
                    f"Application {app_config['slug']!r} references missing provider {application['provider']!r}"
                )
        if provider is None:
            provider = _find_unique(providers, "name", provider_config["name"], "OAuth provider")

        authorization_flow_pk = _resolve_named_pk(
            flows,
            field="slug",
            value=provider_config["authorization_flow"],
            label="authorization flow",
        )
        invalidation_flow_pk = _resolve_named_pk(
            flows,
            field="slug",
            value=provider_config["invalidation_flow"],
            label="invalidation flow",
        )
        scope_pks = [
            _resolve_named_pk(scope_mappings, field="scope_name", value=scope, label="scope mapping")
            for scope in provider_config["scopes"]
        ]
        signing_key_pk = _resolve_named_pk(
            certificate_keys,
            field="name",
            value=signing_key_name,
            label="certificate keypair",
        )
        provider_desired = {
            "name": provider_config["name"],
            "authorization_flow": authorization_flow_pk,
            "invalidation_flow": invalidation_flow_pk,
            "property_mappings": scope_pks,
            "client_type": provider_config["client_type"],
            "grant_types": provider_config["grant_types"],
            "client_id": provider_config["client_id"],
            "signing_key": signing_key_pk,
            "include_claims_in_id_token": provider_config["include_claims_in_id_token"],
            "redirect_uris": [
                {
                    "matching_mode": "strict",
                    "url": uri,
                    "redirect_uri_type": "authorization",
                }
                for uri in provider_config["redirect_uris"]
            ],
            "sub_mode": provider_config["sub_mode"],
            "issuer_mode": provider_config["issuer_mode"],
        }

        provider_action = "unchanged"
        provider_fields: list[str] = []
        if provider is None:
            provider_action = "create"
            provider_fields = list(MANAGED_PROVIDER_FIELDS)
        else:
            provider_fields = _changed_fields(provider, provider_desired, MANAGED_PROVIDER_FIELDS)
            if provider_fields:
                provider_action = "update"

        provider_pk = provider.get("pk") if provider is not None else None
        if provider is not None and provider_pk is None:
            raise ReconcileError(f"Authentik provider for {client_id!r} has no primary key")

        # A provider is an owned OAuth client boundary. Reusing one already
        # linked to another application would make a client-id/callback update
        # mutate that other application implicitly.
        if provider_pk is not None:
            linked_elsewhere = [
                item
                for item in applications
                if item.get("provider") == provider_pk and item.get("slug") != app_config["slug"]
            ]
            if linked_elsewhere:
                raise ReconcileError(
                    f"Authentik provider {provider_pk!r} is shared by another application; refusing mutation"
                )

        if application is not None and application.get("provider") not in {None, provider_pk}:
            raise ReconcileError(
                f"Application {app_config['slug']!r} is linked to a different managed provider; refusing relink"
            )

        secret_path = _safe_secret_path(local_secret_root, client["client_secret_file"])
        secret_changes = _reconcile_secret_file(
            secret_path,
            provider.get("client_secret") if provider is not None else "",
            apply=False,
        )

        application_desired = {
            "name": app_config["name"],
            "slug": app_config["slug"],
            "provider": provider_pk,
            "meta_launch_url": app_config["launch_url"],
            "policy_engine_mode": "any",
        }
        application_action = "unchanged"
        application_fields: list[str] = []
        if application is None:
            application_action = "create"
            application_fields = list(MANAGED_APPLICATION_FIELDS)
        else:
            application_fields = _changed_fields(application, application_desired, MANAGED_APPLICATION_FIELDS)
            if provider is None and "provider" not in application_fields:
                # The provider PK is unknown until create succeeds, but the
                # existing unlinked application will need that field patched.
                application_fields.append("provider")
            if application_fields:
                application_action = "update"

        if provider_action != "unchanged":
            changes.append(_change(client_id, "provider", provider_action, provider_pk, provider_fields))
        if secret_changes:
            changes.append(_change(client_id, "local_secret", "create_or_fix", None, secret_changes))
        if application_action != "unchanged":
            changes.append(
                _change(
                    client_id,
                    "application",
                    application_action,
                    application.get("pk") if application is not None else None,
                    application_fields,
                )
            )

        plans.append(
            {
                "client_id": client_id,
                "provider": provider,
                "provider_desired": provider_desired,
                "provider_action": provider_action,
                "provider_fields": provider_fields,
                "application": application,
                "application_desired": application_desired,
                "application_action": application_action,
                "application_fields": application_fields,
                "secret_path": secret_path,
            }
        )

    if apply:
        # Prepare or revalidate all local secrets before the first API write.
        # New providers receive a controller-generated secret so an API success
        # can never strand an unrecoverable server-generated value.
        for plan in plans:
            provider = plan["provider"]
            secret_path = plan["secret_path"]
            if provider is None:
                if secret_path.exists():
                    _reconcile_secret_file(secret_path, "", apply=True)
                    prepared_secret = secret_path.read_text(encoding="utf-8").strip()
                else:
                    prepared_secret = secrets.token_urlsafe(48)
                    _write_secret_atomic(secret_path, prepared_secret)
                if not prepared_secret:
                    raise ReconcileError(f"Client secret file {secret_path} is empty")
                plan["provider_create_secret"] = prepared_secret
            else:
                _reconcile_secret_file(secret_path, provider.get("client_secret"), apply=True)

    reconciled: list[dict[str, Any]] = []
    for plan in plans:
        provider = plan["provider"]
        provider_action = plan["provider_action"]
        if apply and provider_action == "create":
            provider_payload = {
                **plan["provider_desired"],
                "client_secret": plan["provider_create_secret"],
            }
            provider = api.post(PROVIDERS_PATH, provider_payload)
            providers.append(provider)
        elif apply and provider_action == "update":
            patch_payload = {field: plan["provider_desired"][field] for field in plan["provider_fields"]}
            updated = api.patch(f"{PROVIDERS_PATH}{provider['pk']}/", patch_payload)
            provider = {**provider, **updated}

        provider_pk = provider.get("pk") if provider is not None else None
        application = plan["application"]
        application_desired = {**plan["application_desired"], "provider": provider_pk}
        application_action = plan["application_action"]
        if apply and application_action == "create":
            if provider_pk is None:
                raise ReconcileError("Provider creation did not return a primary key")
            application = api.post(APPLICATIONS_PATH, application_desired)
            applications.append(application)
        elif apply and application_action == "update":
            patch_payload = {field: application_desired[field] for field in plan["application_fields"]}
            updated = api.patch(f"{APPLICATIONS_PATH}{application['slug']}/", patch_payload)
            application = {**application, **updated}
        elif application is None:
            application = {**application_desired, "pk": None}

        reconciled.append(
            {
                "client": plan["client_id"],
                "provider_pk": provider_pk,
                "application_pk": application.get("pk"),
                "provider_action": provider_action,
                "application_action": application_action,
            }
        )

    return {
        "status": "ok",
        "mode": "apply" if apply else "check",
        "changed": bool(changes),
        "change_count": len(changes),
        "changes": changes,
        "clients": reconciled,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--base-url", required=True, help="Authentik base URL, for example https://id.example.com")
    parser.add_argument(
        "--platform-domain",
        help="Explicit platform_domain used to render the manifest (recommended for named deployments)",
    )
    parser.add_argument(
        "--platform-config-prefix",
        help="Explicit platform config prefix used to render client IDs that must remain deployment-unique",
    )
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--client", action="append", dest="clients", help="Reconcile only this manifest client")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Report drift without mutation (default)")
    mode.add_argument("--apply", action="store_true", help="Apply drift and securely adopt client secrets")
    parser.add_argument(
        "--expect-no-change",
        action="store_true",
        help="Fail when read-only reconciliation reports drift",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.expect_no_change and args.apply:
        raise ReconcileError("--expect-no-change cannot be combined with --apply")
    token = args.token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise ReconcileError(f"Authentik token file {args.token_file} is empty")
    render_variables = None
    if args.platform_domain:
        render_variables = {"platform_domain": args.platform_domain}
        if args.platform_config_prefix:
            render_variables["platform_config_prefix"] = args.platform_config_prefix
    elif args.platform_config_prefix:
        raise ReconcileError("--platform-config-prefix requires --platform-domain")
    manifest = load_manifest(args.manifest, variables=render_variables)
    result = reconcile_manifest(
        manifest,
        HTTPAuthentikAPI(require_http_url(args.base_url, "--base-url"), token),
        apply=args.apply,
        local_secret_root=local_overlay_root(REPO_ROOT),
        selected_clients=set(args.clients) if args.clients else None,
    )
    print(json.dumps(result, sort_keys=True))
    if args.expect_no_change and result["changed"]:
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ReconcileError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
