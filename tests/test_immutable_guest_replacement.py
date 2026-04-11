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

import immutable_guest_replacement  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_repo_catalog_validates() -> None:
    catalog = immutable_guest_replacement.load_guest_replacement_catalog()
    immutable_guest_replacement.validate_guest_replacement_catalog(catalog)

    guests = set(catalog["guests"])
    assert guests == {
        "backup-lv3",
        "docker-build-lv3",
        "docker-runtime-lv3",
        "monitoring-lv3",
        "nginx-lv3",
        "postgres-lv3",
    }


def test_build_service_plan_flags_grafana_and_skips_headscale() -> None:
    catalog = immutable_guest_replacement.load_guest_replacement_catalog()

    grafana_plan = immutable_guest_replacement.build_service_plan(catalog, "grafana")
    headscale_plan = immutable_guest_replacement.build_service_plan(catalog, "headscale")

    assert grafana_plan["immutable_guest_replacement"] is True
    assert grafana_plan["guest"] == "monitoring-lv3"
    assert grafana_plan["validation_mode"] == "preview_guest"
    assert grafana_plan["classification"] == "edge_and_stateful"

    assert headscale_plan["immutable_guest_replacement"] is False
    assert "not governed" in headscale_plan["reason"]


def test_check_live_apply_rejects_without_override() -> None:
    catalog = immutable_guest_replacement.load_guest_replacement_catalog()

    with pytest.raises(ValueError, match="grafana -> monitoring-lv3"):
        immutable_guest_replacement.check_live_apply(
            catalog,
            service_id="grafana",
            allow_in_place_mutation=False,
        )


def test_check_live_apply_accepts_documented_override() -> None:
    catalog = immutable_guest_replacement.load_guest_replacement_catalog()
    buffer = io.StringIO()

    with redirect_stdout(buffer):
        exit_code = immutable_guest_replacement.check_live_apply(
            catalog,
            service_id="grafana",
            allow_in_place_mutation=True,
        )

    output = buffer.getvalue()
    assert exit_code == 0
    assert "override: grafana remains governed" in output


def test_validate_catalog_requires_r2_for_warm_standby(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    guest_catalog_path = tmp_path / "config" / "immutable-guest-replacement-catalog.json"
    service_catalog_path = tmp_path / "config" / "service-capability-catalog.json"
    redundancy_catalog_path = tmp_path / "config" / "service-redundancy-catalog.json"
    host_vars_path = tmp_path / "inventory" / "host_vars" / "proxmox_florin.yml"

    _write_json(
        guest_catalog_path,
        {
            "$schema": "docs/schema/immutable-guest-replacement-catalog.schema.json",
            "schema_version": "1.0.0",
            "platform": {
                "default_exception_rule": "document the exception",
                "notes": ["test platform"],
            },
            "guests": {
                "alpha-vm": {
                    "classification": "stateful",
                    "validation_mode": "warm_standby",
                    "cutover_method": "promote the standby",
                    "rollback_window_minutes": 60,
                    "rollback_method": "switch back",
                }
            },
        },
    )
    _write_json(
        service_catalog_path,
        {
            "$schema": "docs/schema/service-capability-catalog.schema.json",
            "schema_version": "1.0.0",
            "services": [
                {
                    "id": "alpha",
                    "name": "Alpha",
                    "description": "Test alpha service.",
                    "category": "data",
                    "lifecycle_status": "active",
                    "vm": "alpha-vm",
                    "exposure": "private-only",
                    "environments": {"production": {"status": "active", "url": "http://alpha.local"}},
                }
            ],
        },
    )
    _write_json(
        redundancy_catalog_path,
        {
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
        },
    )
    _write_yaml(
        host_vars_path,
        "proxmox_guests:\n  - name: alpha-vm\n    vmid: 210\n    role: alpha\n    template_key: alpha-template\n",
    )

    monkeypatch.setattr(immutable_guest_replacement, "IMMUTABLE_GUEST_REPLACEMENT_PATH", guest_catalog_path)
    monkeypatch.setattr(immutable_guest_replacement, "HOST_VARS_PATH", host_vars_path)
    monkeypatch.setattr(immutable_guest_replacement.service_redundancy, "SERVICE_CATALOG_PATH", service_catalog_path)
    monkeypatch.setattr(
        immutable_guest_replacement.service_redundancy, "SERVICE_REDUNDANCY_PATH", redundancy_catalog_path
    )

    catalog = immutable_guest_replacement.load_guest_replacement_catalog()
    with pytest.raises(
        ValueError, match="warm_standby requires at least one hosted service at redundancy tier R2 or higher"
    ):
        immutable_guest_replacement.validate_guest_replacement_catalog(catalog)


def test_rag_context_alias_resolves_to_platform_context_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        immutable_guest_replacement.service_redundancy,
        "load_service_catalog_index",
        lambda: {
            "platform_context_api": {
                "id": "platform_context_api",
                "name": "Platform Context API",
                "vm": "docker-runtime-lv3",
                "exposure": "private-only",
            }
        },
    )
    monkeypatch.setattr(
        immutable_guest_replacement.service_redundancy,
        "load_redundancy_catalog",
        lambda: {
            "services": {
                "platform_context_api": {
                    "tier": "R0",
                    "standby": {
                        "kind": "none",
                        "location": "none",
                        "failover_trigger": "rerun converge",
                        "failback_method": "rerun converge",
                    },
                }
            }
        },
    )

    plan = immutable_guest_replacement.build_service_plan({"guests": {}}, "rag-context")

    assert plan["service_id"] == "platform_context_api"
    assert plan["immutable_guest_replacement"] is False
