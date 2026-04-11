#!/usr/bin/env python3
"""Agent-facing Outline wiki tool for programmatic document management.

Other LLM agents and automation scripts can call this tool to create, read,
update, and delete collections and documents in the LV3 Outline wiki.

All commands output JSON so results can be parsed by downstream agents.

Usage examples:

  # List all collections
  python3 scripts/outline_tool.py collection.list

  # Create a collection
  python3 scripts/outline_tool.py collection.create --name "My Docs" --description "..."

  # Publish a document from a file
  python3 scripts/outline_tool.py document.publish \\
      --collection "Agent Findings" --title "My Finding" --file finding.md

  # Publish a document from stdin (pipe-friendly)
  echo "# My doc" | python3 scripts/outline_tool.py document.publish \\
      --collection "Automation Runs" --title "deploy-2026-04-05" --stdin

  # Push the repo changelog to the Changelogs collection
  python3 scripts/outline_tool.py changelog.push

  # Search documents
  python3 scripts/outline_tool.py document.search --query "postgres migration"

  # List workspace users
  python3 scripts/outline_tool.py user.list

  # Grant a user read access to a collection
  python3 scripts/outline_tool.py collection.grant \\
      --collection "Agent Findings" --user "alice@example.com" --permission read

  # Revoke a user's access to a collection
  python3 scripts/outline_tool.py collection.revoke \\
      --collection "Agent Findings" --user "alice@example.com"

  # List who has access to a collection
  python3 scripts/outline_tool.py collection.members --collection "ADRs"

  # Create a user group
  python3 scripts/outline_tool.py group.create --name "Platform Engineers"

  # Add a user to a group
  python3 scripts/outline_tool.py group.add-user \\
      --group "Platform Engineers" --user "alice@example.com"

  # Grant a group access to a collection
  python3 scripts/outline_tool.py collection.grant-group \\
      --collection "ADRs" --group "Platform Engineers" --permission read_write

NOTE: user/group management commands require a token with scopes:
  users.list, users.read, collections.memberships, collections.addUser,
  collections.removeUser, collections.addGroup, collections.removeGroup,
  groups.list, groups.create, groups.addUser, groups.removeUser
  Re-bootstrap the API token after expanding outline_api_token_scopes.

Environment variables:
  OUTLINE_API_TOKEN   API token (overrides --token-file)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

GITHUB_REPO_BASE = "https://github.com/baditaflorin/ServerClaw/blob/main"
_RELATIVE_LINK_RE = re.compile(r"\[([^\]]+)\]\((?!https?://|mailto:|#)([^)]+)\)")


def _rewrite_links(content: str) -> str:
    """Rewrite relative markdown links to absolute GitHub URLs.

    Links pointing to build/ artifacts or non-committed paths are stripped
    to plain text since they have no public URL equivalent.
    """
    skip_prefixes = ("build/", ".local/", ".claude/")

    def replace(m: re.Match) -> str:
        label, href = m.group(1), m.group(2)
        if any(href.startswith(p) for p in skip_prefixes):
            return label  # strip link, keep label text
        return f"[{label}]({GITHUB_REPO_BASE}/{href})"

    return _RELATIVE_LINK_RE.sub(replace, content)


from outline_client import (
    DEFAULT_BASE_URL,
    DEFAULT_TOKEN_FILE,
    OutlineClient,
    OutlineError,
    collections_by_name,
    documents_in_collection,
    load_api_token,
)

_DEFAULT_CHANGELOG_COLLECTION = "Changelogs"
_DEFAULT_RUNS_COLLECTION = "Automation Runs"
_DEFAULT_BYPASS_COLLECTION = "Gate Bypass Waivers"


# ---------------------------------------------------------------------------
# Bypass receipt helpers
# ---------------------------------------------------------------------------


def _receipt_to_markdown(data: dict[str, Any], filename: str = "") -> str:
    """Format a gate bypass waiver receipt JSON as a human-readable markdown doc."""
    schema = data.get("schema_version", "legacy")
    bypass = data.get("bypass", "unknown")
    branch = data.get("branch", "unknown")
    commit = data.get("commit", "unknown")[:12]
    source = data.get("source", "unknown")
    created_at = data.get("created_at", "unknown")

    lines: list[str] = []
    lines.append(f"# Gate Bypass: {bypass}")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| Schema | `{schema}` |")
    lines.append(f"| Bypass | `{bypass}` |")
    lines.append(f"| Branch | `{branch}` |")
    lines.append(f"| Commit | `{commit}` |")
    lines.append(f"| Source | `{source}` |")
    lines.append(f"| Created | `{created_at}` |")

    waiver = data.get("waiver")
    if waiver and isinstance(waiver, dict):
        reason_code = waiver.get("reason_code", "")
        reason_summary = waiver.get("reason_summary", "")
        detail = waiver.get("detail", "")
        owner = waiver.get("owner", "")
        expires_on = waiver.get("expires_on", "")
        remediation_ref = waiver.get("remediation_ref", "")
        impacted_lanes = waiver.get("impacted_lanes", [])
        substitute_evidence = waiver.get("substitute_evidence", [])

        lines.append(f"| Reason Code | `{reason_code}` |")
        lines.append(f"| Owner | `{owner}` |")
        lines.append(f"| Expires | `{expires_on}` |")
        lines.append(f"| Remediation | `{remediation_ref}` |")
        lines.append("")
        lines.append("## Reason")
        lines.append("")
        lines.append(f"**{reason_summary}**")
        lines.append("")
        if detail:
            lines.append(f"{detail}")
            lines.append("")
        if impacted_lanes:
            lines.append("## Impacted Lanes")
            lines.append("")
            for lane in impacted_lanes:
                lines.append(f"- `{lane}`")
            lines.append("")
        if substitute_evidence:
            lines.append("## Substitute Evidence")
            lines.append("")
            for ev in substitute_evidence:
                lines.append(f"- `{ev}`")
            lines.append("")
    else:
        reason = data.get("reason", "")
        if reason:
            lines.append("")
            lines.append("## Reason")
            lines.append("")
            lines.append(reason)
            lines.append("")

    if filename:
        lines.append("")
        lines.append(f"*Receipt file: `{filename}`*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _ok(data: dict[str, Any]) -> None:
    print(json.dumps({"ok": True, **data}, indent=2))


def _err(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}), file=sys.stderr)


# ---------------------------------------------------------------------------
# Client bootstrap
# ---------------------------------------------------------------------------


def _client(args: argparse.Namespace) -> OutlineClient:
    token: str | None = getattr(args, "token", None) or os.environ.get("OUTLINE_API_TOKEN")
    if not token:
        token_file: Path = getattr(args, "token_file", DEFAULT_TOKEN_FILE)
        token = load_api_token(token_file)
    return OutlineClient(args.base_url, api_token=token)


# ---------------------------------------------------------------------------
# Collection commands
# ---------------------------------------------------------------------------


def cmd_collection_list(client: OutlineClient, _args: argparse.Namespace) -> None:
    by_name = collections_by_name(client)
    _ok(
        {
            "collections": [
                {
                    "id": v["id"],
                    "name": v["name"],
                    "description": v.get("description", ""),
                    "url": v.get("url", ""),
                }
                for v in by_name.values()
            ]
        }
    )


def cmd_collection_create(client: OutlineClient, args: argparse.Namespace) -> None:
    by_name = collections_by_name(client)
    if args.name in by_name:
        existing = by_name[args.name]
        _ok({"id": existing["id"], "name": existing["name"], "outcome": "exists"})
        return
    response = client.call(
        "collections.create",
        {
            "name": args.name,
            "description": getattr(args, "description", "") or "",
            "permission": "read",
            "sharing": True,
        },
    )
    data = response.get("data", {})
    _ok({"id": data.get("id", ""), "name": data.get("name", args.name), "outcome": "created"})


def cmd_collection_delete(client: OutlineClient, args: argparse.Namespace) -> None:
    by_name = collections_by_name(client)
    if args.name not in by_name:
        raise OutlineError(f"collection not found: {args.name}")
    collection_id = by_name[args.name]["id"]
    client.call("collections.delete", {"id": collection_id})
    _ok({"deleted": True, "name": args.name})


# ---------------------------------------------------------------------------
# Document commands
# ---------------------------------------------------------------------------


def _require_collection(client: OutlineClient, name: str) -> str:
    by_name = collections_by_name(client)
    if name not in by_name:
        raise OutlineError(f"collection not found: {name}")
    return by_name[name]["id"]


def _read_content(args: argparse.Namespace) -> str:
    file_path: str | None = getattr(args, "file", None)
    use_stdin: bool = getattr(args, "stdin", False)
    if file_path:
        return Path(file_path).read_text(encoding="utf-8")
    if use_stdin:
        return sys.stdin.read()
    raise OutlineError("no content provided: use --file PATH or --stdin")


def cmd_document_list(client: OutlineClient, args: argparse.Namespace) -> None:
    collection_id = _require_collection(client, args.collection)
    docs = documents_in_collection(client, collection_id)
    _ok(
        {
            "collection": args.collection,
            "documents": [
                {
                    "id": d["id"],
                    "title": d.get("title", ""),
                    "url": d.get("url", ""),
                }
                for d in docs
            ],
        }
    )


def cmd_document_publish(client: OutlineClient, args: argparse.Namespace) -> None:
    content = _read_content(args)
    if getattr(args, "rewrite_links", False):
        content = _rewrite_links(content)
    collection_id = _require_collection(client, args.collection)

    parent_id: str | None = None
    parent_title: str | None = getattr(args, "parent", None)
    if parent_title:
        parent_docs = [d for d in documents_in_collection(client, collection_id) if d.get("title") == parent_title]
        if not parent_docs:
            raise OutlineError(f"parent document not found: {parent_title}")
        parent_id = parent_docs[0]["id"]

    matching = [d for d in documents_in_collection(client, collection_id) if d.get("title") == args.title]
    if matching:
        doc_id = matching[0]["id"]
        response = client.call(
            "documents.update",
            {"id": doc_id, "title": args.title, "text": content, "publish": True, "done": True},
        )
        doc = response.get("data", {})
        for dup in matching[1:]:
            client.call("documents.delete", {"id": dup["id"]})
        _ok(
            {
                "id": doc_id,
                "title": args.title,
                "collection": args.collection,
                "url": doc.get("url", ""),
                "outcome": "updated",
            }
        )
    else:
        payload: dict[str, Any] = {
            "collectionId": collection_id,
            "title": args.title,
            "text": content,
            "publish": True,
        }
        if parent_id:
            payload["parentDocumentId"] = parent_id
        response = client.call("documents.create", payload)
        doc = response.get("data", {})
        _ok(
            {
                "id": doc.get("id", ""),
                "title": args.title,
                "collection": args.collection,
                "url": doc.get("url", ""),
                "outcome": "created",
            }
        )


def cmd_document_get(client: OutlineClient, args: argparse.Namespace) -> None:
    collection_id = _require_collection(client, args.collection)
    docs = documents_in_collection(client, collection_id)
    matching = [d for d in docs if d.get("title") == args.title]
    if not matching:
        raise OutlineError(f"document not found: {args.title!r} in collection {args.collection!r}")
    doc_id = matching[0]["id"]
    response = client.call("documents.info", {"id": doc_id})
    doc = response.get("data", {})
    _ok(
        {
            "id": doc_id,
            "title": doc.get("title", ""),
            "text": doc.get("text", ""),
            "collection": args.collection,
            "url": doc.get("url", ""),
        }
    )


def cmd_document_delete(client: OutlineClient, args: argparse.Namespace) -> None:
    collection_id = _require_collection(client, args.collection)
    docs = documents_in_collection(client, collection_id)
    matching = [d for d in docs if d.get("title") == args.title]
    if not matching:
        raise OutlineError(f"document not found: {args.title!r} in collection {args.collection!r}")
    client.call("documents.delete", {"id": matching[0]["id"]})
    _ok({"deleted": True, "title": args.title, "collection": args.collection, "count": 1})


def cmd_document_search(client: OutlineClient, args: argparse.Namespace) -> None:
    payload: dict[str, Any] = {"query": args.query}
    collection_name: str | None = getattr(args, "collection", None)
    if collection_name:
        payload["collectionId"] = _require_collection(client, collection_name)
    response = client.call("documents.search", payload)
    results = response.get("data", [])
    _ok(
        {
            "query": args.query,
            "results": [
                {
                    "id": r.get("document", {}).get("id", ""),
                    "title": r.get("document", {}).get("title", ""),
                    "collection_id": r.get("document", {}).get("collectionId", ""),
                    "url": r.get("document", {}).get("url", ""),
                    "context": r.get("context", ""),
                }
                for r in results
            ],
        }
    )


# ---------------------------------------------------------------------------
# Generic receipt publisher
# ---------------------------------------------------------------------------

_RECEIPT_COLLECTIONS: dict[str, str] = {
    "cve": "Security & Compliance",
    "sbom": "Security & Compliance",
    "security-reports": "Security & Compliance",
    "security-scan": "Security & Compliance",
    "https-tls-assurance": "Security & Compliance",
    "subdomain-exposure-audit": "Security & Compliance",
    "image-scans": "Security & Compliance",
    "sast": "Security & Compliance",
    "checkov": "Security & Compliance",
    "restore-verifications": "DR & Backup Status",
    "restic-restore-verifications": "DR & Backup Status",
    "backup-coverage": "DR & Backup Status",
    "restic-backups": "DR & Backup Status",
    "dr-table-top-reviews": "DR & Backup Status",
    "dr-reports": "DR & Backup Status",
    "gate-bypasses": "Gate Bypass Waivers",
    "live-applies": "Automation Runs",
    "k6": "Automation Runs",
    "agent-coordination": "Automation Runs",
    "promotions": "Automation Runs",
    "preview-environments": "Automation Runs",
    "runtime-pool-scaling": "Automation Runs",
    "atlas-drift": "Platform Findings",
    "drift-reports": "Platform Findings",
    "token-lifecycle": "Platform Findings",
    "witness-replication": "Platform Findings",
}


def _receipt_json_to_markdown(data: dict[str, Any], filename: str = "") -> str:
    """Format any JSON receipt as readable markdown using its top-level keys."""
    schema = data.get("schema_version", "")
    generated_at = data.get("generated_at") or data.get("created_at") or data.get("timestamp") or ""
    environment = data.get("environment", "")
    status = data.get("status") or data.get("overall") or data.get("overall_status") or ""

    # Title row from filename or schema
    header = filename.replace(".json", "") if filename else "Receipt"
    lines = [f"# {header}", ""]

    # Metadata table
    meta_rows = [
        ("Schema", schema),
        ("Generated", generated_at),
        ("Environment", environment),
        ("Status", str(status)),
    ]
    meta_rows = [(k, v) for k, v in meta_rows if v]
    if meta_rows:
        lines += ["| Field | Value |", "|---|---|"]
        for k, v in meta_rows:
            lines.append(f"| {k} | `{v}` |")
        lines.append("")

    # Summary block
    summary = data.get("summary")
    if isinstance(summary, dict) and summary:
        lines += ["## Summary", "", "| Key | Value |", "|---|---|"]
        for k, v in summary.items():
            lines.append(f"| {k} | `{v}` |")
        lines.append("")

    # Findings
    findings = data.get("findings")
    if isinstance(findings, list) and findings:
        lines += [f"## Findings ({len(findings)})", ""]
        for f in findings[:20]:
            if isinstance(f, dict):
                sev = f.get("severity", "")
                msg = f.get("message") or f.get("summary") or f.get("check") or str(f)[:120]
                lines.append(f"- **[{sev}]** {msg}")
        if len(findings) > 20:
            lines.append(f"- *({len(findings) - 20} more findings — see full receipt)*")
        lines.append("")

    if filename:
        lines += ["", f"*Receipt file: `{filename}`*"]

    return "\n".join(lines)


def _infer_collection_from_path(receipt_path: Path) -> str:
    """Infer target Outline collection from the receipt directory name."""
    parent = receipt_path.parent.name
    return _RECEIPT_COLLECTIONS.get(parent, "Automation Runs")


def cmd_receipt_publish(client: OutlineClient, args: argparse.Namespace) -> None:
    receipt_path = Path(args.file)
    data = json.loads(receipt_path.read_text(encoding="utf-8"))
    collection_name = getattr(args, "collection", None) or _infer_collection_from_path(receipt_path)
    title = (getattr(args, "title", None) or receipt_path.stem)[:100]
    content = _receipt_json_to_markdown(data, filename=receipt_path.name)

    by_name = collections_by_name(client)
    if collection_name not in by_name:
        response = client.call(
            "collections.create",
            {
                "name": collection_name,
                "description": f"Automated outputs — {collection_name}.",
                "permission": "read",
                "sharing": True,
            },
        )
        collection_id = response["data"]["id"]
    else:
        collection_id = by_name[collection_name]["id"]

    matching = [d for d in documents_in_collection(client, collection_id) if d.get("title") == title]
    if matching:
        client.call(
            "documents.update",
            {"id": matching[0]["id"], "title": title, "text": content, "publish": True, "done": True},
        )
        _ok({"outcome": "updated", "title": title, "collection": collection_name})
    else:
        response = client.call(
            "documents.create", {"collectionId": collection_id, "title": title, "text": content, "publish": True}
        )
        doc = response.get("data", {})
        _ok({"outcome": "created", "title": title, "collection": collection_name, "url": doc.get("url", "")})


def cmd_receipt_backfill(client: OutlineClient, args: argparse.Namespace) -> None:
    import time

    receipt_dir = Path(args.receipt_dir)
    collection_name = getattr(args, "collection", None) or _infer_collection_from_path(receipt_dir / "dummy.json")
    receipts = sorted(receipt_dir.glob("*.json"))
    if not receipts:
        _ok({"backfilled": 0, "message": f"no receipts found in {receipt_dir}"})
        return

    by_name = collections_by_name(client)
    if collection_name not in by_name:
        response = client.call(
            "collections.create",
            {
                "name": collection_name,
                "description": f"Automated outputs — {collection_name}.",
                "permission": "read",
                "sharing": True,
            },
        )
        collection_id = response["data"]["id"]
    else:
        collection_id = by_name[collection_name]["id"]

    existing_titles = {d.get("title") for d in documents_in_collection(client, collection_id)}
    created = updated = skipped = 0
    results: list[dict[str, Any]] = []
    for receipt_path in receipts:
        title = receipt_path.stem[:100]
        try:
            data = json.loads(receipt_path.read_text(encoding="utf-8"))
        except Exception as exc:
            results.append({"title": title, "outcome": "error", "error": str(exc)})
            continue
        content = _receipt_json_to_markdown(data, filename=receipt_path.name)
        if title in existing_titles:
            if getattr(args, "force", False):
                matching = [d for d in documents_in_collection(client, collection_id) if d.get("title") == title]
                if matching:
                    client.call(
                        "documents.update",
                        {"id": matching[0]["id"], "title": title, "text": content, "publish": True, "done": True},
                    )
                    updated += 1
                    results.append({"title": title, "outcome": "updated"})
                    time.sleep(0.4)
            else:
                skipped += 1
                results.append({"title": title, "outcome": "skipped"})
        else:
            response = client.call(
                "documents.create", {"collectionId": collection_id, "title": title, "text": content, "publish": True}
            )
            doc = response.get("data", {})
            existing_titles.add(title)
            created += 1
            results.append({"title": title, "outcome": "created", "url": doc.get("url", "")})
            time.sleep(0.4)
    _ok(
        {
            "backfilled": created + updated,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "collection": collection_name,
            "results": results,
        }
    )


# ---------------------------------------------------------------------------
# Bypass receipt commands
# ---------------------------------------------------------------------------


def _ensure_bypass_collection(client: OutlineClient) -> str:
    by_name = collections_by_name(client)
    if _DEFAULT_BYPASS_COLLECTION not in by_name:
        response = client.call(
            "collections.create",
            {
                "name": _DEFAULT_BYPASS_COLLECTION,
                "description": "Gate bypass waiver receipts — every validation bypass recorded by log_gate_bypass.py.",
                "permission": "read",
                "sharing": True,
            },
        )
        return response["data"]["id"]
    return by_name[_DEFAULT_BYPASS_COLLECTION]["id"]


def cmd_bypass_publish(client: OutlineClient, args: argparse.Namespace) -> None:
    receipt_path = Path(args.file)
    data = json.loads(receipt_path.read_text(encoding="utf-8"))
    title = receipt_path.stem  # filename without .json
    content = _receipt_to_markdown(data, filename=receipt_path.name)
    collection_id = _ensure_bypass_collection(client)
    matching = [d for d in documents_in_collection(client, collection_id) if d.get("title") == title]
    if matching:
        doc_id = matching[0]["id"]
        client.call("documents.update", {"id": doc_id, "title": title, "text": content, "publish": True, "done": True})
        _ok({"outcome": "updated", "title": title, "collection": _DEFAULT_BYPASS_COLLECTION})
    else:
        response = client.call(
            "documents.create",
            {
                "collectionId": collection_id,
                "title": title,
                "text": content,
                "publish": True,
            },
        )
        doc = response.get("data", {})
        _ok({"outcome": "created", "title": title, "collection": _DEFAULT_BYPASS_COLLECTION, "url": doc.get("url", "")})


def cmd_bypass_backfill(client: OutlineClient, args: argparse.Namespace) -> None:
    import time

    receipt_dir = Path(getattr(args, "receipt_dir", "receipts/gate-bypasses"))
    receipts = sorted(receipt_dir.glob("*.json"))
    if not receipts:
        _ok({"backfilled": 0, "message": f"no receipts found in {receipt_dir}"})
        return
    collection_id = _ensure_bypass_collection(client)
    existing_titles = {d.get("title") for d in documents_in_collection(client, collection_id)}
    created = updated = skipped = 0
    results: list[dict[str, Any]] = []
    for receipt_path in receipts:
        title = receipt_path.stem
        try:
            data = json.loads(receipt_path.read_text(encoding="utf-8"))
        except Exception as exc:
            results.append({"title": title, "outcome": "error", "error": str(exc)})
            continue
        content = _receipt_to_markdown(data, filename=receipt_path.name)
        if title in existing_titles:
            if getattr(args, "force", False):
                matching = [d for d in documents_in_collection(client, collection_id) if d.get("title") == title]
                if matching:
                    client.call(
                        "documents.update",
                        {"id": matching[0]["id"], "title": title, "text": content, "publish": True, "done": True},
                    )
                    updated += 1
                    results.append({"title": title, "outcome": "updated"})
                    time.sleep(0.4)
            else:
                skipped += 1
                results.append({"title": title, "outcome": "skipped"})
        else:
            response = client.call(
                "documents.create",
                {
                    "collectionId": collection_id,
                    "title": title,
                    "text": content,
                    "publish": True,
                },
            )
            doc = response.get("data", {})
            existing_titles.add(title)
            created += 1
            results.append({"title": title, "outcome": "created", "url": doc.get("url", "")})
            time.sleep(0.4)
    _ok(
        {
            "backfilled": created + updated,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "collection": _DEFAULT_BYPASS_COLLECTION,
            "results": results,
        }
    )


# ---------------------------------------------------------------------------
# CI publish
# ---------------------------------------------------------------------------


def cmd_ci_publish(client: OutlineClient, args: argparse.Namespace) -> None:
    """Publish a CI validation summary to Outline. Used by CI/CD pipelines."""
    import json as _json

    lines = [
        f"# CI Validation: {args.title}",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Branch | {args.branch} |",
        f"| Commit | {args.sha} |",
        f"| Status | {args.status} |",
        f"| Run date | {args.date} |",
        "",
    ]
    gate_json = getattr(args, "gate_json", None)
    if gate_json and Path(gate_json).exists():
        try:
            data = _json.loads(Path(gate_json).read_text(encoding="utf-8"))
            lanes = data.get("lanes", {})
            if isinstance(lanes, dict) and lanes:
                lines += ["## Gate Lanes", "", "| Lane | Result |", "|---|---|"]
                for lane, info in sorted(lanes.items()):
                    icon = "passed" if (isinstance(info, dict) and info.get("passed")) else "failed"
                    lines.append(f"| {lane} | {icon} |")
                lines.append("")
        except (OSError, ValueError):
            pass
    content = "\n".join(lines)
    collection_id = client.find_collection_id(args.collection)
    existing = client.documents_in_collection(collection_id)
    title = args.title[:100]
    match = next((d for d in existing if d.get("title") == title), None)
    if match:
        result = client.call("documents.update", {"id": match["id"], "title": title, "text": content, "done": True})
        outcome = "updated"
    else:
        result = client.call(
            "documents.create",
            {
                "collectionId": collection_id,
                "title": title,
                "text": content,
                "publish": True,
            },
        )
        outcome = "created"
    doc = result.get("data", {})
    print(_json.dumps({"outcome": outcome, "title": title, "url": doc.get("url", "")}, indent=2))


# ---------------------------------------------------------------------------
# Changelog push
# ---------------------------------------------------------------------------


def cmd_changelog_push(client: OutlineClient, args: argparse.Namespace) -> None:
    file_path: str | None = getattr(args, "file", None)
    if file_path:
        content = Path(file_path).read_text(encoding="utf-8")
    else:
        default_changelog = Path(__file__).resolve().parents[1] / "changelog.md"
        if not default_changelog.exists():
            raise OutlineError(f"changelog.md not found at {default_changelog}; pass --file PATH to specify one")
        content = default_changelog.read_text(encoding="utf-8")

    content = _rewrite_links(content)
    title: str = getattr(args, "title", None) or "Changelog"
    collection_name = _DEFAULT_CHANGELOG_COLLECTION

    by_name = collections_by_name(client)
    if collection_name not in by_name:
        response = client.call(
            "collections.create",
            {
                "name": collection_name,
                "description": "Release notes, version history, and automated changelog entries for the LV3 platform.",
                "permission": "read",
                "sharing": True,
            },
        )
        collection_id = response["data"]["id"]
    else:
        collection_id = by_name[collection_name]["id"]

    matching = [d for d in documents_in_collection(client, collection_id) if d.get("title") == title]
    if matching:
        doc_id = matching[0]["id"]
        client.call(
            "documents.update",
            {"id": doc_id, "title": title, "text": content, "publish": True, "done": True},
        )
        for dup in matching[1:]:
            client.call("documents.delete", {"id": dup["id"]})
        _ok({"outcome": "updated", "title": title, "collection": collection_name})
    else:
        response = client.call(
            "documents.create",
            {"collectionId": collection_id, "title": title, "text": content, "publish": True},
        )
        doc = response.get("data", {})
        _ok(
            {
                "outcome": "created",
                "title": title,
                "collection": collection_name,
                "url": doc.get("url", ""),
            }
        )


# ---------------------------------------------------------------------------
# User management helpers
# ---------------------------------------------------------------------------


def _users_by_email(client: OutlineClient) -> dict[str, dict[str, Any]]:
    response = client.call("users.list", {})
    return {u["email"]: u for u in response.get("data", []) if u.get("email")}


def _users_by_name(client: OutlineClient) -> dict[str, dict[str, Any]]:
    response = client.call("users.list", {})
    return {u["name"]: u for u in response.get("data", [])}


def _resolve_user(client: OutlineClient, identifier: str) -> dict[str, Any]:
    """Resolve a user by email or display name."""
    by_email = _users_by_email(client)
    if identifier in by_email:
        return by_email[identifier]
    by_name = _users_by_name(client)
    if identifier in by_name:
        return by_name[identifier]
    raise OutlineError(f"user not found: {identifier!r} — pass email address or exact display name")


def _groups_by_name(client: OutlineClient) -> dict[str, dict[str, Any]]:
    response = client.call("groups.list", {})
    return {g["name"]: g for g in response.get("data", [])}


# ---------------------------------------------------------------------------
# User commands
# ---------------------------------------------------------------------------


def cmd_user_list(client: OutlineClient, _args: argparse.Namespace) -> None:
    response = client.call("users.list", {})
    users = response.get("data", [])
    _ok(
        {
            "users": [
                {
                    "id": u["id"],
                    "name": u.get("name", ""),
                    "email": u.get("email", ""),
                    "role": u.get("role", ""),
                    "isActive": u.get("isSuspended") is False,
                }
                for u in users
            ]
        }
    )


# ---------------------------------------------------------------------------
# Collection membership commands
# ---------------------------------------------------------------------------


def cmd_collection_members(client: OutlineClient, args: argparse.Namespace) -> None:
    collection_id = _require_collection(client, args.collection)
    response = client.call("collections.memberships", {"id": collection_id})
    memberships = response.get("data", {})
    users = memberships.get("users", [])
    groups = memberships.get("groups", [])
    _ok(
        {
            "collection": args.collection,
            "users": [
                {
                    "id": u["id"],
                    "name": u.get("name", ""),
                    "email": u.get("email", ""),
                    "permission": u.get("permission", ""),
                }
                for u in users
            ],
            "groups": [
                {"id": g["id"], "name": g.get("name", ""), "permission": g.get("permission", "")} for g in groups
            ],
        }
    )


def cmd_collection_grant(client: OutlineClient, args: argparse.Namespace) -> None:
    collection_id = _require_collection(client, args.collection)
    user = _resolve_user(client, args.user)
    permission = args.permission  # "read" or "read_write"
    client.call(
        "collections.addUser",
        {"id": collection_id, "userId": user["id"], "permission": permission},
    )
    _ok(
        {
            "granted": True,
            "collection": args.collection,
            "user": user.get("email", user.get("name", "")),
            "permission": permission,
        }
    )


def cmd_collection_revoke(client: OutlineClient, args: argparse.Namespace) -> None:
    collection_id = _require_collection(client, args.collection)
    user = _resolve_user(client, args.user)
    client.call("collections.removeUser", {"id": collection_id, "userId": user["id"]})
    _ok(
        {
            "revoked": True,
            "collection": args.collection,
            "user": user.get("email", user.get("name", "")),
        }
    )


def cmd_collection_grant_group(client: OutlineClient, args: argparse.Namespace) -> None:
    collection_id = _require_collection(client, args.collection)
    groups = _groups_by_name(client)
    if args.group not in groups:
        raise OutlineError(f"group not found: {args.group!r}")
    group = groups[args.group]
    permission = args.permission
    client.call(
        "collections.addGroup",
        {"id": collection_id, "groupId": group["id"], "permission": permission},
    )
    _ok(
        {
            "granted": True,
            "collection": args.collection,
            "group": args.group,
            "permission": permission,
        }
    )


def cmd_collection_revoke_group(client: OutlineClient, args: argparse.Namespace) -> None:
    collection_id = _require_collection(client, args.collection)
    groups = _groups_by_name(client)
    if args.group not in groups:
        raise OutlineError(f"group not found: {args.group!r}")
    group = groups[args.group]
    client.call("collections.removeGroup", {"id": collection_id, "groupId": group["id"]})
    _ok({"revoked": True, "collection": args.collection, "group": args.group})


# ---------------------------------------------------------------------------
# Group commands
# ---------------------------------------------------------------------------


def cmd_group_list(client: OutlineClient, _args: argparse.Namespace) -> None:
    response = client.call("groups.list", {})
    groups = response.get("data", [])
    _ok(
        {"groups": [{"id": g["id"], "name": g.get("name", ""), "memberCount": g.get("memberCount", 0)} for g in groups]}
    )


def cmd_group_create(client: OutlineClient, args: argparse.Namespace) -> None:
    groups = _groups_by_name(client)
    if args.name in groups:
        existing = groups[args.name]
        _ok({"id": existing["id"], "name": existing["name"], "outcome": "exists"})
        return
    response = client.call("groups.create", {"name": args.name})
    group = response.get("data", {})
    _ok({"id": group.get("id", ""), "name": group.get("name", args.name), "outcome": "created"})


def cmd_group_delete(client: OutlineClient, args: argparse.Namespace) -> None:
    groups = _groups_by_name(client)
    if args.name not in groups:
        raise OutlineError(f"group not found: {args.name!r}")
    client.call("groups.delete", {"id": groups[args.name]["id"]})
    _ok({"deleted": True, "name": args.name})


def cmd_group_members(client: OutlineClient, args: argparse.Namespace) -> None:
    groups = _groups_by_name(client)
    if args.group not in groups:
        raise OutlineError(f"group not found: {args.group!r}")
    group_id = groups[args.group]["id"]
    response = client.call("groups.memberships", {"id": group_id})
    users = response.get("data", {}).get("users", [])
    _ok(
        {
            "group": args.group,
            "members": [{"id": u["id"], "name": u.get("name", ""), "email": u.get("email", "")} for u in users],
        }
    )


def cmd_group_add_user(client: OutlineClient, args: argparse.Namespace) -> None:
    groups = _groups_by_name(client)
    if args.group not in groups:
        raise OutlineError(f"group not found: {args.group!r}")
    user = _resolve_user(client, args.user)
    client.call("groups.addUser", {"id": groups[args.group]["id"], "userId": user["id"]})
    _ok(
        {
            "added": True,
            "group": args.group,
            "user": user.get("email", user.get("name", "")),
        }
    )


def cmd_group_remove_user(client: OutlineClient, args: argparse.Namespace) -> None:
    groups = _groups_by_name(client)
    if args.group not in groups:
        raise OutlineError(f"group not found: {args.group!r}")
    user = _resolve_user(client, args.user)
    client.call("groups.removeUser", {"id": groups[args.group]["id"], "userId": user["id"]})
    _ok(
        {
            "removed": True,
            "group": args.group,
            "user": user.get("email", user.get("name", "")),
        }
    )


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _add_auth_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Outline base URL")
    parser.add_argument(
        "--token-file",
        type=Path,
        default=DEFAULT_TOKEN_FILE,
        help="Path to file containing the Outline API token (overridden by OUTLINE_API_TOKEN env var)",
    )
    parser.add_argument("--token", default=None, help="API token (overrides --token-file and env var)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Programmatic Outline wiki tool for LLM agents and automation scripts."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # collection.list
    p = sub.add_parser("collection.list", help="List all collections.")
    _add_auth_args(p)

    # collection.create
    p = sub.add_parser("collection.create", help="Create a collection (idempotent).")
    _add_auth_args(p)
    p.add_argument("--name", required=True, help="Collection name")
    p.add_argument("--description", default="", help="Collection description")

    # collection.delete
    p = sub.add_parser("collection.delete", help="Delete a collection by name.")
    _add_auth_args(p)
    p.add_argument("--name", required=True, help="Collection name")

    # document.list
    p = sub.add_parser("document.list", help="List documents in a collection.")
    _add_auth_args(p)
    p.add_argument("--collection", required=True, help="Collection name")

    # document.publish
    p = sub.add_parser("document.publish", help="Create or update a document (idempotent by title).")
    _add_auth_args(p)
    p.add_argument("--collection", required=True, help="Target collection name")
    p.add_argument("--title", required=True, help="Document title")
    p.add_argument("--parent", default=None, help="Parent document title (optional)")
    content_group = p.add_mutually_exclusive_group(required=True)
    content_group.add_argument("--file", metavar="PATH", help="Read content from this file")
    content_group.add_argument("--stdin", action="store_true", help="Read content from stdin")
    p.add_argument(
        "--rewrite-links", action="store_true", help="Rewrite relative markdown links to absolute GitHub URLs"
    )

    # document.get
    p = sub.add_parser("document.get", help="Retrieve a document's full text.")
    _add_auth_args(p)
    p.add_argument("--collection", required=True, help="Collection name")
    p.add_argument("--title", required=True, help="Document title")

    # document.delete
    p = sub.add_parser("document.delete", help="Delete a document by title.")
    _add_auth_args(p)
    p.add_argument("--collection", required=True, help="Collection name")
    p.add_argument("--title", required=True, help="Document title")

    # document.search
    p = sub.add_parser("document.search", help="Full-text search across the wiki.")
    _add_auth_args(p)
    p.add_argument("--query", required=True, help="Search query")
    p.add_argument("--collection", default=None, help="Restrict search to this collection (optional)")

    # receipt.publish
    p = sub.add_parser("receipt.publish", help="Publish any JSON receipt file to the appropriate collection.")
    _add_auth_args(p)
    p.add_argument("--file", required=True, metavar="PATH", help="Path to the receipt .json file")
    p.add_argument("--collection", default=None, help="Target collection (auto-detected from receipt path if omitted)")
    p.add_argument("--title", default=None, help="Document title (defaults to filename stem)")

    # receipt.backfill
    p = sub.add_parser(
        "receipt.backfill", help="Upload all JSON receipts from a directory to the appropriate collection."
    )
    _add_auth_args(p)
    p.add_argument("--receipt-dir", required=True, metavar="DIR", help="Directory containing receipt JSON files")
    p.add_argument("--collection", default=None, help="Target collection (auto-detected from dir name if omitted)")
    p.add_argument("--force", action="store_true", help="Re-upload receipts that already exist in the wiki")

    # bypass.publish
    p = sub.add_parser(
        "bypass.publish", help=f"Publish one bypass receipt JSON to the '{_DEFAULT_BYPASS_COLLECTION}' collection."
    )
    _add_auth_args(p)
    p.add_argument("--file", required=True, metavar="PATH", help="Path to the receipt .json file")

    # bypass.backfill
    p = sub.add_parser(
        "bypass.backfill", help=f"Upload all bypass receipts to the '{_DEFAULT_BYPASS_COLLECTION}' collection."
    )
    _add_auth_args(p)
    p.add_argument(
        "--receipt-dir", default="receipts/gate-bypasses", metavar="DIR", help="Directory containing receipt JSON files"
    )
    p.add_argument("--force", action="store_true", help="Re-upload receipts that already exist in the wiki")

    # ci.publish
    p = sub.add_parser("ci.publish", help="Publish a CI validation summary to a collection.")
    _add_auth_args(p)
    p.add_argument("--collection", required=True, help="Target collection name")
    p.add_argument("--title", required=True, help="Document title")
    p.add_argument("--status", default="unknown", help="CI run status (success|failure)")
    p.add_argument("--branch", default="unknown", help="Git branch name")
    p.add_argument("--sha", default="unknown", help="Full commit SHA")
    p.add_argument("--date", default="", help="Run timestamp (ISO 8601)")
    p.add_argument("--gate-json", default=None, metavar="PATH", help="Path to gate JSON file for lane details")

    # changelog.push
    p = sub.add_parser("changelog.push", help=f"Push changelog to the '{_DEFAULT_CHANGELOG_COLLECTION}' collection.")
    _add_auth_args(p)
    p.add_argument("--file", metavar="PATH", default=None, help="Changelog file (default: changelog.md in repo root)")
    p.add_argument("--title", default="Changelog", help="Document title in wiki (default: Changelog)")

    # user.list
    p = sub.add_parser("user.list", help="List all workspace users (requires users.list scope).")
    _add_auth_args(p)

    # collection.members
    p = sub.add_parser("collection.members", help="List users and groups with access to a collection.")
    _add_auth_args(p)
    p.add_argument("--collection", required=True, help="Collection name")

    # collection.grant
    p = sub.add_parser("collection.grant", help="Grant a user access to a collection.")
    _add_auth_args(p)
    p.add_argument("--collection", required=True, help="Collection name")
    p.add_argument("--user", required=True, metavar="EMAIL_OR_NAME", help="User email or display name")
    p.add_argument(
        "--permission", default="read", choices=["read", "read_write"], help="Permission level (default: read)"
    )

    # collection.revoke
    p = sub.add_parser("collection.revoke", help="Revoke a user's access to a collection.")
    _add_auth_args(p)
    p.add_argument("--collection", required=True, help="Collection name")
    p.add_argument("--user", required=True, metavar="EMAIL_OR_NAME", help="User email or display name")

    # collection.grant-group
    p = sub.add_parser("collection.grant-group", help="Grant a group access to a collection.")
    _add_auth_args(p)
    p.add_argument("--collection", required=True, help="Collection name")
    p.add_argument("--group", required=True, help="Group name")
    p.add_argument(
        "--permission", default="read", choices=["read", "read_write"], help="Permission level (default: read)"
    )

    # collection.revoke-group
    p = sub.add_parser("collection.revoke-group", help="Revoke a group's access to a collection.")
    _add_auth_args(p)
    p.add_argument("--collection", required=True, help="Collection name")
    p.add_argument("--group", required=True, help="Group name")

    # group.list
    p = sub.add_parser("group.list", help="List all workspace groups.")
    _add_auth_args(p)

    # group.create
    p = sub.add_parser("group.create", help="Create a group (idempotent).")
    _add_auth_args(p)
    p.add_argument("--name", required=True, help="Group name")

    # group.delete
    p = sub.add_parser("group.delete", help="Delete a group by name.")
    _add_auth_args(p)
    p.add_argument("--name", required=True, help="Group name")

    # group.members
    p = sub.add_parser("group.members", help="List members of a group.")
    _add_auth_args(p)
    p.add_argument("--group", required=True, help="Group name")

    # group.add-user
    p = sub.add_parser("group.add-user", help="Add a user to a group.")
    _add_auth_args(p)
    p.add_argument("--group", required=True, help="Group name")
    p.add_argument("--user", required=True, metavar="EMAIL_OR_NAME", help="User email or display name")

    # group.remove-user
    p = sub.add_parser("group.remove-user", help="Remove a user from a group.")
    _add_auth_args(p)
    p.add_argument("--group", required=True, help="Group name")
    p.add_argument("--user", required=True, metavar="EMAIL_OR_NAME", help="User email or display name")

    return parser


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_COMMANDS = {
    "collection.list": cmd_collection_list,
    "collection.create": cmd_collection_create,
    "collection.delete": cmd_collection_delete,
    "collection.members": cmd_collection_members,
    "collection.grant": cmd_collection_grant,
    "collection.revoke": cmd_collection_revoke,
    "collection.grant-group": cmd_collection_grant_group,
    "collection.revoke-group": cmd_collection_revoke_group,
    "document.list": cmd_document_list,
    "document.publish": cmd_document_publish,
    "document.get": cmd_document_get,
    "document.delete": cmd_document_delete,
    "document.search": cmd_document_search,
    "receipt.publish": cmd_receipt_publish,
    "receipt.backfill": cmd_receipt_backfill,
    "bypass.publish": cmd_bypass_publish,
    "bypass.backfill": cmd_bypass_backfill,
    "ci.publish": cmd_ci_publish,
    "changelog.push": cmd_changelog_push,
    "user.list": cmd_user_list,
    "group.list": cmd_group_list,
    "group.create": cmd_group_create,
    "group.delete": cmd_group_delete,
    "group.members": cmd_group_members,
    "group.add-user": cmd_group_add_user,
    "group.remove-user": cmd_group_remove_user,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        client = _client(args)
        _COMMANDS[args.command](client, args)
        return 0
    except OutlineError as exc:
        _err(str(exc))
        return 1
    except Exception as exc:
        _err(f"unexpected error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
