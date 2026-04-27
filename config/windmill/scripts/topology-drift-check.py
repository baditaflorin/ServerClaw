#!/usr/bin/env python3
"""ADR 0443 — Windmill wrapper for the topology reconciler.

Runs `scripts/topology_reconciler.py --mode reconcile` against the
deployment selected via the LV3_DEPLOYMENT env var (or the
deployment-marker on disk). Returns a structured payload Windmill can
fan out to alerting:

    {
      "status": "ok" | "drift" | "error",
      "deployment": "<slug>",
      "drift_count": <int>,
      "drifts": [...],         # truncated to 50 entries
      "report_path": "<json>",
      "report_md_path": "<md>"
    }

Exit code mirrors the reconciler: 0 clean, 1 drift detected, >1 error.

Designed to run from the repo's worker checkout (same layout as
atlas-drift-check.py and continuous-drift-detection.py). It does NOT
fan out to remote hosts itself — the reconciler does that via SSH using
the bootstrap key inside .local/.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _resolve_repo_root() -> Path:
    """Locate the repo root by walking up from this script."""
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "scripts" / "topology_reconciler.py").exists():
            return parent
    return here.parent.parent.parent.parent


def main() -> int:
    repo_root = _resolve_repo_root()
    deployment = os.environ.get("LV3_DEPLOYMENT", "").strip()

    cmd: list[str] = [
        sys.executable,
        str(repo_root / "scripts" / "topology_reconciler.py"),
        "--mode", "reconcile",
        "--write-report",
    ]
    if deployment:
        cmd += ["--deployment", deployment]

    ssh_user = os.environ.get("LV3_TOPOLOGY_SSH_USER", "").strip()
    if ssh_user:
        cmd += ["--ssh-user", ssh_user]
    ssh_key = os.environ.get("LV3_TOPOLOGY_SSH_KEY", "").strip()
    if not ssh_key:
        # Default to the bootstrap key that other Ansible plays use.
        candidate = repo_root / ".local" / "ssh" / "bootstrap.id_ed25519"
        if candidate.exists():
            ssh_key = str(candidate)
    if ssh_key:
        cmd += ["--ssh-key", ssh_key]

    completed = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ},
    )

    payload: dict[str, object] = {
        "command": " ".join(cmd),
        "returncode": completed.returncode,
        "deployment": deployment or "(auto-resolved)",
        "stderr": completed.stderr.strip(),
    }

    # Reconciler exits 2 on deployment-resolution errors. Treat as error.
    if completed.returncode == 2:
        payload["status"] = "error"
        payload["reason"] = "deployment-resolution failed"
        print(json.dumps(payload, indent=2, sort_keys=True))
        return completed.returncode

    # Reconciler writes a JSON report; locate it from stdout, or by
    # calling deployment.py to compute the state_dir.
    report_json: dict | None = None
    report_path: Path | None = None
    md_path: Path | None = None
    for line in completed.stdout.splitlines():
        line = line.strip()
        if line.startswith("Wrote ") and line.endswith(".json"):
            report_path = Path(line[len("Wrote "):])
        elif line.startswith("Wrote ") and line.endswith(".md"):
            md_path = Path(line[len("Wrote "):])
    if report_path is None:
        # Fall back to the canonical state-dir path.
        slug = deployment or "prod"
        report_path = repo_root / ".local" / "deployments" / slug / "state" / "drift-report.json"
    if md_path is None:
        md_path = report_path.with_suffix(".md")

    if report_path.exists():
        try:
            report_json = json.loads(report_path.read_text())
        except json.JSONDecodeError:
            report_json = None

    drift_count = 0
    drifts: list = []
    if isinstance(report_json, dict):
        drift_count = int(report_json.get("drift_count", 0))
        drifts = list(report_json.get("drifts") or [])
        payload["deployment"] = report_json.get("deployment", payload["deployment"])

    payload["drift_count"] = drift_count
    payload["drifts"] = drifts[:50]  # cap noise
    payload["report_path"] = str(report_path)
    payload["report_md_path"] = str(md_path)

    if completed.returncode == 0 and drift_count == 0:
        payload["status"] = "ok"
    elif completed.returncode == 1 or drift_count > 0:
        payload["status"] = "drift"
    else:
        payload["status"] = "error"

    # Publish an ops-portal-compatible receipt under receipts/drift-reports/.
    # The portal aggregator reads {summary, generated_at, records[]} —
    # convert each topology drift entry into that shape.
    receipt_path = _publish_ops_portal_receipt(repo_root, report_json, payload)
    if receipt_path is not None:
        payload["ops_portal_receipt"] = str(receipt_path)

    print(json.dumps(payload, indent=2, sort_keys=True))
    return completed.returncode


def _publish_ops_portal_receipt(
    repo_root: Path,
    report: dict | None,
    payload: dict,
) -> Path | None:
    """Translate the topology drift report into the ops-portal receipt
    schema and write it under receipts/drift-reports/."""
    if not isinstance(report, dict):
        return None
    out_dir = repo_root / "receipts" / "drift-reports"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    severity_for = {
        "missing": "critical",
        "misplaced": "critical",
        "unexpected": "warn",
        "port_stranger": "warn",
    }
    records: list[dict[str, object]] = []
    for d in report.get("drifts") or []:
        if not isinstance(d, dict):
            continue
        sev = severity_for.get(str(d.get("severity")), "warn")
        records.append({
            "source": "topology-reconciler",
            "severity": sev,
            "service": d.get("service"),
            "resource": d.get("host"),
            "detail": d.get("detail") or f"{d.get('severity')} on {d.get('host')}",
        })
    summary = {
        "status": payload.get("status", "unknown"),
        "drift_count": payload.get("drift_count", 0),
        "deployment": payload.get("deployment"),
    }
    out_payload = {
        "schema": "ops-portal-drift-receipt/v1",
        "generated_at": report.get("captured_at"),
        "summary": summary,
        "records": records,
        "source_report": payload.get("report_path"),
    }
    slug = str(payload.get("deployment") or "active").replace("/", "_")
    captured = str(report.get("captured_at") or "now").replace(":", "").replace("-", "")
    out_path = out_dir / f"topology-{slug}-{captured}.json"
    try:
        out_path.write_text(json.dumps(out_payload, indent=2, sort_keys=True) + "\n")
    except OSError:
        return None
    return out_path


if __name__ == "__main__":
    raise SystemExit(main())
