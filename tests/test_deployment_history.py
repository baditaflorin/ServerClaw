from __future__ import annotations

import json
from pathlib import Path

import deployment_history


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
