#!/usr/bin/env python3

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from api_publication import ALLOWED_PUBLICATION_TIERS, load_api_publication_catalog
from control_plane_lanes import ALLOWED_LANE_IDS, load_lane_catalog
from controller_automation_toolkit import README_PATH, emit_cli_error, load_yaml, repo_path


REPO_ROOT = repo_path()
CANONICAL_REPO_ROOT = Path("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server")
STACK_PATH = repo_path("versions", "stack.yaml")
HOST_VARS_PATH = repo_path("inventory", "host_vars", "proxmox_florin.yml")
WORKSTREAMS_PATH = repo_path("workstreams.yaml")
RUNBOOKS_DIR = repo_path("docs", "runbooks")
ADR_DIR = repo_path("docs", "adr")
WORKSTREAM_DOCS_DIR = repo_path("docs", "workstreams")

GENERATED_NOTICE = (
    "> Generated from canonical repository state by "
    "[`scripts/generate_status_docs.py`]"
    "(/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_status_docs.py). "
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


def absolute_link(label: str, path: Path) -> str:
    resolved_path = path
    if path.is_absolute() and path.is_relative_to(REPO_ROOT):
        resolved_path = CANONICAL_REPO_ROOT / path.relative_to(REPO_ROOT)
    return f"[{label}]({resolved_path})"


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def render_platform_status() -> str:
    stack = load_yaml(STACK_PATH)
    host_vars = load_yaml(HOST_VARS_PATH)

    version_rows = [
        ["Repository version", f"`{stack['repo_version']}`"],
        ["Platform version", f"`{stack['platform_version']}`"],
        ["Observed check date", f"`{stack['observed_state']['checked_at']}`"],
        ["Observed OS", f"`Debian {stack['observed_state']['os']['major']}`"],
        ["Observed Proxmox version", f"`{stack['observed_state']['proxmox']['version']}`"],
        ["Observed kernel", f"`{stack['observed_state']['os']['kernel']}`"],
    ]

    guest_rows = []
    for guest in stack["observed_state"]["guests"]["instances"]:
        guest_rows.append(
            [
                str(guest["vmid"]),
                f"`{guest['name']}`",
                f"`{guest['ipv4']}`",
                "`true`" if guest["running"] else "`false`",
            ]
        )

    service_rows = []
    topology = host_vars["lv3_service_topology"]
    for service_id, service in sorted(topology.items(), key=lambda item: item[1].get("public_hostname") or item[0]):
        public_hostname = service.get("public_hostname")
        if not public_hostname:
            continue
        service_rows.append(
            [
                f"`{public_hostname}`",
                f"`{service['service_name']}`",
                f"`{service['exposure_model']}`",
                f"`{service['owning_vm']}`",
            ]
        )

    receipt_rows = []
    for capability, receipt_id in sorted(stack["live_apply_evidence"]["latest_receipts"].items()):
        receipt_rows.append([f"`{capability}`", f"`{receipt_id}`"])

    parts = [
        GENERATED_NOTICE,
        "",
        "### Current Values",
        render_table(["Field", "Value"], version_rows),
        "",
        "### Managed Guests",
        render_table(["VMID", "Name", "IPv4", "Running"], guest_rows),
        "",
        f"Template VM: `{stack['observed_state']['guests']['template']['vmid']}` "
        f"`{stack['observed_state']['guests']['template']['name']}`",
        "",
        "### Published Service Inventory",
        render_table(["Hostname", "Service", "Exposure", "Owner"], service_rows),
        "",
        "### Latest Live-Apply Evidence",
        render_table(["Capability", "Receipt"], receipt_rows),
    ]
    return "\n".join(parts).strip()


def render_control_plane_lanes() -> str:
    _catalog, normalized_lanes = load_lane_catalog()
    _publication_catalog, normalized_tiers, normalized_surfaces = load_api_publication_catalog()
    lane_rows = []
    surface_rows = []
    tier_rows = []
    classified_surface_rows = []
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
        for surface in lane["current_surfaces"]:
            surface_rows.append(
                [
                    f"`{surface['id']}`",
                    f"`{lane_id}`",
                    f"`{surface['kind']}`",
                    f"`{surface['endpoint']}`",
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

    for surface in normalized_surfaces:
        classified_surface_rows.append(
            [
                f"`{surface['id']}`",
                f"`{surface['publication_tier']}`",
                f"`{surface['lane']}`",
                f"`{surface['endpoint']}`",
                surface["reachability"],
            ]
        )

    return "\n".join(
        [
            GENERATED_NOTICE,
            "",
            "### Lane Summary",
            render_table(["Lane", "Title", "Transport", "Surfaces", "Primary Rule"], lane_rows),
            "",
            "### Current Governed Surfaces",
            render_table(["Surface", "Lane", "Kind", "Endpoint"], surface_rows),
            "",
            "### API Publication Tiers",
            render_table(["Tier", "Title", "Surfaces", "Summary"], tier_rows),
            "",
            "### Classified API And Webhook Surfaces",
            render_table(["Surface", "Tier", "Lane", "Endpoint", "Reachability"], classified_surface_rows),
        ]
    ).strip()


def render_document_links(paths: list[Path]) -> list[str]:
    return [f"- {absolute_link(read_heading(path), path)}" for path in paths]


def render_document_index() -> str:
    runbooks = sorted(RUNBOOKS_DIR.glob("*.md"))
    adrs = sorted(ADR_DIR.glob("*.md"))
    workstream_docs = sorted(
        path
        for path in WORKSTREAM_DOCS_DIR.glob("*.md")
        if path.name not in {"README.md", "TEMPLATE.md"}
    )

    parts = [
        GENERATED_NOTICE,
        "",
        "### Core Documents",
        *[f"- {absolute_link(label, path)}" for label, path in CORE_DOCUMENTS],
        "",
        "### Runbooks",
        *render_document_links(runbooks),
        "",
        "### ADRs",
        *render_document_links(adrs),
        "",
        "### Workstream Documents",
        *render_document_links(workstream_docs),
    ]
    return "\n".join(parts).strip()


def render_version_summary() -> str:
    stack = load_yaml(STACK_PATH)
    version_rows = [
        ["Repository version", f"`{stack['repo_version']}`"],
        ["Platform version", f"`{stack['platform_version']}`"],
        ["Observed OS", f"`Debian {stack['observed_state']['os']['major']}`"],
        ["Observed Proxmox installed", "`true`" if stack["observed_state"]["proxmox"]["installed"] else "`false`"],
        ["Observed PVE manager version", f"`{stack['observed_state']['proxmox']['version']}`"],
    ]
    return "\n".join(
        [
            GENERATED_NOTICE,
            "",
            render_table(["Field", "Value"], version_rows),
        ]
    ).strip()


def render_merged_workstreams() -> str:
    workstreams = load_yaml(WORKSTREAMS_PATH)["workstreams"]
    merged_rows = []
    for workstream in sorted(workstreams, key=lambda item: (int(item["adr"]), item["id"])):
        if workstream["status"] not in {"merged", "live_applied"}:
            continue
        merged_rows.append(
            [
                f"`{workstream['adr']}`",
                workstream["title"],
                f"`{workstream['status']}`",
                absolute_link(Path(workstream["doc"]).name, Path(workstream["doc"])),
            ]
        )
    return "\n".join(
        [
            GENERATED_NOTICE,
            "",
            render_table(["ADR", "Title", "Status", "Doc"], merged_rows),
        ]
    ).strip()


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


def write_generated_docs() -> int:
    rendered = render_readme()
    README_PATH.write_text(rendered)
    print(f"Updated generated status docs: {README_PATH}")
    return 0


def check_generated_docs() -> int:
    rendered = render_readme()
    current = README_PATH.read_text()
    if rendered != current:
        print(
            "Generated status docs are stale. Run "
            "'uvx --from pyyaml python scripts/generate_status_docs.py --write' or 'make generate-status-docs'.",
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
