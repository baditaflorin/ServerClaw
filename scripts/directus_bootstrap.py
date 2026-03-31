#!/usr/bin/env python3
"""Bootstrap and verify the repo-managed Directus surface."""

from __future__ import annotations

import argparse
import json
import ssl
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request


DEFAULT_TIMEOUT = 30


class DirectusError(RuntimeError):
    """Raised when the Directus API returns an unexpected response."""


class NoRedirectHandler(request.HTTPRedirectHandler):
    """Capture redirect responses without following them."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str
    data_type: str
    required: bool
    interface: str
    note: str
    max_length: int | None = None


FIELD_SPECS = (
    FieldSpec(
        name="service_name",
        type="string",
        data_type="varchar",
        required=True,
        interface="input",
        note="Stable service identifier.",
        max_length=255,
    ),
    FieldSpec(
        name="public_hostname",
        type="string",
        data_type="varchar",
        required=True,
        interface="input",
        note="Published hostname for the governed service.",
        max_length=255,
    ),
    FieldSpec(
        name="internal_url",
        type="string",
        data_type="varchar",
        required=True,
        interface="input",
        note="Private or guest-local URL used by governed automation.",
        max_length=512,
    ),
)


def read_secret(path: str) -> str:
    value = Path(path).read_text(encoding="utf-8").strip()
    if not value:
        raise DirectusError(f"{path} is empty")
    return value


def build_opener(base_url: str, follow_redirects: bool = True) -> request.OpenerDirector:
    handlers: list[Any] = []
    if not follow_redirects:
        handlers.append(NoRedirectHandler())
    if base_url.startswith("https://"):
        handlers.append(request.HTTPSHandler(context=ssl.create_default_context()))
    return request.build_opener(*handlers)


def api_request(
    opener: request.OpenerDirector,
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    expected_statuses: tuple[int, ...] = (200,),
    return_json: bool = True,
) -> Any:
    headers = {"Accept": "application/json"}
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = request.Request(f"{base_url}{path}", data=payload, headers=headers, method=method)
    try:
        with opener.open(req, timeout=DEFAULT_TIMEOUT) as resp:
            status = resp.getcode()
            content = resp.read()
            if status not in expected_statuses:
                raise DirectusError(f"{method} {path} returned {status}, expected {expected_statuses}")
            if not content:
                return None
            if return_json:
                return json.loads(content)
            return content.decode("utf-8")
    except error.HTTPError as exc:
        content = exc.read().decode("utf-8", errors="replace")
        if exc.code in expected_statuses:
            if not content:
                return None
            if return_json:
                return json.loads(content)
            return content
        raise DirectusError(f"{method} {path} returned {exc.code}: {content}") from exc


def login(base_url: str, email: str, password: str) -> str:
    opener = build_opener(base_url)
    response = api_request(
        opener,
        base_url,
        "POST",
        "/auth/login",
        body={"email": email, "password": password},
    )
    return str(response["data"]["access_token"])


def list_collection_names(opener: request.OpenerDirector, base_url: str, token: str) -> set[str]:
    response = api_request(opener, base_url, "GET", "/collections", token=token)
    return {str(item["collection"]) for item in response.get("data", [])}


def list_field_names(opener: request.OpenerDirector, base_url: str, token: str, collection: str) -> set[str]:
    response = api_request(opener, base_url, "GET", f"/fields/{collection}", token=token)
    return {str(item["field"]) for item in response.get("data", [])}


def ensure_collection(opener: request.OpenerDirector, base_url: str, token: str, collection: str) -> bool:
    if collection in list_collection_names(opener, base_url, token):
        return False
    api_request(
        opener,
        base_url,
        "POST",
        "/collections",
        token=token,
        body={
            "collection": collection,
            "meta": {
                "icon": "storage",
                "note": "Repo-managed Directus service registry collection.",
            },
            "schema": {"name": collection},
        },
        expected_statuses=(200,),
    )
    return True


def ensure_field(
    opener: request.OpenerDirector,
    base_url: str,
    token: str,
    collection: str,
    spec: FieldSpec,
) -> bool:
    if spec.name in list_field_names(opener, base_url, token, collection):
        return False

    schema: dict[str, Any] = {
        "name": spec.name,
        "table": collection,
        "data_type": spec.data_type,
        "is_nullable": not spec.required,
    }
    if spec.max_length is not None:
        schema["max_length"] = spec.max_length

    api_request(
        opener,
        base_url,
        "POST",
        f"/fields/{collection}",
        token=token,
        body={
            "field": spec.name,
            "type": spec.type,
            "schema": schema,
            "meta": {
                "interface": spec.interface,
                "required": spec.required,
                "width": "half",
                "note": spec.note,
            },
        },
        expected_statuses=(200,),
    )
    return True


def ensure_service_item(
    opener: request.OpenerDirector,
    base_url: str,
    token: str,
    collection: str,
    service_name: str,
    public_hostname: str,
    internal_url: str,
) -> bool:
    query = parse.urlencode(
        {
            "limit": "1",
            "filter[service_name][_eq]": service_name,
        }
    )
    response = api_request(opener, base_url, "GET", f"/items/{collection}?{query}", token=token)
    data = response.get("data", [])
    desired = {
        "service_name": service_name,
        "public_hostname": public_hostname,
        "internal_url": internal_url,
    }
    if not data:
        api_request(
            opener,
            base_url,
            "POST",
            f"/items/{collection}",
            token=token,
            body=desired,
            expected_statuses=(200,),
        )
        return True

    item = data[0]
    if (
        item.get("public_hostname") == public_hostname
        and item.get("internal_url") == internal_url
    ):
        return False

    api_request(
        opener,
        base_url,
        "PATCH",
        f"/items/{collection}/{item['id']}",
        token=token,
        body=desired,
        expected_statuses=(200,),
    )
    return True


def bootstrap(args: argparse.Namespace) -> int:
    token = login(args.base_url, args.admin_email, read_secret(args.admin_password_file))
    opener = build_opener(args.base_url)
    changes: list[str] = []

    if ensure_collection(opener, args.base_url, token, args.collection):
        changes.append("collection")

    for spec in FIELD_SPECS:
        if ensure_field(opener, args.base_url, token, args.collection, spec):
            changes.append(f"field:{spec.name}")

    if ensure_service_item(
        opener,
        args.base_url,
        token,
        args.collection,
        args.service_name,
        args.public_hostname,
        args.internal_url,
    ):
        changes.append("item")

    print(json.dumps({"changed": bool(changes), "changes": changes}))
    return 0


def verify_public(args: argparse.Namespace) -> int:
    opener = build_opener(args.base_url)
    no_redirect = build_opener(args.base_url, follow_redirects=False)
    token = read_secret(args.api_token_file)

    health = api_request(opener, args.base_url, "GET", "/server/health")
    if health.get("status") != "ok":
        raise DirectusError("/server/health did not report status=ok")

    ping = api_request(opener, args.base_url, "GET", "/server/ping", return_json=False)
    if ping.strip() != "pong":
        raise DirectusError("/server/ping did not return pong")

    openapi = api_request(opener, args.base_url, "GET", "/server/specs/oas")
    if "paths" not in openapi:
        raise DirectusError("/server/specs/oas did not look like an OpenAPI document")
    if args.openapi_output:
        output_path = Path(args.openapi_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(openapi, indent=2) + "\n", encoding="utf-8")

    req = request.Request(f"{args.base_url}/auth/login/keycloak", method="GET")
    try:
        no_redirect.open(req, timeout=DEFAULT_TIMEOUT)
    except error.HTTPError as exc:
        if exc.code not in (301, 302, 303, 307, 308):
            raise DirectusError(f"/auth/login/keycloak returned unexpected status {exc.code}") from exc
        location = exc.headers.get("Location", "")
        if args.expected_sso_host not in location:
            raise DirectusError(f"SSO redirect did not point at {args.expected_sso_host}: {location}")
    else:
        raise DirectusError("/auth/login/keycloak unexpectedly succeeded without redirecting")

    rest = api_request(
        opener,
        args.base_url,
        "GET",
        f"/items/{args.collection}?limit=10",
        token=token,
    )
    items = rest.get("data", [])
    if not any(item.get("service_name") == args.expected_service_name for item in items):
        raise DirectusError("REST verification did not return the expected Directus service-registry row")

    graphql = api_request(
        opener,
        args.base_url,
        "POST",
        "/graphql",
        token=token,
        body={
            "query": "query { service_registry { id service_name public_hostname internal_url } }",
        },
    )
    rows = graphql.get("data", {}).get("service_registry", [])
    if not any(row.get("service_name") == args.expected_service_name for row in rows):
        raise DirectusError("GraphQL verification did not return the expected Directus service-registry row")

    print(
        json.dumps(
            {
                "status": "ok",
                "collection": args.collection,
                "service_name": args.expected_service_name,
                "rest_items": len(items),
                "graphql_items": len(rows),
            }
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap", help="Create the governed collection fields and seed item.")
    bootstrap_parser.add_argument("--base-url", required=True)
    bootstrap_parser.add_argument("--admin-email", required=True)
    bootstrap_parser.add_argument("--admin-password-file", required=True)
    bootstrap_parser.add_argument("--collection", default="service_registry")
    bootstrap_parser.add_argument("--service-name", required=True)
    bootstrap_parser.add_argument("--public-hostname", required=True)
    bootstrap_parser.add_argument("--internal-url", required=True)
    bootstrap_parser.set_defaults(func=bootstrap)

    verify_parser = subparsers.add_parser("verify-public", help="Verify the public Directus health, SSO redirect, REST, and GraphQL contracts.")
    verify_parser.add_argument("--base-url", required=True)
    verify_parser.add_argument("--api-token-file", required=True)
    verify_parser.add_argument("--collection", default="service_registry")
    verify_parser.add_argument("--expected-service-name", required=True)
    verify_parser.add_argument("--expected-sso-host", required=True)
    verify_parser.add_argument("--openapi-output")
    verify_parser.set_defaults(func=verify_public)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
      return int(args.func(args))
    except DirectusError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
