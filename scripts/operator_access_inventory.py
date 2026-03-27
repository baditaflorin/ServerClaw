#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys

from controller_automation_toolkit import emit_cli_error
from operator_manager import ROSTER_PATH, STATE_DIR, inventory, render_inventory_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show the current access inventory for one operator.")
    parser.add_argument("--id", required=True)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        payload = inventory(
            roster_path=ROSTER_PATH,
            state_dir=STATE_DIR,
            operator_id=args.id,
            actor_id="inventory",
            actor_class="operator",
            dry_run=args.dry_run,
            offline=args.offline,
        )
    except Exception as exc:
        return emit_cli_error("Operator inventory", exc)

    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render_inventory_text(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
