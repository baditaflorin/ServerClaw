from __future__ import annotations

import json
from pathlib import Path

import deployment_history
import jsonschema


def test_collect_live_apply_entries_prefers_explicit_service_ids(tmp_path: Path) -> None:
    receipts_dir = tmp_path / "receipts" / "live-applies"
    receipts_dir.mkdir(parents=True)
    receipt_id = "2026-10-12-explicit-service-scope"
    (receipts_dir / f"{receipt_id}.json").write_text(
        json.dumps(
            {
                "receipt_id": receipt_id,
                "recorded_on": "2026-10-12",
                "recorded_by": "codex",
                "workflow_id": "live-apply-service",
                "summary": "Verified docker-build container health for the artifact cache.",
                "targets": [{"kind": "vm", "name": "docker-build"}],
                "verification": [
                    {
                        "check": "Docker build and container health",
                        "observed": "The artifact cache container responded.",
                    }
                ],
                "service_ids": ["artifact_cache", "docker_build"],
            }
        ),
        encoding="utf-8",
    )
    service_catalog = {
        "services": [
            {"id": "artifact_cache", "name": "Artifact Cache", "tags": ["container", "cache"]},
            {"id": "docker_build", "name": "Docker Build VM", "vm": "docker-build", "tags": ["container", "build"]},
            {"id": "librechat", "name": "LibreChat", "tags": ["container", "build"]},
        ]
    }

    entries = deployment_history.collect_live_apply_entries(receipts_dir=receipts_dir, service_catalog=service_catalog)

    assert len(entries) == 1
    assert entries[0]["service_ids"] == ["artifact_cache", "docker_build"]


def test_infrastructure_receipt_can_explicitly_deploy_no_service(tmp_path: Path) -> None:
    receipt = {
        "schema_version": "1.0.0",
        "receipt_id": "2026-11-06-host-journal-retention",
        "applied_on": "2026-11-06",
        "recorded_on": "2026-11-06",
        "recorded_by": "codex",
        "source_commit": "1a763555767dbb43783a33e556c55cc467d528a0",
        "workflow_id": "adr-0226-journal-retention-live-apply",
        "summary": "Bound local journals on the Docker host; no application was deployed.",
        "targets": [{"kind": "bare-metal", "name": "docker-host"}],
        "verification": [{"check": "Journal cap", "result": "pass", "observed": "1 GiB"}],
        "service_ids": [],
    }
    schema_path = Path(__file__).resolve().parents[1] / "docs/schema/live-apply-receipt.schema.json"
    jsonschema.validate(receipt, json.loads(schema_path.read_text()))
    (tmp_path / f"{receipt['receipt_id']}.json").write_text(json.dumps(receipt))

    catalog = {"services": [{"id": "example_app", "name": "Example", "tags": ["docker", "host"]}]}
    entries = deployment_history.collect_live_apply_entries(receipts_dir=tmp_path, service_catalog=catalog)

    assert entries[0]["service_ids"] == []
    assert entries[0]["service_names"] == []
