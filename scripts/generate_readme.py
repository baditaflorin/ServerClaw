#!/usr/bin/env python3
"""Generate README.md from docs/templates/README.md.j2 and live repository data.

# =============================================================================
# GENERATED OUTPUT: README.md
# SOURCE TEMPLATE:  docs/templates/README.md.j2
# THIS SCRIPT:      scripts/generate_readme.py
# Run:              make generate-readme
# Check drift:      make validate-generated-readme
# =============================================================================

Data injected at render time:
  counts.roles         — Ansible role count (collections/.../roles/)
  counts.playbooks     — playbook count (collections/.../playbooks/)
  counts.adrs          — ADR count (docs/adr/*.md)
  counts.runbooks      — runbook count (docs/runbooks/*.md)
  counts.scripts       — script count (scripts/*.py)
  counts.services      — service count (config/service-capability-catalog.json)
  counts.make_targets  — annotated Makefile target count
  make_targets_table   — markdown table built from Makefile '## ' annotations
  generated_on         — ISO date (YYYY-MM-DD) at render time

Design:
  - Pure function: build_context() -> dict
  - Render: render(context) -> str  (Jinja2 template)
  - Entry points: --write / --check / --print  (same pattern as generate_inventory.py)

Adding a new key Makefile target to the README table:
  1. Annotate the Makefile target with '## Description'
  2. Add the target name to KEY_MAKE_TARGETS below
  3. Run: make generate-readme
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = REPO_ROOT / "docs" / "templates" / "README.md.j2"
README_PATH = REPO_ROOT / "README.md"
MAKEFILE_PATH = REPO_ROOT / "Makefile"
SERVICE_CATALOG_PATH = REPO_ROOT / "config" / "service-capability-catalog.json"

# ---------------------------------------------------------------------------
# Curated key targets shown in the README Make Targets table.
# Order is preserved. Descriptions are pulled live from Makefile '## ' comments.
# To add a target: annotate it in the Makefile and add the name here.
# ---------------------------------------------------------------------------
KEY_MAKE_TARGETS: list[str] = [
    "init-local",
    "generate-inventory",
    "validate-generated-inventory",
    "bootstrap",
    "bootstrap-minimal",
    "docker-dev-up",
    "docker-dev-converge",
    "converge-<service>",
    "verify-platform",
    "validate",
    "validate-types",
    "validate-cross-catalog",
    "generate-readme",
    "validate-generated-readme",
    "publish-serverclaw",
]

# Descriptions for parametric / synthetic targets not present verbatim in the Makefile.
SYNTHETIC_DESCRIPTIONS: dict[str, str] = {
    "converge-<service>": "Deploy a specific service",
    "generate-readme": "Regenerate README.md from docs/templates/README.md.j2",
    "validate-generated-readme": "Exit 1 if README.md is out of sync with template",
}


# ---------------------------------------------------------------------------
# Data collection — all pure functions, no side effects
# ---------------------------------------------------------------------------


def _count_glob(path: Path, pattern: str) -> int:
    return len(list(path.glob(pattern))) if path.exists() else 0


def _count_dir(path: Path) -> int:
    """Count immediate children (files + dirs) of path."""
    return len(list(path.iterdir())) if path.exists() else 0


def collect_counts() -> dict:
    """Return live filesystem counts for all README stats."""
    roles_dir = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"
    playbooks_dir = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks"

    services = 0
    if SERVICE_CATALOG_PATH.exists():
        catalog = json.loads(SERVICE_CATALOG_PATH.read_text())
        services = len(catalog.get("services", []))

    makefile_targets = parse_makefile_targets(MAKEFILE_PATH)

    return {
        "roles": _count_glob(roles_dir, "*/"),
        "playbooks": _count_glob(playbooks_dir, "*.yml"),
        "adrs": _count_glob(REPO_ROOT / "docs" / "adr", "*.md"),
        "runbooks": _count_glob(REPO_ROOT / "docs" / "runbooks", "*.md"),
        "scripts": _count_glob(REPO_ROOT / "scripts", "*.py"),
        "services": services,
        "make_targets": len(makefile_targets),
    }


def parse_makefile_targets(makefile: Path) -> dict[str, str]:
    """Parse ``target: ## Description`` lines from a Makefile.

    Returns a dict of {target_name: description_string}.
    """
    targets: dict[str, str] = {}
    if not makefile.exists():
        return targets
    pattern = re.compile(r"^([a-zA-Z_-][a-zA-Z0-9_./-]*):\s*##\s*(.+)$")
    for line in makefile.read_text().splitlines():
        m = pattern.match(line)
        if m:
            targets[m.group(1)] = m.group(2).strip()
    return targets


def build_make_targets_table(makefile_targets: dict[str, str]) -> str:
    """Render the KEY_MAKE_TARGETS list as a markdown table.

    Descriptions come from Makefile '## ' annotations; synthetic targets
    use SYNTHETIC_DESCRIPTIONS. Missing targets fall back to '—'.
    """
    rows = ["| Target | Description |", "|--------|-------------|"]
    for target in KEY_MAKE_TARGETS:
        desc = SYNTHETIC_DESCRIPTIONS.get(target) or makefile_targets.get(target, "—")
        rows.append(f"| `make {target}` | {desc} |")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Rendering — Jinja2 template → string
# ---------------------------------------------------------------------------


def render(template_path: Path = TEMPLATE_PATH) -> str:
    """Render the README template with live data. Returns the full README string."""
    try:
        from jinja2 import Environment, FileSystemLoader, StrictUndefined
    except ImportError:
        print(
            "ERROR: jinja2 not available. Install with: uv pip install jinja2",
            file=sys.stderr,
        )
        sys.exit(2)

    counts = collect_counts()
    makefile_targets = parse_makefile_targets(MAKEFILE_PATH)
    make_targets_table = build_make_targets_table(makefile_targets)

    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,  # Markdown, not HTML
    )
    tmpl = env.get_template(template_path.name)
    # Strip the Jinja2 comment block from the top of the rendered output;
    # it's already human-readable in the template file itself.
    return tmpl.render(
        counts=counts,
        make_targets_table=make_targets_table,
        generated_on=date.today().isoformat(),
    )


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------


def check_drift(current_path: Path = README_PATH) -> bool:
    """Return True if README.md matches generated output, False if drift detected."""
    generated = render()
    if not current_path.exists():
        return False
    return current_path.read_text() == generated


def show_diff(current_path: Path = README_PATH) -> str:
    """Return a unified diff between current README.md and generated output."""
    generated = render().splitlines(keepends=True)
    current = current_path.read_text().splitlines(keepends=True) if current_path.exists() else []
    return "".join(
        difflib.unified_diff(
            current,
            generated,
            fromfile=str(current_path),
            tofile="<generated>",
        )
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate README.md from docs/templates/README.md.j2 and live repo data. "
            "Run 'make generate-readme' after editing the template or adding Makefile targets."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="Write README.md")
    mode.add_argument("--check", action="store_true", help="Exit 1 if drift detected")
    mode.add_argument("--print", action="store_true", help="Print to stdout (dry-run)")
    parser.add_argument(
        "--template",
        metavar="PATH",
        default=str(TEMPLATE_PATH),
        help=f"Path to README.md.j2 (default: {TEMPLATE_PATH})",
    )
    args = parser.parse_args()

    template_path = Path(args.template)
    if not template_path.exists():
        print(f"ERROR: template not found: {template_path}", file=sys.stderr)
        sys.exit(2)

    if args.print:
        print(render(template_path), end="")
        return

    if args.write:
        content = render(template_path)
        README_PATH.write_text(content)
        print(f"Written {README_PATH}", file=sys.stderr)
        return

    if args.check:
        if check_drift(README_PATH):
            print("README.md is up to date.", file=sys.stderr)
            sys.exit(0)
        diff = show_diff(README_PATH)
        if diff:
            print("DRIFT DETECTED — README.md is out of date:", file=sys.stderr)
            print(diff, file=sys.stderr)
        else:
            print(
                "DRIFT DETECTED — README.md does not exist or is empty.",
                file=sys.stderr,
            )
        print("Run: make generate-readme", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
