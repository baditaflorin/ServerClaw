#!/usr/bin/env python3
"""Verify and dispatch Authentik password-recovery email without exposing secrets."""

from __future__ import annotations

import argparse
import json
import stat
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml


FLOW_INSTANCES_PATH = "/api/v3/flows/instances/"
BRANDS_PATH = "/api/v3/core/brands/"
IDENTIFICATION_STAGES_PATH = "/api/v3/stages/identification/"
EMAIL_STAGES_PATH = "/api/v3/stages/email/"
USERS_PATH = "/api/v3/core/users/"
DEFAULT_RECOVERY_FLOW_SLUG = "platform-operator-recovery"
DEFAULT_IDENTIFICATION_STAGE = "default-authentication-identification"
DEFAULT_EMAIL_STAGE = "platform-operator-recovery-email"


class RecoveryError(RuntimeError):
    """Raised when the safe Authentik recovery contract is not ready."""


class HTTPAuthentikAPI:
    """Small Authentik client that never includes response bodies in errors."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(self, method: str, path: str, *, data: bytes | None = None) -> tuple[int, dict[str, Any]]:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "serverclaw-authentik-recovery/1",
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
                if not body:
                    return response.status, {}
                payload = json.loads(body)
                if not isinstance(payload, dict):
                    raise RecoveryError(f"Authentik {method} {path} returned an invalid JSON object")
                return response.status, payload
        except urllib.error.HTTPError as exc:
            exc.read()
            raise RecoveryError(f"Authentik {method} {path} returned HTTP {exc.code}") from None
        except urllib.error.URLError as exc:
            raise RecoveryError(f"Authentik {method} {path} failed: {exc.reason}") from None

    def list_all(self, path: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        page = 1
        while True:
            query = urllib.parse.urlencode({"page": page, "page_size": 100})
            _, payload = self._request("GET", f"{path}?{query}")
            page_results = payload.get("results")
            if not isinstance(page_results, list):
                raise RecoveryError(f"Authentik GET {path} returned no result list")
            for item in page_results:
                if not isinstance(item, dict):
                    raise RecoveryError(f"Authentik GET {path} returned an invalid result")
                results.append(item)
            pagination = payload.get("pagination")
            if not isinstance(pagination, dict):
                raise RecoveryError(f"Authentik GET {path} returned no pagination object")
            next_page = pagination.get("next")
            if not next_page:
                return results
            if isinstance(next_page, bool) or not isinstance(next_page, int) or next_page <= page:
                raise RecoveryError(f"Authentik GET {path} returned invalid pagination")
            page = next_page

    def post_no_content(self, path: str, payload: dict[str, Any]) -> int:
        status, _ = self._request("POST", path, data=json.dumps(payload).encode("utf-8"))
        return status


def _read_secret(path: Path, label: str) -> str:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        raise RecoveryError(f"{label} file is missing") from None
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise RecoveryError(f"{label} file must be a regular file")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise RecoveryError(f"{label} file must not be group- or world-readable")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RecoveryError(f"{label} file is empty")
    return value


def _object_pk(value: Any, label: str) -> str:
    if isinstance(value, dict):
        value = value.get("pk") or value.get("uuid")
    if isinstance(value, bool) or value is None or not str(value).strip():
        raise RecoveryError(f"Authentik {label} has no usable primary key")
    return str(value)


def _relation_pk(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("pk") or value.get("uuid")
    if isinstance(value, bool) or value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _single(items: list[dict[str, Any]], *, label: str) -> dict[str, Any]:
    if len(items) != 1:
        raise RecoveryError(f"Expected exactly one {label}")
    return items[0]


def check_recovery_contract(
    api: HTTPAuthentikAPI,
    *,
    recovery_flow_slug: str = DEFAULT_RECOVERY_FLOW_SLUG,
    identification_stage_name: str = DEFAULT_IDENTIFICATION_STAGE,
    email_stage_name: str = DEFAULT_EMAIL_STAGE,
) -> dict[str, Any]:
    flows = api.list_all(FLOW_INSTANCES_PATH)
    recovery_flow = _single(
        [flow for flow in flows if flow.get("slug") == recovery_flow_slug],
        label="recovery flow",
    )
    if recovery_flow.get("designation") != "recovery":
        raise RecoveryError("The configured recovery flow does not use recovery designation")
    recovery_flow_pk = _object_pk(recovery_flow, "recovery flow")

    brands = api.list_all(BRANDS_PATH)
    active_brand = _single([brand for brand in brands if brand.get("default") is True], label="default brand")
    if _relation_pk(active_brand.get("flow_recovery")) != recovery_flow_pk:
        raise RecoveryError("The default brand is not bound to the recovery flow")

    identification_stages = api.list_all(IDENTIFICATION_STAGES_PATH)
    login_stage = _single(
        [stage for stage in identification_stages if stage.get("name") == identification_stage_name],
        label="default authentication identification stage",
    )
    if _relation_pk(login_stage.get("recovery_flow")) != recovery_flow_pk:
        raise RecoveryError("The login identification stage is not bound to the recovery flow")

    email_stages = api.list_all(EMAIL_STAGES_PATH)
    email_stage = _single(
        [stage for stage in email_stages if stage.get("name") == email_stage_name],
        label="recovery email stage",
    )
    if email_stage.get("use_global_settings") is not True:
        raise RecoveryError("The recovery email stage does not use global SMTP settings")

    return {
        "check": "authentik_recovery_flow",
        "result": "pass",
        "recovery_flow_present": True,
        "default_brand_bound": True,
        "login_recovery_link_bound": True,
        "global_smtp_enabled": True,
    }


def _operator_email(identity_file: Path) -> str:
    try:
        metadata = identity_file.lstat()
    except FileNotFoundError:
        raise RecoveryError("Operator identity file is missing") from None
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise RecoveryError("Operator identity file must be a regular file")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise RecoveryError("Operator identity file must not be group- or world-readable")
    payload = yaml.safe_load(identity_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RecoveryError("Operator identity file is invalid")
    email = payload.get("platform_operator_email")
    if not isinstance(email, str) or "@" not in email:
        raise RecoveryError("Operator identity file has no valid operator email")
    return email


def send_recovery_email(
    api: HTTPAuthentikAPI,
    *,
    identity_file: Path,
    recovery_flow_slug: str = DEFAULT_RECOVERY_FLOW_SLUG,
    identification_stage_name: str = DEFAULT_IDENTIFICATION_STAGE,
    email_stage_name: str = DEFAULT_EMAIL_STAGE,
) -> dict[str, Any]:
    check_recovery_contract(
        api,
        recovery_flow_slug=recovery_flow_slug,
        identification_stage_name=identification_stage_name,
        email_stage_name=email_stage_name,
    )
    operator_email = _operator_email(identity_file).casefold()
    users = api.list_all(USERS_PATH)
    operator = _single(
        [user for user in users if str(user.get("email", "")).casefold() == operator_email],
        label="active platform operator",
    )
    if operator.get("is_active") is not True:
        raise RecoveryError("The platform operator account is inactive")
    user_pk = _object_pk(operator, "platform operator")
    email_stages = api.list_all(EMAIL_STAGES_PATH)
    email_stage = _single(
        [stage for stage in email_stages if stage.get("name") == email_stage_name],
        label="recovery email stage",
    )
    email_stage_pk = _object_pk(email_stage, "recovery email stage")
    status = api.post_no_content(
        f"{USERS_PATH}{urllib.parse.quote(user_pk, safe='')}/recovery_email/",
        {"email_stage": email_stage_pk},
    )
    if status != 204:
        raise RecoveryError("Authentik did not accept the recovery-email request")
    return {
        "check": "authentik_recovery_email",
        "result": "accepted",
        "recipient": "platform_operator",
        "status": status,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify or send a governed Authentik recovery email.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def common(command: argparse.ArgumentParser) -> None:
        command.add_argument("--base-url", required=True)
        command.add_argument("--token-file", required=True, type=Path)
        command.add_argument("--recovery-flow-slug", default=DEFAULT_RECOVERY_FLOW_SLUG)
        command.add_argument("--identification-stage", default=DEFAULT_IDENTIFICATION_STAGE)
        command.add_argument("--email-stage", default=DEFAULT_EMAIL_STAGE)

    check_parser = subparsers.add_parser("check", help="Verify recovery flow, brand, login, and SMTP-stage bindings.")
    common(check_parser)
    send_parser = subparsers.add_parser("send-email", help="Request a recovery email for the configured operator.")
    common(send_parser)
    send_parser.add_argument("--identity-file", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        api = HTTPAuthentikAPI(args.base_url, _read_secret(args.token_file, "Authentik API token"))
        kwargs = {
            "recovery_flow_slug": args.recovery_flow_slug,
            "identification_stage_name": args.identification_stage,
            "email_stage_name": args.email_stage,
        }
        if args.command == "check":
            result = check_recovery_contract(api, **kwargs)
        else:
            result = send_recovery_email(api, identity_file=args.identity_file, **kwargs)
    except (RecoveryError, OSError, ValueError, yaml.YAMLError) as exc:
        print(json.dumps({"result": "fail", "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
