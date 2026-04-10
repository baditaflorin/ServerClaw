#!/usr/bin/env python3
"""One-time migration: add # BEGIN SERVICE / # END SERVICE markers to keycloak_runtime role.

Covers:
  - keycloak_runtime/defaults/main.yml  (variable groups per service)
  - keycloak_runtime/tasks/main.yml     (task blocks: reconcile, read-secret, set_fact, mirror)

After this script runs, decommission_service.py._remove_role_inline_markers() calls
_remove_yaml_block_markers() on each role YAML file and picks up both inline # SERVICE:
annotations AND block markers in one pass.

Usage:
    python3 scripts/migrate_keycloak_markers.py [--dry-run] [--defaults-only] [--tasks-only]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "keycloak_runtime"
)
DEFAULTS_PATH = ROLE_ROOT / "defaults" / "main.yml"
TASKS_PATH = ROLE_ROOT / "tasks" / "main.yml"

# Maps variable prefix → service_id used in markers.
# Order matters: more-specific prefixes must come before shorter ones
# (e.g., keycloak_ops_portal_ before keycloak_ops_).
KEYCLOAK_SERVICE_PREFIXES: list[tuple[str, str]] = [
    ("keycloak_api_gateway_",       "api_gateway"),
    ("keycloak_ops_portal_",        "ops_portal"),
    ("keycloak_grafana_",           "grafana"),
    ("keycloak_gitea_",             "gitea"),
    ("keycloak_agent_",             "agent"),
    ("keycloak_serverclaw_runtime_","serverclaw_runtime"),
    ("keycloak_langfuse_",          "langfuse"),
    ("keycloak_grist_",             "grist"),
    ("keycloak_directus_",          "directus"),
    ("keycloak_superset_",          "superset"),
    ("keycloak_glitchtip_",         "glitchtip"),
    ("keycloak_outline_",           "outline"),
    ("keycloak_paperless_",         "paperless"),
    ("keycloak_serverclaw_",        "serverclaw"),
    ("keycloak_dify_",              "dify"),
    ("keycloak_nomad_",             "nomad"),
    ("keycloak_plane_",             "plane"),
    # plane_oidc_* also belongs to plane
    ("plane_oidc_",                 "plane"),
]


def _service_for_line(line: str) -> str | None:
    """Return service_id if line starts with a keycloak_<service>_ variable key."""
    stripped = line.lstrip()
    if not stripped or stripped.startswith("#") or stripped.startswith("-"):
        return None
    key = stripped.split(":")[0].strip() if ":" in stripped else ""
    for prefix, service_id in KEYCLOAK_SERVICE_PREFIXES:
        if key.startswith(prefix) or key == prefix.rstrip("_"):
            return service_id
    return None


def migrate_defaults(text: str) -> str:
    """Add BEGIN/END SERVICE markers around variable groups in defaults/main.yml."""
    lines = text.splitlines(keepends=True)
    result: list[str] = []
    current_service: str | None = None
    in_multiline_value = False  # True when inside an indented list/block

    def close_current() -> None:
        nonlocal current_service
        if current_service:
            result.append(f"# END SERVICE: {current_service}\n")
            current_service = None

    for line in lines:
        raw = line.rstrip("\n").rstrip("\r")
        stripped = raw.lstrip()
        indent = len(raw) - len(stripped) if raw.strip() else 0

        # Inside a multi-line YAML value (indented list items)
        if in_multiline_value:
            if not stripped or indent > 0:
                result.append(line)
                continue
            # Exited the multi-line block
            in_multiline_value = False

        # Blank line — close current service block
        if not stripped:
            close_current()
            result.append(line)
            continue

        # Comment line — keep as-is (don't close current block)
        if stripped.startswith("#"):
            result.append(line)
            continue

        # Top-level YAML key (indent == 0)
        service = _service_for_line(line)

        if service:
            if service != current_service:
                close_current()
                result.append(f"# BEGIN SERVICE: {service}\n")
                current_service = service
            result.append(line)
            # If this line's value is a bare key (no value = next line is a block),
            # mark that we might enter a multi-line value
            if raw.rstrip().endswith(":"):
                in_multiline_value = True
        else:
            # Non-service line — close any open service block
            close_current()
            result.append(line)

    close_current()
    return "".join(result)


def _find_task_block_bounds(lines: list[str], start: int) -> int:
    """Return the index of the last line of the Ansible task block starting at `start`.

    A task block is a YAML list item starting with `- name:` and ends at the line
    before the next `- name:` at the same or lower indentation, or a blank line
    that is followed by a `- name:` at the same level.
    """
    if start >= len(lines):
        return start

    first_line = lines[start]
    task_indent = len(first_line) - len(first_line.lstrip())

    end = start
    i = start + 1
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        current_indent = len(line) - len(stripped) if line.strip() else -1

        if not line.strip():
            # Blank line — peek ahead
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                next_stripped = lines[j].lstrip()
                next_indent = len(lines[j]) - len(next_stripped)
                if next_stripped.startswith("- name:") and next_indent <= task_indent:
                    # Blank gap before next sibling task — stop before the blank
                    return end
            # Blank line inside block — continue
            end = i
            i += 1
            continue

        if current_indent <= task_indent and stripped.startswith("- "):
            # New sibling (or parent) list item — stop
            return end

        end = i
        i += 1

    return end


def _get_task_service(lines: list[str], idx: int) -> str | None:
    """Return service_id if the `- name:` task line at idx is a per-service keycloak task."""
    line = lines[idx].strip()
    if not line.startswith("- name:"):
        return None
    name = line[len("- name:"):].strip().strip("\"'")
    name_lower = name.lower()

    # Match patterns: "Ensure the X OAuth client", "Read the X client secret",
    # "Mirror the X client secret"
    for prefix, service_id in KEYCLOAK_SERVICE_PREFIXES:
        service_slug = service_id.replace("_", " ").lower()
        service_slug_dash = service_id.replace("_", "-").lower()
        if (
            service_slug in name_lower
            or service_slug_dash in name_lower
            or prefix.strip("_").replace("_", " ") in name_lower
        ):
            return service_id
    return None


def migrate_tasks(text: str) -> str:
    """Add BEGIN/END SERVICE markers around per-service task blocks in tasks/main.yml.

    Handles three patterns:
    1. `- name: Ensure/Read/Mirror the X ...` task list items
    2. `keycloak_x_client_secret: "..."` lines inside a set_fact vars block
    """
    lines = text.splitlines(keepends=True)
    marked_ranges: list[tuple[int, int, str]] = []  # (start_idx, end_idx, service_id)

    # Pass 1: find - name: task blocks
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped.startswith("- name:"):
            continue
        service = _get_task_service(lines, i)
        if service is None:
            continue
        end = _find_task_block_bounds(lines, i)
        marked_ranges.append((i, end, service))

    # Pass 2: find keycloak_x_client_secret: lines in set_fact vars block
    for i, line in enumerate(lines):
        key = line.lstrip().split(":")[0].strip() if ":" in line.lstrip() else ""
        if not re.match(r"keycloak_\w+_client_secret$", key):
            continue
        # Only single-line set_fact style (not an existing block)
        service = None
        for prefix, sid in KEYCLOAK_SERVICE_PREFIXES:
            if key == f"{prefix}client_secret".rstrip("_"):
                service = sid
                break
            # try: keycloak_<service_id>_client_secret
            expected = f"keycloak_{sid.replace('-','_')}_client_secret"
            if key == expected:
                service = sid
                break
        if service:
            marked_ranges.append((i, i, service))

    if not marked_ranges:
        return text

    # Sort and deduplicate / merge overlapping ranges
    marked_ranges.sort(key=lambda r: r[0])

    # Build the new lines with markers inserted
    marked_lines: dict[int, tuple[str, str]] = {}  # line_idx → (begin_marker, end_marker)
    for start, end, service in marked_ranges:
        # Determine indent from the first line
        first_line = lines[start]
        indent = len(first_line) - len(first_line.lstrip())
        ind = " " * indent
        begin = f"{ind}# BEGIN SERVICE: {service}\n"
        end_marker = f"{ind}# END SERVICE: {service}\n"

        # Don't double-wrap
        if start in marked_lines:
            continue

        marked_lines[start] = (begin, "")
        marked_lines[end] = ("", end_marker)

        if start == end:
            marked_lines[start] = (begin, end_marker)

    result: list[str] = []
    for i, line in enumerate(lines):
        if i in marked_lines:
            begin_m, end_m = marked_lines[i]
            if begin_m:
                result.append(begin_m)
            result.append(line)
            if end_m:
                result.append(end_m)
        else:
            result.append(line)

    return "".join(result)


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    defaults_only = "--defaults-only" in sys.argv
    tasks_only = "--tasks-only" in sys.argv

    exit_code = 0

    if not tasks_only:
        if not DEFAULTS_PATH.is_file():
            print(f"ERROR: {DEFAULTS_PATH} not found", file=sys.stderr)
            return 1
        original = DEFAULTS_PATH.read_text()
        if "# BEGIN SERVICE:" in original:
            print(f"INFO: {DEFAULTS_PATH.name} already contains markers — skipping")
        else:
            migrated = migrate_defaults(original)
            begin_count = migrated.count("# BEGIN SERVICE:")
            end_count = migrated.count("# END SERVICE:")
            if begin_count != end_count:
                print(
                    f"ERROR: defaults marker mismatch: {begin_count} BEGIN vs {end_count} END",
                    file=sys.stderr,
                )
                exit_code = 1
            else:
                print(f"defaults/main.yml: {begin_count} service blocks marked")
                if dry_run:
                    for i, line in enumerate(migrated.splitlines()[:150], 1):
                        print(f"{i:4d}  {line}")
                else:
                    DEFAULTS_PATH.write_text(migrated)
                    print(f"Wrote {DEFAULTS_PATH}")

    if not defaults_only and exit_code == 0:
        if not TASKS_PATH.is_file():
            print(f"ERROR: {TASKS_PATH} not found", file=sys.stderr)
            return 1
        original = TASKS_PATH.read_text()
        if "# BEGIN SERVICE:" in original:
            print(f"INFO: {TASKS_PATH.name} already contains markers — skipping")
        else:
            migrated = migrate_tasks(original)
            begin_count = migrated.count("# BEGIN SERVICE:")
            end_count = migrated.count("# END SERVICE:")
            print(f"tasks/main.yml: {begin_count} BEGIN, {end_count} END markers")
            try:
                import yaml
                yaml.safe_load(migrated)
                print("tasks/main.yml YAML parse: OK")
            except Exception as e:
                print(f"WARNING: tasks/main.yml YAML parse failed: {e}", file=sys.stderr)
                # Don't fail — tasks files can have Jinja2 that confuses YAML parser
            if dry_run:
                print("DRY-RUN: tasks not written")
            else:
                TASKS_PATH.write_text(migrated)
                print(f"Wrote {TASKS_PATH}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
