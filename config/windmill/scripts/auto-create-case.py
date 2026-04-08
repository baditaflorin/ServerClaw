#!/usr/bin/env python3
"""ADR 0118 — Create a skeleton failure case from a GlitchTip or triage incident payload.

Windmill entrypoint: called automatically when GlitchTip (ADR 0061) opens an
incident or when the triage engine (ADR 0114) fires.  Can also be invoked
manually for incidents discovered outside the automated path.

Expected incident_payload keys (all optional except service identification):
    affected_service / service_id / service / project
    title / name
    symptoms                   list[str]
    summary / detail / message fallback symptom sources
    correlated_signals / signal_set   dict[str, Any]
    triage_report_id           str UUID
    ledger_event_ids           list[str UUID]
    first_observed_at          ISO-8601 timestamp
    incident_id / id / fingerprint

The function returns {"status": "ok", "case": <created_case_dict>} on success
or {"status": "blocked", "reason": "..."} when the repo checkout is missing.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any


def _load_case_store(repo_root: Path):
    """Import scripts/cases from the mounted repo checkout."""
    scripts_dir = str(repo_root / "scripts")
    if scripts_dir in sys.path:
        sys.path.remove(scripts_dir)
    sys.path.insert(0, scripts_dir)
    # Evict any stale module cached from a different path.
    existing = sys.modules.get("cases")
    if existing is not None and not str(
        getattr(existing, "__file__", "")
    ).startswith(scripts_dir):
        for name in list(sys.modules):
            if name == "cases" or name.startswith("cases."):
                del sys.modules[name]
    module = importlib.import_module("cases")
    return module.CaseStore(
        path=repo_root / ".local" / "state" / "cases" / "failure_cases.json"
    )


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Map an arbitrary incident payload to the canonical case-creation dict."""
    service_id = (
        payload.get("affected_service")
        or payload.get("service_id")
        or payload.get("service")
        or payload.get("project")
        or "unknown-service"
    )
    incident_id = (
        payload.get("incident_id")
        or payload.get("id")
        or payload.get("fingerprint")
    )
    title = payload.get("title") or payload.get("name") or f"{service_id} incident"

    symptoms = payload.get("symptoms")
    if not isinstance(symptoms, list):
        symptoms = []
        for field in ("summary", "detail", "message"):
            value = payload.get(field)
            if isinstance(value, str) and value.strip():
                symptoms.append(value.strip())

    correlated_signals = (
        payload.get("signal_set") or payload.get("correlated_signals") or {}
    )

    triage_report_id = payload.get("triage_report_id")
    if triage_report_id is None and isinstance(payload.get("triage_report"), dict):
        triage_report_id = payload["triage_report"].get("incident_id")

    return {
        "incident_id": incident_id,
        "title": str(title),
        "affected_service": str(service_id),
        "symptoms": symptoms,
        "correlated_signals": correlated_signals,
        "triage_report_id": triage_report_id,
        "ledger_event_ids": payload.get("ledger_event_ids", []),
        "first_observed_at": (
            payload.get("first_observed_at") or payload.get("started_at")
        ),
    }


# Windmill entrypoint — the function Windmill calls with the workflow inputs.
def main(
    incident_payload: dict[str, Any] | None = None,
    *,
    repo_path: str = "/srv/proxmox_florin_server",
) -> dict[str, Any]:
    repo_root = Path(repo_path)
    if not (repo_root / "scripts").exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }
    payload = incident_payload or {}
    if not isinstance(payload, dict) or not payload:
        return {"status": "blocked", "reason": "incident_payload is required"}
    store = _load_case_store(repo_root)
    case = store.create(_normalize_payload(payload))
    return {"status": "ok", "case": case}


# ------------------------------------------------------------------
# CLI wrapper for local testing / manual invocation
# ------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create an ADR 0118 failure case from an incident payload."
    )
    parser.add_argument(
        "--repo-path",
        default="/srv/proxmox_florin_server",
        help="Path to the repo checkout on this machine.",
    )
    parser.add_argument(
        "--payload-file",
        type=Path,
        required=True,
        help="JSON file containing the incident payload.",
    )
    return parser


if __name__ == "__main__":
    args = _build_parser().parse_args()
    payload = json.loads(args.payload_file.read_text(encoding="utf-8"))
    print(
        json.dumps(
            main(payload, repo_path=args.repo_path),
            indent=2,
            sort_keys=True,
        )
    )
