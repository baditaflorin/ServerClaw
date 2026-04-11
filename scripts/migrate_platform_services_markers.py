#!/usr/bin/env python3
"""One-time migration: add # BEGIN SERVICE / # END SERVICE markers to platform_services.yml.

After this script runs, decommission_service.py can use _remove_yaml_block_markers to
atomically remove any service block (key + entire body) in a single CPU-only pass.

Usage:
    python3 scripts/migrate_platform_services_markers.py [--dry-run]
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET = REPO_ROOT / "inventory" / "group_vars" / "all" / "platform_services.yml"
REGISTRY_KEY = "platform_service_registry"


def add_markers(text: str) -> str:
    lines = text.splitlines(keepends=True)
    result: list[str] = []

    STATE_PREAMBLE = "preamble"
    STATE_REGISTRY_GAP = "registry_gap"
    STATE_IN_SERVICE = "in_service"

    state = STATE_PREAMBLE
    current_service: str | None = None
    service_lines: list[str] = []

    def flush_service() -> None:
        nonlocal current_service, service_lines
        if current_service and service_lines:
            result.append(f"  # BEGIN SERVICE: {current_service}\n")
            result.extend(service_lines)
            result.append(f"  # END SERVICE: {current_service}\n")
        current_service = None
        service_lines = []

    for line in lines:
        raw = line.rstrip("\n").rstrip("\r")
        stripped = raw.lstrip()
        indent = len(raw) - len(stripped) if raw.strip() else 0

        if state == STATE_PREAMBLE:
            result.append(line)
            if stripped.rstrip(":") == REGISTRY_KEY:
                state = STATE_REGISTRY_GAP
            continue

        # ---- inside platform_service_registry ----

        # Return to top-level (non-blank, non-comment at indent 0)
        if stripped and indent == 0 and not stripped.startswith("#"):
            flush_service()
            result.append(line)
            state = STATE_PREAMBLE
            continue

        if state == STATE_REGISTRY_GAP:
            # Blank line or section-separator comment: gap content
            if not stripped or (stripped.startswith("#") and indent <= 2):
                result.append(line)
                continue
            # New service key at 2-space indent
            if indent == 2 and ":" in stripped and not stripped.startswith("#"):
                current_service = stripped.split(":")[0].strip()
                service_lines = [line]
                state = STATE_IN_SERVICE
                continue
            # Anything else (shouldn't occur) — keep as-is
            result.append(line)
            continue

        if state == STATE_IN_SERVICE:
            # Blank line = end of service block
            if not stripped:
                flush_service()
                result.append(line)
                state = STATE_REGISTRY_GAP
                continue
            # Section-separator comment at 2-space = end of service block
            if stripped.startswith("#") and indent <= 2:
                flush_service()
                result.append(line)
                state = STATE_REGISTRY_GAP
                continue
            # Another service key at 2-space = adjacent service
            if indent == 2 and ":" in stripped and not stripped.startswith("#"):
                flush_service()
                current_service = stripped.split(":")[0].strip()
                service_lines = [line]
                # state stays IN_SERVICE
                continue
            # Content inside the service block
            service_lines.append(line)
            continue

    # Flush any trailing service (end of file without trailing blank)
    if state == STATE_IN_SERVICE:
        flush_service()

    return "".join(result)


def validate_markers(text: str, original: str) -> list[str]:
    """Basic sanity checks on the migrated file."""
    errors: list[str] = []
    begin_count = text.count("# BEGIN SERVICE:")
    end_count = text.count("# END SERVICE:")
    if begin_count != end_count:
        errors.append(f"Mismatched markers: {begin_count} BEGIN vs {end_count} END")

    # Count original service keys (2-space indent keys under platform_service_registry)
    import re

    service_keys = re.findall(r"^  ([a-z][a-z0-9_]+):", original, re.MULTILINE)
    # Filter out keys that are inside registry content (they'd be at indent >2 in original)
    # The 2-space keys in original that appear after platform_service_registry
    in_registry = False
    expected_services = []
    for m in re.finditer(r"^  ([a-z][a-z0-9_]+):", original, re.MULTILINE):
        key = m.group(1)
        # Simple check: if the key appears in the migrated text as a BEGIN SERVICE marker
        expected_services.append(key)

    if begin_count < len(expected_services) - 5:
        errors.append(f"Too few markers ({begin_count}) for {len(expected_services)} candidate service keys")

    # Try YAML parse
    try:
        import yaml

        yaml.safe_load(text)
    except Exception as e:
        errors.append(f"YAML parse failed after migration: {e}")

    return errors


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    if not TARGET.is_file():
        print(f"ERROR: {TARGET} not found", file=sys.stderr)
        return 1

    original = TARGET.read_text()

    # Skip if already migrated
    if "# BEGIN SERVICE:" in original:
        print(f"INFO: {TARGET.name} already contains markers — skipping")
        return 0

    migrated = add_markers(original)
    errors = validate_markers(migrated, original)

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    begin_count = migrated.count("# BEGIN SERVICE:")
    print(f"Migration: {begin_count} service blocks marked")

    if dry_run:
        print("DRY-RUN: no file written")
        print("--- first 120 migrated lines ---")
        for i, line in enumerate(migrated.splitlines()[:120], 1):
            print(f"{i:4d}  {line}")
    else:
        TARGET.write_text(migrated)
        print(f"Wrote {TARGET}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
