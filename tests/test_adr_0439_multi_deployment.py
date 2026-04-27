"""ADR 0439/0440/0441 — multi-deployment loader & resolver tests.

Phase 1 tests cover:
  - resolve_active_slug precedence chain (explicit > env > marker > active-file > error)
  - Deployment.load with valid + invalid YAML
  - Profile resolver: composition, extends graph, extra/disabled, requires_services closure
  - Migration plan dry-run produces sensible operations

These tests do not touch the real .local/ directory. Each test runs against
a tmp_path fixture so concurrent tests cannot collide.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Import deployment.py directly so tests can monkeypatch DEPLOYMENTS_DIR/ACTIVE_FILE.
from scripts import deployment as dep_module  # noqa: E402


@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
    """Re-root the deployment module at a temp directory."""
    deployments_dir = tmp_path / ".local" / "deployments"
    deployments_dir.mkdir(parents=True)
    active_file = tmp_path / ".local" / "active-deployment"

    monkeypatch.setattr(dep_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(dep_module, "DEPLOYMENTS_DIR", deployments_dir)
    monkeypatch.setattr(dep_module, "ACTIVE_FILE", active_file)
    monkeypatch.delenv("DEPLOYMENT", raising=False)
    return tmp_path


def _write_deployment(
    root: Path, slug: str, *, identity: dict | None = None, topology: dict | None = None, profile: dict | None = None
) -> Path:
    import yaml

    d = root / ".local" / "deployments" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "identity.yml").write_text(
        yaml.safe_dump(
            identity
            or {
                "platform_domain": f"{slug}.example",
                "platform_operator_email": f"ops@{slug}.example",
                "platform_operator_name": f"{slug.title()} Operator",
            }
        )
    )
    (d / "topology.yml").write_text(
        yaml.safe_dump(
            topology
            or {
                "proxmox_guests": [
                    {"name": "host01", "vmid": 100, "ipv4": "10.10.10.10"},
                ],
            }
        )
    )
    (d / "profile.yml").write_text(
        yaml.safe_dump(
            profile
            or {
                "profiles": ["core"],
                "extra_services": [],
                "disabled_services": [],
                "service_overrides": {},
            }
        )
    )
    return d


# ---------------------------------------------------------------------------
# resolve_active_slug precedence
# ---------------------------------------------------------------------------


def test_resolve_explicit_wins(tmp_repo, monkeypatch):
    monkeypatch.setenv("DEPLOYMENT", "from-env")
    (tmp_repo / ".local" / "active-deployment").write_text("from-active-file\n")
    assert dep_module.resolve_active_slug("explicit-arg") == "explicit-arg"


def test_resolve_env_var_beats_active_file(tmp_repo, monkeypatch):
    monkeypatch.setenv("DEPLOYMENT", "from-env")
    (tmp_repo / ".local" / "active-deployment").write_text("from-active-file\n")
    assert dep_module.resolve_active_slug() == "from-env"


def test_resolve_active_file_when_no_env(tmp_repo):
    (tmp_repo / ".local" / "active-deployment").write_text("from-active-file\n")
    assert dep_module.resolve_active_slug() == "from-active-file"


def test_resolve_raises_when_nothing_set(tmp_repo):
    with pytest.raises(dep_module.DeploymentNotResolvedError):
        dep_module.resolve_active_slug()


def test_resolve_strips_whitespace(tmp_repo):
    (tmp_repo / ".local" / "active-deployment").write_text("  prod  \n")
    assert dep_module.resolve_active_slug() == "prod"


# ---------------------------------------------------------------------------
# Deployment.load
# ---------------------------------------------------------------------------


def test_load_returns_typed_deployment(tmp_repo):
    _write_deployment(tmp_repo, "prod")
    (tmp_repo / ".local" / "active-deployment").write_text("prod")
    d = dep_module.load(validate=False)
    assert d.slug == "prod"
    assert d.platform_domain == "prod.example"
    assert d.operator_email == "ops@prod.example"


def test_load_unknown_slug_raises(tmp_repo):
    with pytest.raises(dep_module.DeploymentNotFoundError):
        dep_module.load("ghost", validate=False)


def test_load_validates_minimal_required_keys(tmp_repo):
    # Identity missing platform_domain
    d = _write_deployment(
        tmp_repo,
        "broken",
        identity={
            "platform_operator_email": "ops@broken.example",
            "platform_operator_name": "Broken Op",
        },
    )
    deployment = dep_module.load("broken", validate=False)
    errors = deployment._validate_minimal()
    assert any("platform_domain" in e for e in errors)


def test_list_all_returns_sorted_slugs(tmp_repo):
    _write_deployment(tmp_repo, "zeta")
    _write_deployment(tmp_repo, "alpha")
    _write_deployment(tmp_repo, "mid")
    assert dep_module.list_all() == ["alpha", "mid", "zeta"]


def test_list_all_ignores_dotfiles(tmp_repo):
    _write_deployment(tmp_repo, "real")
    (tmp_repo / ".local" / "deployments" / ".hidden").mkdir()
    assert dep_module.list_all() == ["real"]


# ---------------------------------------------------------------------------
# Profile resolver (ADR 0441)
# ---------------------------------------------------------------------------


def test_profile_closure_simple():
    catalog = {
        "core": {"services": ["postgres", "openbao"]},
        "identity": {"extends": ["core"], "services": ["gitea", "harbor"]},
    }
    services = dep_module._profile_closure("identity", catalog)
    assert services == {"postgres", "openbao", "gitea", "harbor"}


def test_profile_closure_unknown_profile():
    with pytest.raises(dep_module.DeploymentValidationError, match="Unknown profile"):
        dep_module._profile_closure("ghost", {})


def test_profile_closure_detects_cycle():
    catalog = {
        "a": {"extends": ["b"], "services": []},
        "b": {"extends": ["a"], "services": []},
    }
    with pytest.raises(dep_module.DeploymentValidationError, match="cycle"):
        dep_module._profile_closure("a", catalog)


def test_resolve_enabled_services_with_extras_and_disabled(tmp_repo):
    catalog = {
        "core": {"services": ["postgres", "openbao", "alertmanager"]},
    }
    registry = {
        "postgres": {},
        "openbao": {},
        "alertmanager": {},
        "outline": {"requires_services": ["postgres", "minio"]},
        "minio": {},
    }
    _write_deployment(
        tmp_repo,
        "test",
        profile={
            "profiles": ["core"],
            "extra_services": ["outline"],
            "disabled_services": ["alertmanager"],
            "service_overrides": {},
        },
    )
    d = dep_module.load("test", validate=False)
    enabled = dep_module.resolve_enabled_services(d, profile_catalog=catalog, service_registry=registry)
    assert enabled == {"postgres", "openbao", "outline", "minio"}
    assert "alertmanager" not in enabled


def test_resolve_enabled_services_blocks_disabling_required_dep(tmp_repo):
    catalog = {"core": {"services": ["outline"]}}
    registry = {
        "outline": {"requires_services": ["minio"]},
        "minio": {},
    }
    _write_deployment(
        tmp_repo,
        "test",
        profile={
            "profiles": ["core"],
            "extra_services": [],
            "disabled_services": ["minio"],
            "service_overrides": {},
        },
    )
    d = dep_module.load("test", validate=False)
    with pytest.raises(dep_module.DeploymentValidationError, match="requires 'minio'"):
        dep_module.resolve_enabled_services(d, profile_catalog=catalog, service_registry=registry)


def test_resolve_enabled_services_walks_transitive_requires(tmp_repo):
    catalog = {"core": {"services": ["a"]}}
    registry = {
        "a": {"requires_services": ["b"]},
        "b": {"requires_services": ["c"]},
        "c": {},
    }
    _write_deployment(tmp_repo, "test")
    d = dep_module.load("test", validate=False)
    enabled = dep_module.resolve_enabled_services(d, profile_catalog=catalog, service_registry=registry)
    assert enabled == {"a", "b", "c"}


# ---------------------------------------------------------------------------
# Migration script (dry-run)
# ---------------------------------------------------------------------------


def test_migration_dry_run_plans_operator_authored_moves(tmp_repo, monkeypatch):
    # Re-root the migration module's REPO_ROOT to the tmp dir.
    from scripts import migrate_to_multi_deployment as mig

    monkeypatch.setattr(mig, "REPO_ROOT", tmp_repo)
    monkeypatch.setattr(mig, "DEPLOYMENTS_DIR", tmp_repo / ".local" / "deployments")

    # Place a fake old-layout identity.yml
    (tmp_repo / ".local").mkdir(parents=True, exist_ok=True)
    (tmp_repo / ".local" / "identity.yml").write_text("platform_domain: test.example\n")
    # And a fake old-layout proxmox-host.yml
    (tmp_repo / "inventory" / "host_vars").mkdir(parents=True, exist_ok=True)
    (tmp_repo / "inventory" / "host_vars" / "proxmox-host.yml").write_text("proxmox_guests: []\n")

    plan = mig.build_plan("prod", repo_root=tmp_repo)
    op_kinds = {op.kind for op in plan.operations}
    assert "move" in op_kinds
    assert "synthesise" in op_kinds  # profile.yml stub
    assert "write" in op_kinds  # active-deployment marker

    # Operator-authored sources end up at the right destinations
    by_dst = {op.dst.name: op for op in plan.operations if op.kind == "move"}
    assert "identity.yml" in by_dst
    assert "topology.yml" in by_dst


def test_migration_apply_executes_when_legacy_layout_exists(tmp_repo, monkeypatch):
    """Phase 2: --apply is no longer gated; it executes the migration."""
    from scripts import migrate_to_multi_deployment as mig

    monkeypatch.setattr(mig, "REPO_ROOT", tmp_repo)
    monkeypatch.setattr(mig, "DEPLOYMENTS_DIR", tmp_repo / ".local" / "deployments")
    (tmp_repo / "inventory" / "host_vars").mkdir(parents=True, exist_ok=True)
    (tmp_repo / "inventory" / "host_vars" / "proxmox-host.yml").write_text("proxmox_guests: []\n")
    (tmp_repo / ".local").mkdir(exist_ok=True)
    (tmp_repo / ".local" / "identity.yml").write_text("platform_domain: t.example\n")

    rc = mig.main(["--apply", "--slug", "prod"])
    assert rc == 0
    assert (tmp_repo / ".local" / "deployments" / "prod" / "identity.yml").exists()
    assert (tmp_repo / ".local" / "deployments" / "prod" / "topology.yml").exists()


# ---------------------------------------------------------------------------
# Advisory lock
# ---------------------------------------------------------------------------


def test_deployment_lock_serialises_same_kind(tmp_repo):
    from scripts.deployment_lock import DeploymentLocked, deployment_lock

    _write_deployment(tmp_repo, "prod")

    with deployment_lock("prod", kind="converge"):
        with pytest.raises(DeploymentLocked):
            with deployment_lock("prod", kind="converge"):
                pass


def test_deployment_lock_independent_kinds(tmp_repo):
    from scripts.deployment_lock import deployment_lock

    _write_deployment(tmp_repo, "prod")

    with deployment_lock("prod", kind="converge"):
        # Different kind should not block
        with deployment_lock("prod", kind="generate"):
            pass


def test_deployment_lock_independent_deployments(tmp_repo):
    from scripts.deployment_lock import deployment_lock

    _write_deployment(tmp_repo, "prod")
    _write_deployment(tmp_repo, "fork")

    with deployment_lock("prod", kind="converge"):
        # Different deployment should not block — this is the property that
        # makes parallel multi-deployment work.
        with deployment_lock("fork", kind="converge"):
            pass
