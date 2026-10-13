#!/usr/bin/env python3
"""Idempotently reconcile repository-owned Authentik OAuth scope mappings."""

from __future__ import annotations

import argparse
import json
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Protocol

import yaml

from validation_toolkit import require_identifier, require_list, require_mapping, require_str


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "config" / "authentik" / "scope-mappings.yaml"
SCOPE_MAPPINGS_PATH = "/api/v3/propertymappings/provider/scope/"
MANAGED_MARKER = "managed-by: serverclaw"
MANAGED_FIELDS = ("name", "scope_name", "description", "expression")


class ReconcileError(RuntimeError):
    """Raised when safe scope mapping reconciliation cannot continue."""


class AuthentikAPI(Protocol):
    def list_all(self, path: str) -> list[dict[str, Any]]: ...

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    def patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class HTTPAuthentikAPI:
    """Minimal API client which never includes credentials or response bodies in errors."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self.token}"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
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
            results.extend(
                require_mapping(row, f"GET {path}.results[{index}]") for index, row in enumerate(page_results)
            )
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


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ReconcileError(f"Cannot read scope mapping manifest {path}: {exc}") from None
    manifest = require_mapping(payload, str(path))
    if manifest.get("version") != 1:
        raise ReconcileError(f"{path}.version must be 1")
    mappings: list[dict[str, str]] = []
    for index, raw in enumerate(require_list(manifest.get("mappings"), "mappings")):
        item = require_mapping(raw, f"mappings[{index}]")
        mapping = {
            "id": require_identifier(item.get("id"), f"mappings[{index}].id"),
            "name": require_str(item.get("name"), f"mappings[{index}].name"),
            "scope_name": require_identifier(item.get("scope_name"), f"mappings[{index}].scope_name"),
            "description": require_str(item.get("description"), f"mappings[{index}].description"),
            "expression": require_str(item.get("expression"), f"mappings[{index}].expression"),
        }
        if MANAGED_MARKER not in mapping["description"].casefold():
            raise ReconcileError(f"mappings[{index}].description must include the ownership marker")
        mappings.append(mapping)
    if not mappings:
        raise ReconcileError("mappings must not be empty")
    for field in ("id", "name", "scope_name"):
        values = [mapping[field] for mapping in mappings]
        if len(values) != len(set(values)):
            raise ReconcileError(f"mappings must use unique {field} values")
    return {"version": 1, "mappings": mappings}


def _find_unique(rows: list[dict[str, Any]], *, field: str, value: str) -> dict[str, Any] | None:
    matches = [row for row in rows if row.get(field) == value]
    if len(matches) > 1:
        raise ReconcileError(f"Multiple Authentik scope mappings match {field}={value!r}")
    return matches[0] if matches else None


def _managed_value_matches(field: str, current: Any, desired: str) -> bool:
    # Authentik stores expression source without the manifest block scalar's
    # final newline. That transport normalization is semantically inert and
    # must not produce perpetual reconciliation drift.
    if field == "expression":
        return isinstance(current, str) and current.rstrip() == desired.rstrip()
    return current == desired


def reconcile_manifest(
    manifest: dict[str, Any],
    api: AuthentikAPI,
    *,
    apply: bool,
    selected_mappings: set[str] | None = None,
) -> dict[str, Any]:
    configured_ids = {item["id"] for item in manifest["mappings"]}
    if selected_mappings is not None and (unknown := sorted(selected_mappings - configured_ids)):
        raise ReconcileError(f"Unknown scope mapping id(s): {', '.join(unknown)}")

    current_rows = api.list_all(SCOPE_MAPPINGS_PATH)
    plans: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    for definition in manifest["mappings"]:
        if selected_mappings is not None and definition["id"] not in selected_mappings:
            continue
        current = _find_unique(current_rows, field="scope_name", value=definition["scope_name"])
        if current is not None:
            description = str(current.get("description", ""))
            if current.get("name") != definition["name"] or MANAGED_MARKER not in description.casefold():
                raise ReconcileError(
                    f"Scope {definition['scope_name']!r} already exists but is not owned by this manifest; refusing mutation"
                )
            if current.get("pk") is None:
                raise ReconcileError(f"Managed scope {definition['scope_name']!r} has no primary key")
        desired = {field: definition[field] for field in MANAGED_FIELDS}
        fields = [
            field
            for field in MANAGED_FIELDS
            if current is None or not _managed_value_matches(field, current.get(field), desired[field])
        ]
        action = "create" if current is None else "update" if fields else "unchanged"
        if action != "unchanged":
            changes.append(
                {
                    "scope_name": definition["scope_name"],
                    "action": action,
                    "pk": current.get("pk") if current else None,
                    "fields": sorted(fields),
                }
            )
        plans.append(
            {"definition": definition, "current": current, "desired": desired, "action": action, "fields": fields}
        )

    results: list[dict[str, Any]] = []
    for plan in plans:
        current = plan["current"]
        action = plan["action"]
        pk = current.get("pk") if current else None
        if apply and action == "create":
            created = api.post(SCOPE_MAPPINGS_PATH, plan["desired"])
            pk = created.get("pk")
            if pk is None:
                raise ReconcileError(f"Authentik did not return a primary key for {plan['definition']['scope_name']!r}")
        elif apply and action == "update":
            updated = api.patch(
                f"{SCOPE_MAPPINGS_PATH}{pk}/", {field: plan["desired"][field] for field in plan["fields"]}
            )
            pk = updated.get("pk", pk)
        results.append({"scope_name": plan["definition"]["scope_name"], "pk": pk, "action": action})

    return {
        "status": "ok",
        "mode": "apply" if apply else "check",
        "changed": bool(changes),
        "change_count": len(changes),
        "changes": changes,
        "mappings": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--mapping", action="append", dest="mappings", help="Reconcile only this manifest mapping")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Report drift without mutation (default)")
    mode.add_argument("--apply", action="store_true", help="Create or update repository-owned scope mappings")
    parser.add_argument(
        "--expect-no-change", action="store_true", help="Fail when read-only reconciliation reports drift"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.expect_no_change and args.apply:
        raise ReconcileError("--expect-no-change cannot be combined with --apply")
    token_stat = args.token_file.lstat()
    if not stat.S_ISREG(token_stat.st_mode) or stat.S_IMODE(token_stat.st_mode) & 0o077:
        raise ReconcileError("Authentik token file must be a regular file with no group/world permissions")
    token = args.token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise ReconcileError(f"Authentik token file {args.token_file} is empty")
    parsed_url = urllib.parse.urlsplit(args.base_url)
    if (
        parsed_url.scheme != "https"
        or not parsed_url.netloc
        or parsed_url.username
        or parsed_url.password
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise ReconcileError("--base-url must be an HTTPS origin without credentials, query, or fragment")
    manifest = load_manifest(args.manifest)
    result = reconcile_manifest(
        manifest,
        HTTPAuthentikAPI(args.base_url, token),
        apply=args.apply,
        selected_mappings=set(args.mappings) if args.mappings else None,
    )
    print(json.dumps(result, sort_keys=True))
    return 2 if args.expect_no_change and result["changed"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ReconcileError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
