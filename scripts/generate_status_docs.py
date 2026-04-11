#!/usr/bin/env python3

import argparse
import json
import re
import sys
from pathlib import Path

from api_publication import ALLOWED_PUBLICATION_TIERS, load_api_publication_catalog
from control_plane_lanes import ALLOWED_LANE_IDS, load_lane_catalog
from controller_automation_toolkit import README_PATH, emit_cli_error, load_yaml, repo_path
from platform.root_summary import (
    collect_live_apply_evidence_records,
    collect_merged_workstream_records,
    enforce_line_budget,
    load_root_summary_budgets,
    relative_markdown_link,
)
from platform.workstream_registry import load_workstreams
from platform.repo import TOPOLOGY_HOST_VARS_PATH


REPO_ROOT = repo_path()
STACK_PATH = repo_path("versions", "stack.yaml")
WORKSTREAMS_PATH = repo_path("workstreams.yaml")
RUNBOOKS_DIR = repo_path("docs", "runbooks")
ADR_DIR = repo_path("docs", "adr")
WORKSTREAM_DOCS_DIR = repo_path("docs", "workstreams")

GENERATED_NOTICE = (
    "> Generated from canonical repository state by "
    "[`scripts/generate_status_docs.py`]"
    "(scripts/generate_status_docs.py). "
    "Do not edit this block by hand."
)
MARKERS = {
    "platform-status": "platform-status",
    "control-plane-lanes": "control-plane-lanes",
    "document-index": "document-index",
    "version-summary": "version-summary",
    "merged-workstreams": "merged-workstreams",
}
CORE_DOCUMENTS = [
    ("Changelog", REPO_ROOT / "changelog.md"),
    ("Release notes", REPO_ROOT / "docs" / "release-notes" / "README.md"),
    ("Repository map", REPO_ROOT / "docs" / "repository-map.md"),
    ("Assistant operator guide", REPO_ROOT / "docs" / "assistant-operator-guide.md"),
    ("Release process", REPO_ROOT / "docs" / "release-process.md"),
    ("Workstreams registry", REPO_ROOT / "workstreams.yaml"),
    ("Workstreams guide", REPO_ROOT / "docs" / "workstreams" / "README.md"),
]


def read_heading(path: Path) -> str:
    for line in path.read_text().splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def repo_relative_link(label: str, path: Path) -> str:
    resolved_path = path if path.is_absolute() else REPO_ROOT / path
    relative = resolved_path.relative_to(REPO_ROOT).as_posix()
    return f"[{label}]({relative})"


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def render_platform_status() -> str:
    budgets = load_root_summary_budgets()
    stack = load_yaml(STACK_PATH)
    host_vars = load_yaml(TOPOLOGY_HOST_VARS_PATH)

    version_rows = [
        ["Repository version", f"`{stack['repo_version']}`"],
        ["Platform version", f"`{stack['platform_version']}`"],
        ["Observed check date", f"`{stack['observed_state']['checked_at']}`"],
        ["Observed OS", f"`Debian {stack['observed_state']['os']['major']}`"],
        ["Observed Proxmox version", f"`{stack['observed_state']['proxmox']['version']}`"],
        ["Observed kernel", f"`{stack['observed_state']['os']['kernel']}`"],
    ]

    topology = host_vars["lv3_service_topology"]
    exposure_counts: dict[str, int] = {}
    for service in topology.values():
        exposure_model = service.get("exposure_model", "unknown")
        exposure_counts[exposure_model] = exposure_counts.get(exposure_model, 0) + 1

    topology_rows = [
        ["Managed guest count", str(len(stack["observed_state"]["guests"]["instances"]))],
        [
            "Running guest count",
            str(sum(1 for guest in stack["observed_state"]["guests"]["instances"] if guest["running"])),
        ],
        ["Template VM present", "`true`" if stack["observed_state"]["guests"]["template"]["vmid"] else "`false`"],
        ["Declared services", str(len(topology))],
        ["Publicly published services", str(sum(1 for service in topology.values() if service.get("public_hostname")))],
    ]

    exposure_rows = [[f"`{model}`", str(count)] for model, count in sorted(exposure_counts.items())]

    receipt_records = collect_live_apply_evidence_records(stack["live_apply_evidence"]["latest_receipts"])
    recent_receipts = receipt_records[: budgets.readme.recent_live_apply_entries]
    receipt_rows = [[f"`{record.capability}`", f"`{record.receipt_id}`"] for record in recent_receipts]

    parts = [
        GENERATED_NOTICE,
        "",
        "### Current Values",
        render_table(["Field", "Value"], version_rows),
        "",
        "### Topology Summary",
        render_table(["Field", "Value"], topology_rows),
        "",
        "### Service Exposure Summary",
        render_table(["Exposure Model", "Services"], exposure_rows),
        "",
        "### Latest Live-Apply Evidence",
        render_table(["Capability", "Receipt"], receipt_rows),
        "",
        (
            f"Showing {len(recent_receipts)} of {len(receipt_records)} capability receipts. "
            f"Full history: {relative_markdown_link('live-apply evidence history', from_path=README_PATH, target_path=REPO_ROOT / budgets.readme.live_apply_history_path)}"
        ),
    ]
    return "\n".join(parts).strip()


def render_control_plane_lanes() -> str:
    _catalog, normalized_lanes = load_lane_catalog()
    _publication_catalog, normalized_tiers, normalized_surfaces = load_api_publication_catalog()
    lane_rows = []
    tier_rows = []
    for lane_id in ALLOWED_LANE_IDS:
        lane = normalized_lanes[lane_id]
        lane_rows.append(
            [
                f"`{lane_id}`",
                lane["title"],
                f"`{lane['transport']}`",
                str(len(lane["current_surfaces"])),
                lane["steady_state_rules"][0],
            ]
        )

    for tier_id in ALLOWED_PUBLICATION_TIERS:
        tier = normalized_tiers[tier_id]
        tier_rows.append(
            [
                f"`{tier_id}`",
                tier["title"],
                str(sum(1 for surface in normalized_surfaces if surface["publication_tier"] == tier_id)),
                tier["summary"],
            ]
        )

    return "\n".join(
        [
            GENERATED_NOTICE,
            "",
            "### Lane Summary",
            render_table(["Lane", "Title", "Transport", "Surfaces", "Primary Rule"], lane_rows),
            "",
            "### API Publication Tiers",
            render_table(["Tier", "Title", "Surfaces", "Summary"], tier_rows),
        ]
    ).strip()


def render_document_links(paths: list[Path]) -> list[str]:
    return [f"- {repo_relative_link(read_heading(path), path)}" for path in paths]


def render_document_index() -> str:
    parts = [
        GENERATED_NOTICE,
        "",
        "### Core Documents",
        *[f"- {repo_relative_link(label, path)}" for label, path in CORE_DOCUMENTS],
        "",
        "### Discovery Indexes",
        f"- {repo_relative_link('ADR index', ADR_DIR / '.index.yaml')}",
        f"- {repo_relative_link('Runbooks directory', RUNBOOKS_DIR)}",
        f"- {repo_relative_link('Workstreams directory', WORKSTREAM_DOCS_DIR)}",
        f"- {repo_relative_link('Release notes index', REPO_ROOT / 'docs' / 'release-notes' / 'README.md')}",
        f"- {repo_relative_link('Generated docs directory', REPO_ROOT / 'docs' / 'site-generated')}",
    ]
    return "\n".join(parts).strip()


def render_version_summary() -> str:
    stack = load_yaml(STACK_PATH)
    host_vars = load_yaml(TOPOLOGY_HOST_VARS_PATH)
    version_rows = [
        ["Repository version", f"`{stack['repo_version']}`"],
        ["Platform version", f"`{stack['platform_version']}`"],
        ["Observed OS", f"`Debian {stack['observed_state']['os']['major']}`"],
        ["Observed Proxmox installed", "`true`" if stack["observed_state"]["proxmox"]["installed"] else "`false`"],
        ["Observed PVE manager version", f"`{stack['observed_state']['proxmox']['version']}`"],
        ["Declared services", str(len(host_vars["lv3_service_topology"]))],
    ]
    return "\n".join(
        [
            GENERATED_NOTICE,
            "",
            render_table(["Field", "Value"], version_rows),
        ]
    ).strip()


def render_merged_workstreams() -> str:
    budgets = load_root_summary_budgets()
    workstreams = load_workstreams(repo_root=REPO_ROOT, include_archive=True)
    merged_records = collect_merged_workstream_records(workstreams)
    recent_records = merged_records[: budgets.readme.recent_merged_workstream_entries]
    merged_rows = [
        [
            f"`{record.adr}`",
            record.title,
            f"`{record.status}`",
            repo_relative_link(record.doc_path.name, record.doc_path),
        ]
        for record in recent_records
    ]
    return "\n".join(
        [
            GENERATED_NOTICE,
            "",
            (
                f"Showing {len(recent_records)} of {len(merged_records)} merged or live-applied workstreams. "
                f"Full history: {relative_markdown_link('merged workstream history', from_path=README_PATH, target_path=REPO_ROOT / budgets.readme.merged_workstream_history_path)}"
            ),
            "",
            render_table(["ADR", "Title", "Status", "Doc"], merged_rows),
        ]
    ).strip()


def render_live_apply_history() -> str:
    budgets = load_root_summary_budgets()
    stack = load_yaml(STACK_PATH)
    history_path = REPO_ROOT / budgets.readme.live_apply_history_path
    receipt_rows = [
        [f"`{record.capability}`", f"`{record.receipt_id}`"]
        for record in collect_live_apply_evidence_records(stack["live_apply_evidence"]["latest_receipts"])
    ]
    return "\n".join(
        [
            "# Live-Apply Evidence History",
            "",
            "This generated ledger records every capability-to-receipt mapping currently tracked in `versions/stack.yaml`.",
            "",
            f"- README summary: {relative_markdown_link('README.md', from_path=history_path, target_path=README_PATH)}",
            "",
            "## Receipts",
            "",
            render_table(["Capability", "Receipt"], receipt_rows),
            "",
        ]
    )


def render_merged_workstream_history() -> str:
    budgets = load_root_summary_budgets()
    history_path = REPO_ROOT / budgets.readme.merged_workstream_history_path
    workstreams = load_workstreams(repo_root=REPO_ROOT, include_archive=True)
    rows = [
        [
            f"`{record.adr}`",
            record.title,
            f"`{record.status}`",
            relative_markdown_link(
                record.doc_path.name, from_path=history_path, target_path=REPO_ROOT / record.doc_path
            ),
        ]
        for record in collect_merged_workstream_records(workstreams)
    ]
    return "\n".join(
        [
            "# Merged Workstream History",
            "",
            "This generated ledger preserves the full merged and live-applied workstream history after the README summary rolls older rows away.",
            "",
            f"- README summary: {relative_markdown_link('README.md', from_path=history_path, target_path=README_PATH)}",
            "",
            "## Workstreams",
            "",
            render_table(["ADR", "Title", "Status", "Doc"], rows),
            "",
        ]
    )


def replace_generated_block(readme_text: str, marker: str, content: str) -> str:
    pattern = re.compile(
        rf"(<!-- BEGIN GENERATED: {re.escape(marker)} -->\n)(.*?)(<!-- END GENERATED: {re.escape(marker)} -->)",
        re.DOTALL,
    )
    replacement = rf"\1{content}\n\3"
    updated, count = pattern.subn(replacement, readme_text)
    if count != 1:
        raise ValueError(f"README marker '{marker}' must appear exactly once")
    return updated


def render_readme() -> str:
    readme_text = README_PATH.read_text()
    rendered_sections = {
        MARKERS["platform-status"]: render_platform_status(),
        MARKERS["control-plane-lanes"]: render_control_plane_lanes(),
        MARKERS["document-index"]: render_document_index(),
        MARKERS["version-summary"]: render_version_summary(),
        MARKERS["merged-workstreams"]: render_merged_workstreams(),
    }
    for marker, content in rendered_sections.items():
        readme_text = replace_generated_block(readme_text, marker, content)
    return readme_text


def render_generated_docs() -> dict[Path, str]:
    budgets = load_root_summary_budgets()
    rendered = {
        README_PATH: render_readme(),
        REPO_ROOT / budgets.readme.live_apply_history_path: render_live_apply_history(),
        REPO_ROOT / budgets.readme.merged_workstream_history_path: render_merged_workstream_history(),
    }
    enforce_line_budget(rendered[README_PATH], label="README.md", max_lines=budgets.readme.max_lines)
    return rendered


def write_generated_docs() -> int:
    rendered = render_generated_docs()
    for path, text in rendered.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(f"Updated generated status docs: {', '.join(str(path.relative_to(REPO_ROOT)) for path in rendered)}")
    return 0


def check_generated_docs() -> int:
    rendered = render_generated_docs()
    stale_paths = []
    for path, expected_text in rendered.items():
        if not path.exists() or path.read_text(encoding="utf-8") != expected_text:
            stale_paths.append(path.relative_to(REPO_ROOT).as_posix())
    if stale_paths:
        print(
            "Generated status docs are stale. Run "
            "'uvx --from pyyaml python scripts/generate_status_docs.py --write' or 'make generate-status-docs'. "
            f"Stale paths: {', '.join(stale_paths)}",
            file=sys.stderr,
        )
        return 2
    print("Generated status docs OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render or verify generated README status fragments from canonical repository state."
    )
    parser.add_argument("--write", action="store_true", help="Regenerate README generated sections.")
    parser.add_argument("--check", action="store_true", help="Verify generated README sections are current.")
    args = parser.parse_args()

    if args.write == args.check:
        parser.print_help()
        return 0

    try:
        if args.write:
            return write_generated_docs()
        return check_generated_docs()
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        return emit_cli_error("Generated status doc", exc)


if __name__ == "__main__":
    sys.exit(main())
