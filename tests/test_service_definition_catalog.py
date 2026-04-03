from pathlib import Path
import sys
import tempfile

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import service_definition_catalog  # noqa: E402


def test_repo_service_definition_catalog_matches_generated_aggregates() -> None:
    assert service_definition_catalog.main(["--check"]) == 0


def test_bundle_directory_name_must_match_service_id() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        bundle_root = Path(tmp) / "catalog" / "services"
        bundle_root.mkdir(parents=True)
        (bundle_root / "_metadata.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": "1.0.0",
                    "outputs": {
                        "service_capability_catalog": {
                            "path": "config/service-capability-catalog.json",
                            "top_level": {
                                "$schema": "docs/schema/service-capability-catalog.schema.json",
                                "schema_version": "1.0.0",
                            },
                        },
                        "health_probe_catalog": {
                            "path": "config/health-probe-catalog.json",
                            "top_level": {"schema_version": "1.0.0"},
                        },
                        "service_completeness": {
                            "path": "config/service-completeness.json",
                            "top_level": {
                                "$schema": "docs/schema/service-completeness.schema.json",
                                "schema_version": "1.0.0",
                                "suppression_presets": {},
                            },
                        },
                        "service_redundancy": {
                            "path": "config/service-redundancy-catalog.json",
                            "top_level": {
                                "$schema": "docs/schema/service-redundancy-catalog.schema.json",
                                "schema_version": "1.0.0",
                                "platform": {
                                    "failure_domain_count": 1,
                                    "max_supported_tier": "R2",
                                    "notes": ["fixture"],
                                    "rehearsal_gate": {
                                        "tiers": {
                                            "R1": {
                                                "exercise": "restore_to_preview",
                                                "freshness_window_days": 90,
                                            },
                                            "R2": {
                                                "exercise": "standby_switchover_or_promotion",
                                                "freshness_window_days": 30,
                                            },
                                            "R3": {
                                                "exercise": "cross_domain_failover",
                                                "freshness_window_days": 30,
                                            },
                                        }
                                    },
                                },
                            },
                        },
                        "dependency_graph": {
                            "path": "config/dependency-graph.json",
                            "top_level": {
                                "$schema": "docs/schema/service-dependency-graph.schema.json",
                                "schema_version": "1.0.0",
                            },
                        },
                        "data_catalog": {
                            "path": "config/data-catalog.json",
                            "top_level": {
                                "$schema": "docs/schema/data-catalog.schema.json",
                                "schema_version": "1.0.0",
                            },
                        },
                        "slo_catalog": {
                            "path": "config/slo-catalog.json",
                            "top_level": {
                                "$schema": "docs/schema/slo-catalog.schema.json",
                                "schema_version": "1.0.0",
                                "review_note": "fixture",
                            },
                        },
                    },
                },
                sort_keys=False,
            )
        )
        wrong_dir = bundle_root / "wrong"
        wrong_dir.mkdir()
        (wrong_dir / "service.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": "1.0.0",
                    "service": {
                        "id": "other",
                        "name": "Other",
                        "description": "Fixture service.",
                    },
                    "completeness": {
                        "service_type": "compose",
                        "requires_subdomain": False,
                        "requires_oidc": False,
                        "requires_secrets": False,
                        "requires_compose_secrets": False,
                    },
                    "redundancy": {
                        "tier": "R0",
                        "recovery_objective": {"rto_minutes": 10, "rpo_minutes": 10},
                        "backup_sources": ["git_repository"],
                        "standby": {
                            "kind": "none",
                            "location": "none",
                            "failover_trigger": "fixture",
                            "failback_method": "fixture",
                        },
                    },
                    "dependency": {
                        "node": {
                            "id": "other",
                            "service": "other",
                            "name": "Other",
                            "vm": "docker-runtime-lv3",
                            "tier": 1,
                        },
                        "outbound_edges": [],
                    },
                },
                sort_keys=False,
            )
        )

        try:
            service_definition_catalog.load_service_bundle_index(bundle_root=bundle_root)
        except ValueError as exc:
            assert "directory name" in str(exc)
        else:  # pragma: no cover - defensive failure path
            raise AssertionError("expected the directory/service id mismatch to fail")
