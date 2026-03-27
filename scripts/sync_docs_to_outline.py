#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request
from http import cookiejar


DEFAULT_BASE_URL = "https://wiki.lv3.org"
DEFAULT_TOKEN_FILE = Path(".local/outline/api-token.txt")
DEFAULT_USERNAME = "outline.automation"
DEFAULT_PASSWORD_FILE = Path(".local/keycloak/outline.automation-password.txt")
API_TOKEN_SCOPES = [
    "collections.create",
    "collections.delete",
    "collections.info",
    "collections.list",
    "collections.update",
    "documents.create",
    "documents.delete",
    "documents.info",
    "documents.list",
    "documents.update",
]
UUID_NAMESPACE = uuid.UUID("e7dc945f-7c87-4a79-aaab-9a1c6655a7aa")


@dataclass(frozen=True)
class CollectionSpec:
    slug: str
    name: str
    description: str
    landing_title: str
    landing_markdown: str


COLLECTION_SPECS = [
    CollectionSpec(
        slug="adrs",
        name="ADRs",
        description="Architectural decisions for the LV3 platform.",
        landing_title="ADR Index",
        landing_markdown="",
    ),
    CollectionSpec(
        slug="runbooks",
        name="Runbooks",
        description="Operational procedures and operator-facing workflows for the LV3 platform.",
        landing_title="Runbook Index",
        landing_markdown="",
    ),
    CollectionSpec(
        slug="incident-postmortems",
        name="Incident Postmortems",
        description="Post-incident analysis, remediations, and operational follow-up.",
        landing_title="Postmortem Index",
        landing_markdown="",
    ),
    CollectionSpec(
        slug="agent-findings",
        name="Agent Findings",
        description="Agent-authored findings, investigation notes, and suggested follow-up work.",
        landing_title="Agent Findings Guide",
        landing_markdown="",
    ),
    CollectionSpec(
        slug="architecture",
        name="Architecture",
        description="System overviews, structural maps, and architecture-facing reference surfaces.",
        landing_title="Architecture Overview",
        landing_markdown="",
    ),
]


class KeycloakLoginFormParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_login_form = False
        self.form_action: str | None = None
        self.hidden_fields: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "form" and attr_map.get("id") == "kc-form-login":
            self.in_login_form = True
            self.form_action = attr_map.get("action")
            return
        if self.in_login_form and tag == "input":
            name = attr_map.get("name")
            if name:
                self.hidden_fields[name] = attr_map.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self.in_login_form:
            self.in_login_form = False


class OutlineError(RuntimeError):
    pass


class OutlineClient:
    def __init__(
        self,
        base_url: str,
        *,
        api_token: str | None = None,
        app_token: str | None = None,
        opener: request.OpenerDirector | None = None,
        csrf_token: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.app_token = app_token
        self.opener = opener
        self.csrf_token = csrf_token

    def call(self, endpoint: str, payload: dict[str, Any], *, use_app_token: bool = False) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        token = self.app_token if use_app_token else self.api_token
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif self.csrf_token:
            headers["X-CSRF-Token"] = self.csrf_token
        req = request.Request(
            f"{self.base_url}/api/{endpoint}",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            if self.opener is not None:
                response_ctx = self.opener.open(req, timeout=60)
            else:
                response_ctx = request.urlopen(req, timeout=60)  # noqa: S310
            with response_ctx as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:  # noqa: PERF203
            detail = exc.read().decode("utf-8", errors="replace")
            raise OutlineError(f"{endpoint} failed with HTTP {exc.code}: {detail}") from exc


def deterministic_id(prefix: str, value: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, f"{prefix}:{value}"))


def repo_link(repo_root: Path, path: Path) -> str:
    return str((repo_root / path).resolve())


def parse_markdown_title(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("-", " ").replace("_", " ").title()


def render_adrs_index(repo_root: Path) -> str:
    lines = [
        "# ADR Index",
        "",
        "The repository remains the canonical source of truth. This page is a living index of the current ADR set.",
        "",
    ]
    for path in sorted((repo_root / "docs/adr").glob("*.md")):
        title = parse_markdown_title(path)
        metadata = extract_metadata(path)
        status = metadata.get("Status", "unknown")
        impl = metadata.get("Implementation Status", "unknown")
        lines.append(
            f"- [{path.name}]({repo_link(repo_root, path.relative_to(repo_root))})"
            f" - **{title}**"
            f" - Status: `{status}`"
            f" - Implementation: `{impl}`"
        )
    return "\n".join(lines) + "\n"


def render_runbooks_index(repo_root: Path) -> str:
    lines = [
        "# Runbook Index",
        "",
        "Operational procedures mirrored from the git repository for quick browsing and search.",
        "",
    ]
    for path in sorted((repo_root / "docs/runbooks").glob("*.md")):
        title = parse_markdown_title(path)
        lines.append(f"- [{title}]({repo_link(repo_root, path.relative_to(repo_root))})")
    lines.extend(
        [
            "",
            "## Drafts",
            "",
            "Repo-managed draft publication targets the `Runbooks / Drafts` area as new automation-generated drafts are introduced.",
            "",
        ]
    )
    return "\n".join(lines)


def render_architecture_overview(repo_root: Path) -> str:
    return "\n".join(
        [
            "# Architecture Overview",
            "",
            "This collection links the main structural surfaces that define and explain the LV3 platform.",
            "",
            f"- [README.md]({repo_link(repo_root, Path('README.md'))})",
            f"- [AGENTS.md]({repo_link(repo_root, Path('AGENTS.md'))})",
            f"- [.repo-structure.yaml]({repo_link(repo_root, Path('.repo-structure.yaml'))})",
            f"- [.config-locations.yaml]({repo_link(repo_root, Path('.config-locations.yaml'))})",
            f"- [ADR Index YAML]({repo_link(repo_root, Path('docs/adr/.index.yaml'))})",
            f"- [workstreams.yaml]({repo_link(repo_root, Path('workstreams.yaml'))})",
            "",
        ]
    )


def render_postmortem_index(repo_root: Path) -> str:
    postmortem_roots = [
        repo_root / "docs/postmortems",
        repo_root / "docs/incidents/postmortems",
    ]
    discovered: list[Path] = []
    for root in postmortem_roots:
        if root.exists():
            discovered.extend(sorted(root.rglob("*.md")))
    lines = [
        "# Postmortem Index",
        "",
        "Incident postmortems remain canonical in git. This landing page tracks the current published set.",
        "",
    ]
    if not discovered:
        lines.append("No repo-managed postmortem markdown files are currently published.")
        lines.append("")
        return "\n".join(lines)
    for path in discovered:
        rel = path.relative_to(repo_root)
        lines.append(f"- [{parse_markdown_title(path)}]({repo_link(repo_root, rel)})")
    lines.append("")
    return "\n".join(lines)


def render_agent_findings_guide(_repo_root: Path) -> str:
    return "\n".join(
        [
            "# Agent Findings Guide",
            "",
            "This collection is reserved for governed agent-authored findings.",
            "",
            "Use the repo-managed Outline API token to publish concise findings, evidence links, and follow-up recommendations.",
            "",
            "Suggested conventions:",
            "",
            "- one document per investigation or incident thread",
            "- include the source branch, receipt ids, and exact file links",
            "- prefer links back to the canonical repo files when quoting or summarizing managed surfaces",
            "",
        ]
    )


def extract_metadata(path: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- "):
            if metadata:
                break
            continue
        key, _, value = line[2:].partition(":")
        if value:
            metadata[key.strip()] = value.strip()
    return metadata


def landing_docs(repo_root: Path) -> list[tuple[CollectionSpec, str]]:
    rendered: list[tuple[CollectionSpec, str]] = []
    for spec in COLLECTION_SPECS:
        if spec.slug == "adrs":
            rendered.append((spec, render_adrs_index(repo_root)))
        elif spec.slug == "runbooks":
            rendered.append((spec, render_runbooks_index(repo_root)))
        elif spec.slug == "incident-postmortems":
            rendered.append((spec, render_postmortem_index(repo_root)))
        elif spec.slug == "agent-findings":
            rendered.append((spec, render_agent_findings_guide(repo_root)))
        elif spec.slug == "architecture":
            rendered.append((spec, render_architecture_overview(repo_root)))
    return rendered


def load_file(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def load_api_token(path: Path) -> str:
    if not path.exists():
        raise OutlineError(f"missing API token file: {path}")
    return load_file(path)


def build_opener() -> tuple[request.OpenerDirector, cookiejar.CookieJar]:
    jar = cookiejar.CookieJar()
    opener = request.build_opener(request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", "lv3-outline-sync/1.0")]
    return opener, jar


def find_cookie(jar: cookiejar.CookieJar, name: str) -> str | None:
    for cookie in jar:
        if cookie.name == name:
            return cookie.value
    return None


def bootstrap_token(base_url: str, username: str, password_file: Path, token_name: str, token_file: Path, scope: list[str]) -> int:
    if token_file.exists() and load_file(token_file):
        print(f"api token already present at {token_file}")
        return 0

    opener, jar = build_opener()
    with opener.open(f"{base_url.rstrip('/')}/auth/oidc", timeout=60) as response:  # noqa: S310
        login_html = response.read().decode("utf-8", errors="replace")
        login_url = response.geturl()

    parser = KeycloakLoginFormParser()
    parser.feed(login_html)
    if not parser.form_action:
        raise OutlineError(f"unable to find Keycloak login form at {login_url}")

    form_fields = dict(parser.hidden_fields)
    form_fields["username"] = username
    form_fields["password"] = load_file(password_file)
    payload = parse.urlencode(form_fields).encode("utf-8")
    login_request = request.Request(parser.form_action, data=payload, method="POST")
    login_request.add_header("Content-Type", "application/x-www-form-urlencoded")
    with opener.open(login_request, timeout=60) as response:  # noqa: S310
        _ = response.read()

    app_token = find_cookie(jar, "accessToken")
    csrf_token = find_cookie(jar, "csrfToken")
    client = OutlineClient(base_url, app_token=app_token, opener=opener, csrf_token=csrf_token)
    response = client.call(
        "apiKeys.create",
        {
            "name": token_name,
            "scope": scope,
        },
        use_app_token=True,
    )
    token_payload = response.get("data", {})
    token = token_payload.get("value") or token_payload.get("token")
    if not token:
        raise OutlineError(f"apiKeys.create response did not include a token value: {response}")
    write_file(token_file, token)
    print(f"created api token at {token_file}")
    return 0


def collections_by_name(client: OutlineClient) -> dict[str, dict[str, Any]]:
    response = client.call("collections.list", {})
    return {item["name"]: item for item in response.get("data", [])}


def documents_in_collection(client: OutlineClient, collection_id: str) -> list[dict[str, Any]]:
    response = client.call("documents.list", {"collectionId": collection_id})
    return list(response.get("data", []))


def cleanup_bootstrap_collections(client: OutlineClient) -> list[str]:
    outcomes: list[str] = []
    welcome = collections_by_name(client).get("Welcome")
    if welcome:
        client.call("collections.delete", {"id": welcome["id"]})
        outcomes.append("Welcome collection deleted")
    return outcomes


def ensure_collection(client: OutlineClient, spec: CollectionSpec, *, dry_run: bool) -> tuple[str, str]:
    current = collections_by_name(client).get(spec.name)
    if current:
        if dry_run:
            return current["id"], "checked"
        client.call(
            "collections.update",
            {
                "id": current["id"],
                "name": spec.name,
                "description": spec.description,
                "sharing": False,
            },
        )
        return current["id"], "updated"
    if dry_run:
        return deterministic_id("collection", spec.slug), "created"
    created = client.call(
        "collections.create",
        {
            "name": spec.name,
            "description": spec.description,
            "sharing": False,
        },
    )
    return created["data"]["id"], "created"


def ensure_document(
    client: OutlineClient,
    *,
    collection_id: str,
    title: str,
    markdown: str,
    dry_run: bool,
) -> str:
    matching = [item for item in documents_in_collection(client, collection_id) if item.get("title") == title]
    current = matching[0] if matching else None
    duplicates = matching[1:]
    if dry_run:
        return "updated" if current else "created"
    if current:
        client.call(
            "documents.update",
            {
                "id": current["id"],
                "title": title,
                "text": markdown,
                "publish": True,
                "done": True,
            },
        )
        outcome = "updated"
    else:
        client.call(
            "documents.create",
            {
                "collectionId": collection_id,
                "title": title,
                "text": markdown,
                "publish": True,
            },
        )
        outcome = "created"
    for duplicate in duplicates:
        client.call("documents.delete", {"id": duplicate["id"]})
    return outcome


def sync(repo_root: Path, base_url: str, api_token_file: Path, *, dry_run: bool) -> int:
    client = OutlineClient(base_url, api_token=load_api_token(api_token_file))
    outcomes = cleanup_bootstrap_collections(client) if not dry_run else []
    for spec, markdown in landing_docs(repo_root):
        collection_id, collection_outcome = ensure_collection(client, spec, dry_run=dry_run)
        outcomes.append(f"{spec.name} collection {collection_outcome}")
        if dry_run and collection_outcome == "created":
            document_outcome = "created"
        else:
            document_outcome = ensure_document(
                client,
                collection_id=collection_id,
                title=spec.landing_title,
                markdown=markdown,
                dry_run=dry_run,
            )
        outcomes.append(f"{spec.landing_title} {document_outcome}")
        time.sleep(0.1)
    print("\n".join(outcomes))
    return 0


def verify(repo_root: Path, base_url: str, api_token_file: Path) -> int:
    client = OutlineClient(base_url, api_token=load_api_token(api_token_file))
    available = collections_by_name(client)
    for spec, _markdown in landing_docs(repo_root):
        collection = available.get(spec.name)
        if not collection:
            raise OutlineError(f"missing collection: {spec.name}")
        documents = documents_in_collection(client, collection["id"])
        if not any(document.get("title") == spec.landing_title for document in documents):
            raise OutlineError(f"unexpected landing document title for {spec.name}")
    print("outline living collections verified")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap and sync the LV3 Outline knowledge surface.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap-token", help="Create the repo-managed Outline API token through OIDC.")
    bootstrap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    bootstrap.add_argument("--username", default=DEFAULT_USERNAME)
    bootstrap.add_argument("--password-file", type=Path, default=DEFAULT_PASSWORD_FILE)
    bootstrap.add_argument("--token-name", default="lv3-outline-sync")
    bootstrap.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN_FILE)
    bootstrap.add_argument("--scope", default=",".join(API_TOKEN_SCOPES))

    sync_parser = subparsers.add_parser("sync", help="Sync the managed Outline collections and landing pages.")
    sync_parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    sync_parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    sync_parser.add_argument("--api-token-file", type=Path, default=DEFAULT_TOKEN_FILE)
    sync_parser.add_argument("--dry-run", action="store_true")

    verify_parser = subparsers.add_parser("verify", help="Verify the managed Outline collections and landing pages.")
    verify_parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    verify_parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    verify_parser.add_argument("--api-token-file", type=Path, default=DEFAULT_TOKEN_FILE)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "bootstrap-token":
            scopes = [item.strip() for item in args.scope.split(",") if item.strip()]
            return bootstrap_token(
                base_url=args.base_url,
                username=args.username,
                password_file=args.password_file,
                token_name=args.token_name,
                token_file=args.token_file,
                scope=scopes,
            )
        if args.command == "sync":
            return sync(args.repo_root.resolve(), args.base_url, args.api_token_file, dry_run=args.dry_run)
        if args.command == "verify":
            return verify(args.repo_root.resolve(), args.base_url, args.api_token_file)
        raise OutlineError(f"unknown command: {args.command}")
    except Exception as exc:  # noqa: BLE001
        print(f"outline sync error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
