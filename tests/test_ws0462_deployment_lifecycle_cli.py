"""Tests for ADR 0459 — deployment.py lifecycle CLI subcommands.

Covers:
  - `use --slug <slug>` writes .local/active-deployment when slug exists.
  - `use --slug <unknown>` fails with exit 2 and a helpful message.
  - `use` rejects malformed slugs (validates pattern).
  - `new --slug <slug> --apex <domain>` scaffolds the four canonical files.
  - `new` refuses to overwrite an existing deployment.
  - `new` parses `--operator "Name <email>"` correctly.
  - `bind --slug <slug>` writes .deployment marker in the worktree root.
  - `bind` refuses unknown slugs.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT_SCRIPT = REPO_ROOT / "scripts" / "deployment.py"


def _load_module(repo_root_override: Path):
    spec = importlib.util.spec_from_file_location("deployment_for_ws0462", DEPLOYMENT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["deployment_for_ws0462"] = module
    spec.loader.exec_module(module)
    module.REPO_ROOT = repo_root_override
    module.DEPLOYMENTS_DIR = repo_root_override / ".local" / "deployments"
    module.ACTIVE_FILE = repo_root_override / ".local" / "active-deployment"
    module.DEPLOYMENTS_DIR.mkdir(parents=True, exist_ok=True)
    return module


@pytest.fixture
def synthetic_repo(tmp_path):
    return tmp_path


# --- use -------------------------------------------------------------------


def test_use_writes_active_deployment_marker(synthetic_repo):
    mod = _load_module(synthetic_repo)
    (mod.DEPLOYMENTS_DIR / "alpha").mkdir(parents=True)
    rc = mod.main(["use", "--slug", "alpha"])
    assert rc == 0
    assert mod.ACTIVE_FILE.read_text().strip() == "alpha"


def test_use_rejects_unknown_slug(synthetic_repo):
    mod = _load_module(synthetic_repo)
    rc = mod.main(["use", "--slug", "missing"])
    assert rc == 2


def test_use_rejects_malformed_slug(synthetic_repo):
    mod = _load_module(synthetic_repo)
    rc = mod.main(["use", "--slug", "Bad-Slug"])  # capitals not allowed
    assert rc == 2


# --- new -------------------------------------------------------------------


def test_new_scaffolds_four_canonical_files(synthetic_repo):
    mod = _load_module(synthetic_repo)
    rc = mod.main(["new", "--slug", "alpha", "--apex", "alpha.invalid"])
    assert rc == 0
    root = mod.DEPLOYMENTS_DIR / "alpha"
    assert (root / "identity.yml").is_file()
    assert (root / "topology.yml").is_file()
    assert (root / "profile.yml").is_file()
    assert (root / "connection.yml").is_file()
    assert (root / "generated").is_dir()
    assert (root / "secrets").is_dir()
    assert (root / "receipts").is_dir()
    assert (root / "state").is_dir()


def test_new_refuses_overwrite(synthetic_repo):
    mod = _load_module(synthetic_repo)
    (mod.DEPLOYMENTS_DIR / "alpha").mkdir(parents=True)
    rc = mod.main(["new", "--slug", "alpha", "--apex", "alpha.invalid"])
    assert rc == 2


def test_new_parses_operator_name_email(synthetic_repo):
    mod = _load_module(synthetic_repo)
    rc = mod.main(
        ["new", "--slug", "alpha", "--apex", "alpha.invalid", "--operator", "Jane Doe <jane@alpha.invalid>"]
    )
    assert rc == 0
    identity = (mod.DEPLOYMENTS_DIR / "alpha" / "identity.yml").read_text()
    assert "platform_operator_name: Jane Doe" in identity
    assert "platform_operator_email: jane@alpha.invalid" in identity


def test_new_falls_back_to_placeholder_email(synthetic_repo):
    mod = _load_module(synthetic_repo)
    rc = mod.main(["new", "--slug", "alpha", "--apex", "alpha.invalid"])
    assert rc == 0
    identity = (mod.DEPLOYMENTS_DIR / "alpha" / "identity.yml").read_text()
    assert "TODO@alpha.invalid" in identity


# --- bind ------------------------------------------------------------------


def test_bind_writes_deployment_marker(synthetic_repo, monkeypatch):
    mod = _load_module(synthetic_repo)
    (mod.DEPLOYMENTS_DIR / "alpha").mkdir(parents=True)
    # Set up a fake worktree root: directory containing .git
    worktree = synthetic_repo / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: /fake\n")
    monkeypatch.chdir(worktree)
    rc = mod.main(["bind", "--slug", "alpha"])
    assert rc == 0
    assert (worktree / ".deployment").read_text().strip() == "alpha"


def test_bind_rejects_unknown_slug(synthetic_repo):
    mod = _load_module(synthetic_repo)
    rc = mod.main(["bind", "--slug", "missing"])
    assert rc == 2
