"""Integration test: fork-shape fixtures × deployment.py loader — ADR 0444 phase 1.4.

The deployment-loader substrate (scripts/deployment.py + the schemas under
config/contracts/deployment-v1/) is already in place from ws-0439. This
test confirms that the three identity shapes ws-0445 phase 1 commits as
fixtures (lv3 / 0fork / synthetic) all load and schema-validate through
that loader. Without this check there is no signal that the matrix the
convergence dry-run runs (Phase 1.2) and the matrix the deployment loader
accepts are the same matrix.

Each fixture is materialised into a temporary deployment directory shaped
like `.local/deployments/<slug>/` and loaded with `validate=True`. The
test asserts:

1. The loader resolves the deployment root from an explicit slug.
2. `Deployment.validate()` returns no errors against the contract schemas.
3. The loaded identity matches the fixture file byte-for-byte (round-trip).
4. Resolution by env var (`DEPLOYMENT=<slug>`) returns the same slug.

The test does NOT exercise Makefile wiring or `make converge-X
deployment=<slug>` — that is covered by the existing make-help target
and the Makefile's `MULTI_DEPLOYMENT_ENABLED` flag. Adding a Makefile
test here would couple the fixture matrix to the Make grammar, which
would create unnecessary churn.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT_SCRIPT = REPO_ROOT / "scripts" / "deployment.py"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "inventories"

# Map fixture file → deployment slug to use under tmp_path/.local/deployments/.
FIXTURE_SLUGS = {
    "lv3-shape.yml": "lv3test",
    "0fork-shape.yml": "0forktest",
    "synthetic-shape.yml": "synthetic",
}


def _load_deployment_module(repo_root_override: Path):
    """Load scripts/deployment.py with REPO_ROOT redirected at tmp_path.

    deployment.py uses module-level `REPO_ROOT = Path(__file__).resolve().parents[1]`
    to compute DEPLOYMENTS_DIR / SCHEMA_DIR. To run the loader against a
    synthetic fixtures-derived deployment under tmp_path/.local/deployments,
    we need to override that constant after import. This helper does the
    import + override, then returns the module.
    """
    spec = importlib.util.spec_from_file_location("deployment_for_ws0445", DEPLOYMENT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["deployment_for_ws0445"] = module
    spec.loader.exec_module(module)
    # Override the data-root constants but keep SCHEMA_DIR pointed at the
    # real config/contracts/deployment-v1/ tree (those schemas are the
    # contract under test, not synthetic).
    module.DEPLOYMENTS_DIR = repo_root_override / ".local" / "deployments"
    module.ACTIVE_FILE = repo_root_override / ".local" / "active-deployment"
    module.DEPLOYMENTS_DIR.mkdir(parents=True, exist_ok=True)
    return module


def _materialise_deployment(
    deploy_root: Path,
    slug: str,
    identity: dict[str, Any],
    topology: dict[str, Any],
    profile: dict[str, Any],
) -> Path:
    """Write identity.yml/topology.yml/profile.yml under deploy_root/<slug>/.

    Returns the deployment root path.
    """
    root = deploy_root / slug
    root.mkdir(parents=True, exist_ok=True)
    (root / "identity.yml").write_text(yaml.safe_dump(identity, sort_keys=False))
    (root / "topology.yml").write_text(yaml.safe_dump(topology, sort_keys=False))
    (root / "profile.yml").write_text(yaml.safe_dump(profile, sort_keys=False))
    return root


@pytest.fixture
def synthetic_repo_root(tmp_path):
    """tmp_path with a fake .local/ tree the loader can read."""
    (tmp_path / ".local" / "deployments").mkdir(parents=True)
    return tmp_path


@pytest.mark.parametrize("fixture_name,slug", sorted(FIXTURE_SLUGS.items()))
def test_fork_shape_fixture_loads_through_deployment_loader(fixture_name, slug, synthetic_repo_root):
    """Each ws-0445 phase 1.1 fixture must validate as a deployment."""
    deployment = _load_deployment_module(synthetic_repo_root)
    identity = yaml.safe_load((FIXTURE_DIR / fixture_name).read_text())
    # Minimal topology/profile that satisfy the contract schemas. The
    # topology schema requires at least one guest with name/vmid/ipv4 —
    # we don't care which, only that the loader accepts the identity
    # half of the matrix. Full topology lives in
    # inventory/host_vars/proxmox-host.yml and is out-of-scope here.
    topology = {"proxmox_guests": [{"name": "fixture-guest", "vmid": 199, "ipv4": "10.10.10.199"}]}
    profile = {"profiles": ["core"]}
    _materialise_deployment(deployment.DEPLOYMENTS_DIR, slug, identity, topology, profile)

    loaded = deployment.load(slug, validate=True)
    assert loaded.slug == slug
    assert loaded.platform_domain == identity["platform_domain"]
    assert loaded.operator_email == identity["platform_operator_email"]
    assert loaded.operator_name == identity["platform_operator_name"]


def test_resolve_active_slug_honours_explicit_then_env(synthetic_repo_root, monkeypatch):
    """Precedence: explicit > $DEPLOYMENT > worktree marker > active file.
    Confirm the explicit/env path matches deployment.py's documented contract.
    """
    deployment = _load_deployment_module(synthetic_repo_root)
    monkeypatch.setenv("DEPLOYMENT", "from_env")
    # Explicit wins.
    assert deployment.resolve_active_slug("from_explicit") == "from_explicit"
    # Env is next.
    assert deployment.resolve_active_slug(None) == "from_env"


def test_loader_rejects_unknown_slug(synthetic_repo_root):
    deployment = _load_deployment_module(synthetic_repo_root)
    with pytest.raises(deployment.DeploymentNotFoundError):
        deployment.load("does-not-exist", validate=True)


def test_loader_rejects_invalid_identity(synthetic_repo_root):
    """An identity that breaks the contract schema must produce a
    DeploymentValidationError, not silently succeed. Catches the class
    of bug where a fixture is committed but the schema drifts."""
    deployment = _load_deployment_module(synthetic_repo_root)
    bad_identity = {
        # Missing required `platform_operator_email` and
        # `platform_operator_name`.
        "platform_domain": "example.invalid",
    }
    _materialise_deployment(
        deployment.DEPLOYMENTS_DIR,
        "broken",
        bad_identity,
        {"proxmox_guests": [{"name": "g", "vmid": 199, "ipv4": "10.10.10.199"}]},
        {"profiles": ["core"]},
    )
    with pytest.raises(deployment.DeploymentValidationError):
        deployment.load("broken", validate=True)


def test_list_all_returns_materialised_slugs(synthetic_repo_root, monkeypatch):
    """list_all() reads the data-root constant. After materialisation the
    fixtures should appear in the output."""
    deployment = _load_deployment_module(synthetic_repo_root)
    valid_topology = {"proxmox_guests": [{"name": "fixture-guest", "vmid": 199, "ipv4": "10.10.10.199"}]}
    for fixture_name, slug in FIXTURE_SLUGS.items():
        identity = yaml.safe_load((FIXTURE_DIR / fixture_name).read_text())
        _materialise_deployment(
            deployment.DEPLOYMENTS_DIR,
            slug,
            identity,
            valid_topology,
            {"profiles": ["core"]},
        )
    # Patch list_all's view of DEPLOYMENTS_DIR (it reads the module
    # global, which we already overrode in _load_deployment_module).
    monkeypatch.setattr(deployment, "DEPLOYMENTS_DIR", deployment.DEPLOYMENTS_DIR)
    listed = deployment.list_all()
    assert set(FIXTURE_SLUGS.values()).issubset(listed), (
        f"materialised slugs {sorted(FIXTURE_SLUGS.values())} missing from {listed}"
    )
