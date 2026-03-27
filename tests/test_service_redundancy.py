import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import service_redundancy  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_repo_catalog_validates() -> None:
    catalog = service_redundancy.load_redundancy_catalog()
    service_redundancy.validate_redundancy_catalog(catalog)

    service_ids = set(catalog["services"])
    assert "postgres" in service_ids
    assert "headscale" in service_ids
    assert "docs_portal" in service_ids
    assert len(service_ids) >= 36


def test_show_service_renders_expected_summary() -> None:
    catalog = service_redundancy.load_redundancy_catalog()
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exit_code = service_redundancy.show_service(catalog, "postgres")
    output = buffer.getvalue()

    assert exit_code == 0
    assert "Service: postgres" in output
    assert "Tier: R2" in output
    assert "Standby Kind: warm" in output
    assert "Standby Location: postgres-replica-lv3" in output


def test_live_apply_plan_distinguishes_primary_only_and_warm_standby() -> None:
    catalog = service_redundancy.load_redundancy_catalog()

    postgres_plan = service_redundancy.build_live_apply_plan(catalog, service_id="postgres")
    headscale_plan = service_redundancy.build_live_apply_plan(catalog, service_id="headscale")

    assert postgres_plan == [
        {
            "service_id": "postgres",
            "declared_tier": "R2",
            "effective_tier": "R2",
            "live_apply_mode": "primary_and_standby",
            "standby_kind": "warm",
            "standby_location": "postgres-replica-lv3",
        }
    ]
    assert headscale_plan == [
        {
            "service_id": "headscale",
            "declared_tier": "R0",
            "effective_tier": "R0",
            "live_apply_mode": "primary_only",
            "standby_kind": "none",
            "standby_location": "none",
        }
    ]


def test_effective_tier_rejects_unsupported_r3_without_fallback() -> None:
    with pytest.raises(ValueError, match="exceeds the current platform limit R2"):
        service_redundancy.effective_tier("R3", "R2")

    assert service_redundancy.effective_tier("R3", "R2", allow_fallback=True) == "R2"


def test_validate_catalog_requires_full_service_coverage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    service_catalog_path = tmp_path / "config" / "service-capability-catalog.json"
    host_vars_path = tmp_path / "inventory" / "host_vars" / "proxmox_florin.yml"

    _write_json(
        service_catalog_path,
        {
            "$schema": "docs/schema/service-capability-catalog.schema.json",
            "schema_version": "1.0.0",
            "services": [
                {
                    "id": "alpha",
                    "name": "Alpha",
                    "description": "Test service alpha.",
                    "category": "automation",
                    "lifecycle_status": "active",
                    "vm": "alpha-vm",
                    "exposure": "private-only",
                    "environments": {"production": {"status": "active", "url": "http://alpha.local"}},
                },
                {
                    "id": "beta",
                    "name": "Beta",
                    "description": "Test service beta.",
                    "category": "automation",
                    "lifecycle_status": "active",
                    "vm": "beta-vm",
                    "exposure": "private-only",
                    "environments": {"production": {"status": "active", "url": "http://beta.local"}},
                },
            ],
        },
    )
    _write_yaml(
        host_vars_path,
        "proxmox_guests:\n"
        "  - name: alpha-vm\n"
        "  - name: beta-vm\n",
    )

    monkeypatch.setattr(service_redundancy, "SERVICE_CATALOG_PATH", service_catalog_path)
    monkeypatch.setattr(service_redundancy, "HOST_VARS_PATH", host_vars_path)

    catalog = {
        "$schema": "docs/schema/service-redundancy-catalog.schema.json",
        "schema_version": "1.0.0",
        "platform": {
            "failure_domain_count": 1,
            "max_supported_tier": "R2",
            "notes": ["single-host test platform"],
        },
        "services": {
            "alpha": {
                "tier": "R1",
                "recovery_objective": {"rto_minutes": 30, "rpo_minutes": 60},
                "backup_sources": ["git_repository"],
                "standby": {
                    "kind": "cold",
                    "location": "alpha-vm",
                    "failover_trigger": "restore alpha",
                    "failback_method": "replay alpha",
                },
            }
        },
    }

    with pytest.raises(ValueError, match="missing services: beta"):
        service_redundancy.validate_redundancy_catalog(catalog)


def test_validate_catalog_rejects_wrong_standby_kind(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    service_catalog_path = tmp_path / "config" / "service-capability-catalog.json"
    host_vars_path = tmp_path / "inventory" / "host_vars" / "proxmox_florin.yml"

    _write_json(
        service_catalog_path,
        {
            "$schema": "docs/schema/service-capability-catalog.schema.json",
            "schema_version": "1.0.0",
            "services": [
                {
                    "id": "postgres",
                    "name": "Postgres",
                    "description": "Test postgres service.",
                    "category": "data",
                    "lifecycle_status": "active",
                    "vm": "postgres-vm",
                    "exposure": "private-only",
                    "environments": {"production": {"status": "active", "url": "postgres://postgres.local:5432"}},
                }
            ],
        },
    )
    _write_yaml(
        host_vars_path,
        "proxmox_guests:\n"
        "  - name: postgres-vm\n"
        "  - name: postgres-replica-vm\n",
    )

    monkeypatch.setattr(service_redundancy, "SERVICE_CATALOG_PATH", service_catalog_path)
    monkeypatch.setattr(service_redundancy, "HOST_VARS_PATH", host_vars_path)

    catalog = {
        "$schema": "docs/schema/service-redundancy-catalog.schema.json",
        "schema_version": "1.0.0",
        "platform": {
            "failure_domain_count": 1,
            "max_supported_tier": "R2",
            "notes": ["single-host test platform"],
        },
        "services": {
            "postgres": {
                "tier": "R2",
                "recovery_objective": {"rto_minutes": 1, "rpo_minutes": 0},
                "backup_sources": ["patroni_replication"],
                "standby": {
                    "kind": "cold",
                    "location": "postgres-replica-vm",
                    "failover_trigger": "promote replica",
                    "failback_method": "resync old primary",
                },
            }
        },
    }

    with pytest.raises(ValueError, match="must be 'warm' for tier R2"):
        service_redundancy.validate_redundancy_catalog(catalog)
