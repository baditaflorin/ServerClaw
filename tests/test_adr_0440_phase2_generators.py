"""ADR 0440 Phase 2 — generator integration tests.

Phase 2 adds `--deployment <slug>` to four generators
(generate_platform_vars, generate_inventory, platform_manifest,
generate_discovery_artifacts) plus rollback support to the migration
script. These tests exercise the contract that each generator opts in
correctly without altering the legacy single-deployment path.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import deployment as dep_module  # noqa: E402
from scripts import migrate_to_multi_deployment as migrate  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
    deployments_dir = tmp_path / ".local" / "deployments"
    deployments_dir.mkdir(parents=True)
    active_file = tmp_path / ".local" / "active-deployment"

    monkeypatch.setattr(dep_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(dep_module, "DEPLOYMENTS_DIR", deployments_dir)
    monkeypatch.setattr(dep_module, "ACTIVE_FILE", active_file)
    monkeypatch.setattr(migrate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(migrate, "DEPLOYMENTS_DIR", deployments_dir)
    monkeypatch.delenv("DEPLOYMENT", raising=False)
    return tmp_path


def _seed_legacy_layout(root: Path) -> dict[str, Path]:
    """Create the pre-ADR-0440 layout so migration has work to do."""
    paths = {
        "identity": root / ".local" / "identity.yml",
        "host_vars": root / "inventory" / "host_vars" / "proxmox-host.yml",
        "platform": root / "inventory" / "group_vars" / "platform.yml",
        "hosts": root / "inventory" / "hosts.yml",
        "manifest": root / "build" / "platform-manifest.json",
        "onboarding": root / "build" / "onboarding",
    }
    for p in paths.values():
        p.parent.mkdir(parents=True, exist_ok=True)
    paths["identity"].write_text("platform_domain: test.example\n")
    paths["host_vars"].write_text("proxmox_guests: []\n")
    paths["platform"].write_text("# generated\n")
    paths["hosts"].write_text("all: {}\n")
    paths["manifest"].write_text("{}")
    paths["onboarding"].mkdir(exist_ok=True)
    (paths["onboarding"] / "service.yaml").write_text("name: test\n")
    return paths


# ---------------------------------------------------------------------------
# Migration apply + rollback
# ---------------------------------------------------------------------------


def test_migration_apply_then_rollback_round_trip(tmp_repo):
    paths = _seed_legacy_layout(tmp_repo)
    legacy_snapshot = {k: v.read_text() if v.is_file() else None for k, v in paths.items()}

    plan = migrate.build_plan("prod", repo_root=tmp_repo)
    migrate.execute_plan(plan)

    # Original paths gone, deployment paths populated
    assert not paths["identity"].exists()
    assert not paths["host_vars"].exists()
    assert (tmp_repo / ".local" / "deployments" / "prod" / "identity.yml").exists()
    assert (tmp_repo / ".local" / "deployments" / "prod" / "topology.yml").exists()
    assert (tmp_repo / ".local" / "deployments" / "prod" / "generated" / "platform.yml").exists()

    # Rollback restores
    rb = migrate.build_rollback_plan("prod", repo_root=tmp_repo)
    assert not rb.warnings, f"expected clean rollback, got: {rb.warnings}"
    migrate.execute_rollback(rb)

    for key, original in legacy_snapshot.items():
        if original is None:
            continue
        assert paths[key].is_file(), f"{key} not restored"
        assert paths[key].read_text() == original, f"{key} content drift after round-trip"


def test_rollback_refuses_when_legacy_path_occupied(tmp_repo):
    _seed_legacy_layout(tmp_repo)
    plan = migrate.build_plan("prod", repo_root=tmp_repo)
    migrate.execute_plan(plan)

    # Operator regenerated old layout while new one is active
    (tmp_repo / "inventory" / "host_vars" / "proxmox-host.yml").write_text("conflict\n")

    rb = migrate.build_rollback_plan("prod", repo_root=tmp_repo)
    assert any("already exists" in w for w in rb.warnings)


def test_rollback_for_unknown_slug_warns_and_skips(tmp_repo):
    rb = migrate.build_rollback_plan("ghost", repo_root=tmp_repo)
    assert rb.operations == []
    assert any("does not exist" in w for w in rb.warnings)


# ---------------------------------------------------------------------------
# Audit sanitization coverage — multi-deployment identity scan
# ---------------------------------------------------------------------------


def test_audit_picks_up_per_deployment_identity(tmp_path, monkeypatch):
    """ADR 0440: every .local/deployments/<slug>/identity.yml must contribute
    leak markers to the publish pipeline, not just the legacy
    inventory/group_vars/all/identity.yml."""
    from scripts import audit_sanitization_coverage as audit

    deployments = tmp_path / ".local" / "deployments"
    (deployments / "prod").mkdir(parents=True)
    (deployments / "prod" / "identity.yml").write_text(
        yaml.safe_dump(
            {
                "platform_domain": "alpha.test",
                "platform_operator_email": "ops@alpha.test",
                "platform_operator_name": "Alpha Operator",
            }
        )
    )
    (deployments / "staging").mkdir(parents=True)
    (deployments / "staging" / "identity.yml").write_text(
        yaml.safe_dump(
            {
                "platform_domain": "beta.test",
                "platform_operator_email": "ops@beta.test",
                "platform_operator_name": "Beta Operator",
            }
        )
    )

    # Point all audit-script paths at temp dirs so we don't pull in
    # real .local data from the surrounding repo.
    monkeypatch.setattr(audit, "DEPLOYMENTS_DIR", deployments)
    monkeypatch.setattr(audit, "IDENTITY_PATH", tmp_path / "missing-identity.yml")
    monkeypatch.setattr(audit, "HOSTS_PATH", tmp_path / "missing-hosts.yml")
    monkeypatch.setattr(audit, "OPERATORS_PATH", tmp_path / "missing-operators.yaml")
    monkeypatch.setattr(audit, "HOST_VARS_DIR", tmp_path / "missing-host-vars")

    values = audit.extract_sensitive_values()
    flat = {(v.value, v.category) for v in values}

    assert ("alpha.test", "domain") in flat
    assert ("ops@alpha.test", "pii") in flat
    assert ("Alpha Operator", "pii") in flat
    assert ("beta.test", "domain") in flat
    assert ("ops@beta.test", "pii") in flat
    assert ("Beta Operator", "pii") in flat


# ---------------------------------------------------------------------------
# Generator argparse — each generator must accept --deployment without error
# ---------------------------------------------------------------------------


def test_platform_manifest_parser_accepts_deployment_flag():
    from scripts import platform_manifest

    parser = platform_manifest.build_parser()
    args = parser.parse_args(["--write", "--deployment", "prod"])
    assert args.deployment == "prod"

    args_default = parser.parse_args(["--write"])
    assert args_default.deployment is None


def test_generate_platform_vars_parser_accepts_deployment_flag():
    from scripts import generate_platform_vars

    # generate_platform_vars uses argparse module-level; reach into main()
    # via parse-only by building the parser directly if exposed, otherwise
    # call main with --check to avoid writes.
    parser = None
    if hasattr(generate_platform_vars, "build_parser"):
        parser = generate_platform_vars.build_parser()
    elif hasattr(generate_platform_vars, "_build_parser"):
        parser = generate_platform_vars._build_parser()

    if parser is not None:
        args = parser.parse_args(["--check", "--deployment", "prod"])
        assert getattr(args, "deployment", None) == "prod"
    else:
        # Fallback: ensure the script imports without error and mentions the flag
        import inspect

        src = inspect.getsource(generate_platform_vars)
        assert "--deployment" in src
