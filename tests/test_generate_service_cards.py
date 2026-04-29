"""Unit tests for scripts/generate_service_cards.py — ADR 0473 phase 11.1."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_service_cards.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_service_cards", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["generate_service_cards"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gsc():
    return _load_module()


def _make_service(tmp_path: Path, svc_id: str, payload: dict) -> Path:
    d = tmp_path / svc_id
    d.mkdir()
    (d / "service.yaml").write_text(yaml.safe_dump(payload))
    return d


def test_render_card_full(gsc):
    payload = {
        "service": {
            "id": "keycloak",
            "name": "Keycloak",
            "description": "SSO broker",
            "category": "access",
            "lifecycle_status": "active",
            "vm": "runtime-control",
            "internal_url": "http://10.10.10.92:8091",
            "tags": ["identity", "oidc"],
            "environments": {
                "production": {"status": "active", "url": "https://sso.example.com"},
                "staging": {"status": "planned", "url": "https://sso.staging.example.com"},
            },
        }
    }
    out = gsc.render_card(payload)
    assert "# Keycloak (`keycloak`)" in out
    assert "SSO broker" in out
    assert "**Category:** access" in out
    assert "identity, oidc" in out
    assert "production | active | https://sso.example.com" in out


def test_render_card_minimal(gsc):
    payload = {"service": {"id": "minimal"}}
    out = gsc.render_card(payload)
    assert "# minimal (`minimal`)" in out
    assert "## Identity" in out


def test_render_card_malformed(gsc):
    out = gsc.render_card({"service": "not-a-mapping"})
    assert "Malformed" in out


def test_render_index(gsc):
    out = gsc.render_index([("a", "Alpha"), ("b", "Beta")])
    assert "2 services indexed" in out
    assert "[Alpha (`a`)](a.md)" in out
    assert "[Beta (`b`)](b.md)" in out


def test_discover_services_empty(gsc, tmp_path):
    assert gsc.discover_services(tmp_path / "nope") == []


def test_discover_services_skips_dirs_without_service_yaml(gsc, tmp_path):
    (tmp_path / "yes").mkdir()
    (tmp_path / "yes" / "service.yaml").write_text("service: {id: yes}")
    (tmp_path / "no_yaml").mkdir()
    assert [p.name for p in gsc.discover_services(tmp_path)] == ["yes"]


def test_load_service_rejects_non_mapping(gsc, tmp_path):
    d = tmp_path / "bad"
    d.mkdir()
    (d / "service.yaml").write_text("- not-a-mapping")
    with pytest.raises(ValueError):
        gsc.load_service(d)


def test_write_or_check_writes(gsc, tmp_path):
    services_dir = tmp_path / "services"
    services_dir.mkdir()
    _make_service(services_dir, "alpha", {"service": {"id": "alpha", "name": "Alpha"}})
    output = tmp_path / "out"
    rc = gsc.write_or_check(output_dir=output, services_dir=services_dir, check=False)
    assert rc == 0
    assert (output / "alpha.md").is_file()
    assert (output / "index.md").is_file()


def test_write_or_check_check_clean(gsc, tmp_path):
    services_dir = tmp_path / "services"
    services_dir.mkdir()
    _make_service(services_dir, "alpha", {"service": {"id": "alpha", "name": "Alpha"}})
    output = tmp_path / "out"
    gsc.write_or_check(output_dir=output, services_dir=services_dir, check=False)
    rc = gsc.write_or_check(output_dir=output, services_dir=services_dir, check=True)
    assert rc == 0


def test_write_or_check_check_drift(gsc, tmp_path, capsys):
    services_dir = tmp_path / "services"
    services_dir.mkdir()
    _make_service(services_dir, "alpha", {"service": {"id": "alpha", "name": "Alpha"}})
    output = tmp_path / "out"
    output.mkdir()
    (output / "alpha.md").write_text("stale\n")
    rc = gsc.write_or_check(output_dir=output, services_dir=services_dir, check=True)
    assert rc == 1
    err = capsys.readouterr().err
    assert "stale" in err


def test_main_check_drift_returns_1(gsc, tmp_path, capsys):
    services_dir = tmp_path / "services"
    services_dir.mkdir()
    _make_service(services_dir, "alpha", {"service": {"id": "alpha", "name": "Alpha"}})
    output = tmp_path / "out"
    output.mkdir()
    rc = gsc.main(
        [
            "--services-dir",
            str(services_dir),
            "--output-dir",
            str(output),
            "--check",
        ]
    )
    assert rc == 1


def test_main_write_returns_0(gsc, tmp_path):
    services_dir = tmp_path / "services"
    services_dir.mkdir()
    _make_service(services_dir, "alpha", {"service": {"id": "alpha", "name": "Alpha"}})
    output = tmp_path / "out"
    rc = gsc.main(
        [
            "--services-dir",
            str(services_dir),
            "--output-dir",
            str(output),
        ]
    )
    assert rc == 0
    assert (output / "alpha.md").exists()
