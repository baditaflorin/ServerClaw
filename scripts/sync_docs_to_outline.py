#!/usr/bin/env python3

from __future__ import annotations

import argparse
import html.parser
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import parse, request

from outline_client import (
    DEFAULT_BASE_URL,
    DEFAULT_TOKEN_FILE,
    OutlineClient,
    OutlineError,
    collections_by_name,
    deterministic_id,
    documents_in_collection,
    ensure_document,
    load_api_token,
    load_file,
)

API_TOKEN_SCOPES = [
    "collections.create",
    "collections.delete",
    "collections.info",
    "collections.list",
    "collections.update",
    "collections.memberships",
    "collections.addUser",
    "collections.removeUser",
    "collections.addGroup",
    "collections.removeGroup",
    "documents.create",
    "documents.delete",
    "documents.info",
    "documents.list",
    "documents.update",
    "groups.create",
    "groups.delete",
    "groups.info",
    "groups.list",
    "groups.update",
    "groups.memberships",
    "groups.addUser",
    "groups.removeUser",
    "users.list",
    "users.read",
]


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
    CollectionSpec(
        slug="changelogs",
        name="Changelogs",
        description="Release notes, version history, and automated changelog entries for the LV3 platform.",
        landing_title="Changelog Index",
        landing_markdown="",
    ),
    CollectionSpec(
        slug="automation-runs",
        name="Automation Runs",
        description="Programmatically generated outputs from live playbook runs, CI/CD pipelines, and agent executions.",
        landing_title="Automation Runs Guide",
        landing_markdown="",
    ),
    CollectionSpec(
        slug="gate-bypass-waivers",
        name="Gate Bypass Waivers",
        description="Every validation gate bypass waiver receipt logged by log_gate_bypass.py.",
        landing_title="Gate Bypass Waivers Index",
        landing_markdown="",
    ),
    CollectionSpec(
        slug="security-compliance",
        name="Security & Compliance",
        description="CVE scans, SBOM, security posture reports, TLS assurance, and subdomain exposure audits.",
        landing_title="Security & Compliance Index",
        landing_markdown="",
    ),
    CollectionSpec(
        slug="dr-backup-status",
        name="DR & Backup Status",
        description="Disaster recovery table-top reviews, restore verifications, and backup coverage ledger reports.",
        landing_title="DR & Backup Status Index",
        landing_markdown="",
    ),
    CollectionSpec(
        slug="platform-findings",
        name="Platform Findings",
        description="Daily findings digests, weekly capacity reports, mutation audit summaries, and drift reports.",
        landing_title="Platform Findings Index",
        landing_markdown="",
    ),
    CollectionSpec(
        slug="platform-tools",
        name="Platform Tools",
        description="Auto-generated index of all scripts, Windmill jobs, outline_tool.py commands, and Makefile targets available to operators and LLM agents.",
        landing_title="Platform Tools Index",
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


GITHUB_REPO_BASE = "https://github.com/baditaflorin/ServerClaw/blob/main"


def repo_link(repo_root: Path, path: Path) -> str:
    """Return a publicly-accessible GitHub URL for a repo-relative path."""
    return f"{GITHUB_REPO_BASE}/{path}"


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


def render_changelog_index(repo_root: Path) -> str:
    lines = [
        "# Changelog Index",
        "",
        "Release notes and version history for the LV3 platform.",
        "The canonical source of truth is `changelog.md` in the repository.",
        "",
        "Use `outline_tool.py changelog.push` to publish the current changelog here.",
        "",
    ]
    changelog_path = repo_root / "changelog.md"
    if changelog_path.exists():
        lines.append(f"- [changelog.md]({repo_link(repo_root, Path('changelog.md'))})")
    release_notes_root = repo_root / "docs/release-notes"
    if release_notes_root.exists():
        for path in sorted(release_notes_root.glob("*.md")):
            title = parse_markdown_title(path)
            lines.append(f"- [{title}]({repo_link(repo_root, path.relative_to(repo_root))})")
    lines.append("")
    return "\n".join(lines)


def render_bypass_waivers_index(repo_root: Path) -> str:
    receipt_dir = repo_root / "receipts" / "gate-bypasses"
    lines = [
        "# Gate Bypass Waivers Index",
        "",
        "Every validation gate bypass waiver is logged here automatically when `log_gate_bypass.py` runs.",
        "",
        "Each document in this collection corresponds to one receipt file in `receipts/gate-bypasses/`.",
        "",
        f"- [Gate Bypass Schema]({repo_link(repo_root, Path('docs/schema/gate-bypass-waiver-receipt.schema.json'))})",
        f"- [Waiver Catalog]({repo_link(repo_root, Path('config/gate-bypass-waiver-catalog.json'))})",
        f"- [ADR 0267]({repo_link(repo_root, Path('docs/adr/0267-expiring-gate-bypass-waivers-with-structured-reason-codes.md'))})",
        "",
    ]
    if receipt_dir.exists():
        receipts = sorted(receipt_dir.glob("*.json"), reverse=True)
        lines.append(f"## Recent Receipts ({len(receipts)} total)")
        lines.append("")
        for path in receipts[:20]:
            lines.append(f"- `{path.name}`")
        if len(receipts) > 20:
            lines.append(f"- *(and {len(receipts) - 20} more — browse the collection documents)*")
        lines.append("")
    lines.append("Use `outline_tool.py bypass.backfill` to upload all existing receipts.")
    lines.append("")
    return "\n".join(lines)


def render_automation_runs_guide(_repo_root: Path) -> str:
    return "\n".join(
        [
            "# Automation Runs Guide",
            "",
            "This collection receives programmatically generated outputs from the LV3 platform automation layer.",
            "",
            "Sources that publish here:",
            "",
            "- Live Ansible playbook runs (via `outline_tool.py document.publish`)",
            "- CI/CD pipeline summaries",
            "- Agent-triggered deployments and verification outputs",
            "- Scheduled automation jobs",
            "",
            "Naming convention: `<service>-<YYYY-MM-DD>[-<run-id>]`",
            "",
            "Use `outline_tool.py document.publish --collection 'Automation Runs' --title <title> --stdin` to publish run output.",
            "",
        ]
    )


def _receipt_count(repo_root: Path, subdir: str) -> int:
    d = repo_root / "receipts" / subdir
    return len(list(d.glob("*.json"))) if d.exists() else 0


def render_security_compliance_index(repo_root: Path) -> str:
    lines = [
        "# Security & Compliance Index",
        "",
        "Security scan outputs published automatically by the LV3 platform scripts.",
        "Every document in this collection corresponds to one scan run.",
        "",
        "## Sources",
        "",
        "| Source | Script | Receipt Dir | Collection Key |",
        "|---|---|---|---|",
        f"| CVE / SBOM scans | `scripts/sbom_refresh.py` | `receipts/cve/`, `receipts/sbom/` | {_receipt_count(repo_root, 'cve')} CVE + {_receipt_count(repo_root, 'sbom')} SBOM receipts |",
        f"| Security posture | `scripts/security_posture_report.py` | `receipts/security-reports/` | {_receipt_count(repo_root, 'security-reports')} receipts |",
        f"| HTTPS/TLS assurance | `scripts/https_tls_assurance.py` | `receipts/https-tls-assurance/` | {_receipt_count(repo_root, 'https-tls-assurance')} receipts |",
        f"| Subdomain exposure | `scripts/subdomain_exposure_audit.py` | `receipts/subdomain-exposure-audit/` | {_receipt_count(repo_root, 'subdomain-exposure-audit')} receipts |",
        "",
        "## Key References",
        "",
        f"- [ADR 0346 — Outline automation hooks]({repo_link(repo_root, Path('docs/adr/0346-outline-programmatic-wiki-api-and-automation-hooks.md'))})",
        f"- [config/image-catalog.json]({repo_link(repo_root, Path('config/image-catalog.json'))})",
        "",
        "Use `outline_tool.py receipt.backfill --collection 'Security & Compliance' --receipt-dir receipts/cve` to upload existing receipts.",
        "",
    ]
    return "\n".join(lines)


def render_dr_backup_index(repo_root: Path) -> str:
    lines = [
        "# DR & Backup Status Index",
        "",
        "Disaster recovery and backup health outputs published automatically by platform scripts.",
        "",
        "## Sources",
        "",
        "| Source | Script | Receipt Dir | Count |",
        "|---|---|---|---|",
        f"| Restore verifications | `scripts/restore_verification.py` | `receipts/restore-verifications/` | {_receipt_count(repo_root, 'restore-verifications')} |",
        f"| Backup coverage ledger | `scripts/backup_coverage_ledger.py` | `receipts/backup-coverage/` | {_receipt_count(repo_root, 'backup-coverage')} |",
        f"| Restic backups | `scripts/restic_config_backup.py` | `receipts/restic-backups/` | {_receipt_count(repo_root, 'restic-backups')} |",
        f"| DR table-top reviews | `scripts/generate_dr_report.py` | `receipts/dr-table-top-reviews/` | {_receipt_count(repo_root, 'dr-table-top-reviews')} |",
        "",
        "## Key References",
        "",
        f"- [ADR 0100 — Disaster recovery]({repo_link(repo_root, Path('docs/adr/0100-disaster-recovery-runbook.md'))})"
        if (repo_root / "docs/adr/0100-disaster-recovery-runbook.md").exists()
        else "",
        f"- [config/dr-targets.yaml]({repo_link(repo_root, Path('config/dr-targets.yaml'))})"
        if (repo_root / "config/dr-targets.yaml").exists()
        else "",
        "",
        "Use `outline_tool.py receipt.backfill --collection 'DR & Backup Status' --receipt-dir receipts/restore-verifications` to upload existing receipts.",
        "",
    ]
    return "\n".join(line for line in lines if line is not None)


def render_platform_findings_index(_repo_root: Path) -> str:
    return "\n".join(
        [
            "# Platform Findings Index",
            "",
            "Automated findings, digests, and drift reports published by the LV3 platform.",
            "",
            "## Sources",
            "",
            "| Source | Windmill Script | Cadence |",
            "|---|---|---|",
            "| Daily findings digest | `platform-findings-daily-digest.py` | Daily |",
            "| Weekly capacity report | `weekly-capacity-report.py` | Weekly |",
            "| Mutation audit summary | `lv3-mutation-audit.py` | Per-event |",
            "| Drift reports (infra/DNS/Docker/TLS) | `continuous-drift-detection.py` | Scheduled |",
            "| Weekly security scan | `weekly-security-scan.py` | Weekly |",
            "",
            "## Naming Convention",
            "",
            "Documents follow the pattern: `{report-type}-{YYYY-MM-DD}`",
            "",
            "Examples: `findings-digest-2026-04-05`, `capacity-report-2026-04-05`, `drift-report-2026-04-05`",
            "",
        ]
    )


def _script_docstring(path: Path) -> str:
    """Extract the module docstring from a Python script."""
    import re as _re

    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:600]
        # Try triple-double-quoted docstring (single or multi-line — take first line)
        m = _re.search(r'"""(.*?)(?:"""|$)', text, _re.DOTALL)
        if m:
            first_line = m.group(1).strip().splitlines()[0].strip() if m.group(1).strip() else ""
            if first_line:
                return first_line[:120]
        # Try triple-single-quoted docstring
        m = _re.search(r"'''(.*?)(?:'''|$)", text, _re.DOTALL)
        if m:
            first_line = m.group(1).strip().splitlines()[0].strip() if m.group(1).strip() else ""
            if first_line:
                return first_line[:120]
        # Fall back to first non-shebang comment
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#!"):
                continue
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip()[:120]
    except OSError:
        pass
    return ""


def render_platform_tools_index(repo_root: Path) -> str:
    lines = [
        "# Platform Tools Index",
        "",
        "Auto-generated index of all scripts, Windmill jobs, and CLI tools available to operators and LLM agents.",
        "Updated on every `sync_docs_to_outline.py sync` run.",
        "",
        "## outline_tool.py — Agent Wiki API",
        "",
        'All commands output `{"ok": true/false, ...}` JSON. Auth via `OUTLINE_API_TOKEN` env var.',
        "",
        "| Command | Purpose |",
        "|---|---|",
        "| `collection.list/create/delete` | Manage wiki collections |",
        "| `collection.members/grant/revoke` | User access control |",
        "| `collection.grant-group/revoke-group` | Group access control |",
        "| `document.list/publish/get/delete/search` | Document CRUD |",
        "| `changelog.push` | Push `changelog.md` to Changelogs collection |",
        "| `bypass.publish/backfill` | Publish gate bypass receipts |",
        "| `receipt.publish/backfill` | Publish any JSON receipt file |",
        "| `user.list` | List workspace users |",
        "| `group.list/create/delete/members/add-user/remove-user` | Group management |",
        "",
        f"Source: [`scripts/outline_tool.py`]({repo_link(repo_root, Path('scripts/outline_tool.py'))})",
        "",
    ]

    # Scripts index
    scripts_dir = repo_root / "scripts"
    scripts = sorted(p for p in scripts_dir.glob("*.py") if not p.name.startswith("_"))
    lines += [
        "## scripts/ — Operator & Automation Scripts",
        "",
        "| Script | Purpose |",
        "|---|---|",
    ]
    for path in scripts:
        doc = _script_docstring(path)
        link = f"[`{path.name}`]({repo_link(repo_root, path.relative_to(repo_root))})"
        lines.append(f"| {link} | {doc} |")
    lines.append("")

    # Windmill scripts index
    windmill_dir = repo_root / "config" / "windmill" / "scripts"
    if windmill_dir.exists():
        windmill_scripts = sorted(windmill_dir.glob("*.py"))
        lines += [
            "## config/windmill/scripts/ — Windmill Jobs",
            "",
            "| Script | Purpose |",
            "|---|---|",
        ]
        for path in windmill_scripts:
            doc = _script_docstring(path)
            link = f"[`{path.name}`]({repo_link(repo_root, path.relative_to(repo_root))})"
            lines.append(f"| {link} | {doc} |")
        lines.append("")

    # Makefile targets
    makefile = repo_root / "Makefile"
    if makefile.exists():
        targets: list[str] = []
        for line in makefile.read_text(encoding="utf-8").splitlines():
            if (
                line
                and not line.startswith("\t")
                and not line.startswith("#")
                and not line.startswith(".")
                and ":" in line
            ):
                target = line.split(":")[0].strip()
                if target and " " not in target and target not in ("PHONY", "all"):
                    targets.append(target)
        if targets:
            lines += [
                "## Makefile Targets",
                "",
                ", ".join(f"`{t}`" for t in targets[:60]),
                "",
                f"Full list: [`Makefile`]({repo_link(repo_root, Path('Makefile'))})",
                "",
            ]

    return "\n".join(lines)


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
        elif spec.slug == "changelogs":
            rendered.append((spec, render_changelog_index(repo_root)))
        elif spec.slug == "automation-runs":
            rendered.append((spec, render_automation_runs_guide(repo_root)))
        elif spec.slug == "gate-bypass-waivers":
            rendered.append((spec, render_bypass_waivers_index(repo_root)))
        elif spec.slug == "security-compliance":
            rendered.append((spec, render_security_compliance_index(repo_root)))
        elif spec.slug == "dr-backup-status":
            rendered.append((spec, render_dr_backup_index(repo_root)))
        elif spec.slug == "platform-findings":
            rendered.append((spec, render_platform_findings_index(repo_root)))
        elif spec.slug == "platform-tools":
            rendered.append((spec, render_platform_tools_index(repo_root)))
    return rendered


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def build_opener() -> tuple[request.OpenerDirector, Any]:
    from http import cookiejar

    jar = cookiejar.CookieJar()
    opener = request.build_opener(request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", "lv3-outline-sync/1.0")]
    return opener, jar


def find_cookie(jar: Any, name: str) -> str | None:
    for cookie in jar:
        if cookie.name == name:
            return cookie.value
    return None


def bootstrap_token(
    base_url: str, username: str, password_file: Path, token_name: str, token_file: Path, scope: list[str]
) -> int:
    if token_file.exists() and load_file(token_file):
        print(f"api token already present at {token_file}")
        return 0

    opener, jar = build_opener()
    with opener.open(f"{base_url.rstrip('/')}/auth/oidc", timeout=60) as response:
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
    with opener.open(login_request, timeout=60) as response:
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
                "permission": "read",
                "sharing": True,
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
            "permission": "read",
            "sharing": True,
        },
    )
    return created["data"]["id"], "created"


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
    bootstrap.add_argument("--username", default="outline.automation")
    bootstrap.add_argument(
        "--password-file", type=Path, default=Path(".local/keycloak/outline.automation-password.txt")
    )
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
    except Exception as exc:
        print(f"outline sync error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
