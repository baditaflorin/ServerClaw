from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "audit_sanitization_coverage.py"
spec = importlib.util.spec_from_file_location("audit_sanitization_coverage", SCRIPT_PATH)
audit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = audit
assert spec.loader is not None
spec.loader.exec_module(audit)


def test_generic_public_dns_resolvers_are_not_deployment_leaks(tmp_path, monkeypatch) -> None:
    host_vars = tmp_path / "host_vars"
    host_vars.mkdir()
    (host_vars / "platform-host.yml").write_text(
        "nameservers: [1.1.1.1, 8.8.8.8]\nmanagement_ip: 203.0.113.1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(audit, "HOST_VARS_DIR", host_vars)
    monkeypatch.setattr(audit, "IDENTITY_PATH", tmp_path / "missing-identity.yml")
    monkeypatch.setattr(audit, "HOSTS_PATH", tmp_path / "missing-hosts.yml")
    monkeypatch.setattr(audit, "OPERATORS_PATH", tmp_path / "missing-operators.yml")
    monkeypatch.setattr(audit, "DEPLOYMENTS_DIR", tmp_path / "missing-deployments")

    values = audit.extract_sensitive_values()

    assert [(value.value, value.severity) for value in values] == [("203.0.113.1", "CRITICAL")]


def test_publication_deployments_dir_can_be_read_from_main_checkout(tmp_path, monkeypatch) -> None:
    local_deployments = tmp_path / "main-checkout" / ".local" / "deployments"
    local_deployments.mkdir(parents=True)
    monkeypatch.setenv(audit.DEPLOYMENTS_DIR_ENV, str(local_deployments))

    assert audit.resolve_deployments_dir(tmp_path / "fresh-worktree") == local_deployments


def test_publication_deployments_dir_override_must_be_absolute_and_exist(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(audit.DEPLOYMENTS_DIR_ENV, ".local/deployments")
    with pytest.raises(ValueError, match="absolute path"):
        audit.resolve_deployments_dir(tmp_path / "fresh-worktree")

    missing = tmp_path / "missing-deployments"
    monkeypatch.setenv(audit.DEPLOYMENTS_DIR_ENV, str(missing))
    with pytest.raises(FileNotFoundError):
        audit.resolve_deployments_dir(tmp_path / "fresh-worktree")
