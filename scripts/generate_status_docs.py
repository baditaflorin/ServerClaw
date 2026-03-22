#!/usr/bin/env python3

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - direct runtime guard
    print(
        "Missing dependency: PyYAML. Run via 'uvx --from pyyaml python ...' or 'uv run --with pyyaml ...'.",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc


REPO_ROOT = Path(__file__).resolve().parent.parent
README_PATH = REPO_ROOT / "README.md"
STACK_PATH = REPO_ROOT / "versions" / "stack.yaml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"
WORKSTREAMS_PATH = REPO_ROOT / "workstreams.yaml"
RUNBOOKS_DIR = REPO_ROOT / "docs" / "runbooks"
ADR_DIR = REPO_ROOT / "docs" / "adr"
WORKSTREAM_DOCS_DIR = REPO_ROOT / "docs" / "workstreams"

GENERATED_NOTICE = (
    "> Generated from canonical repository state by "
    "[`scripts/generate_status_docs.py`]"
    "(/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_status_docs.py). "
    "Do not edit this block by hand."
)
MARKERS = {
    "platform-status": "platform-status",
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


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text())


def read_heading(path: Path) -> str:
    for line in path.read_text().splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def absolute_link(label: str, path: Path) -> str:
    return f"[{label}]({path})"


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
    except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
        print(f"Generated status doc error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
