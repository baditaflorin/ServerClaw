#!/usr/bin/env python3
"""Write the bootstrap completion receipt to receipts/live-applies/.

Called by `make write-bootstrap-receipt` (bootstrap step 13, ADR 0483).
The receipt marks the deployment as bootstrap-verified. Downstream tooling
(ADR 0420) checks for the presence of this file.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
RECEIPTS_DIR = REPO_ROOT / "receipts" / "live-applies"


def main() -> int:
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.datetime.now(tz=datetime.timezone.utc)
    slug = ts.strftime("%Y-%m-%dT%H-%M-%SZ")

    receipt: dict = {
        "schema_version": 1,
        "receipt_type": "bootstrap-complete",
        "written_at": ts.isoformat(),
    }

    # Optionally annotate with the deployment domain.
    identity_path = REPO_ROOT / ".local" / "identity.yml"
    if identity_path.exists():
        try:
            import yaml  # type: ignore[import]

            identity = yaml.safe_load(identity_path.read_text())
            receipt["deployment"] = identity.get("platform_domain", "unknown")
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"warning: could not read identity: {exc}\n")

    path = RECEIPTS_DIR / f"{slug}-bootstrap-complete.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    sys.stdout.write(f"Bootstrap receipt written: {path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
