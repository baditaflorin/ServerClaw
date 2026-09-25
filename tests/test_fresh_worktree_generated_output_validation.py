from pathlib import Path

import pytest

import validate_dns_declarations
import validate_nginx_config
import validate_sso_clients


def test_dns_validator_skips_missing_deployment_output_after_registry_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(validate_dns_declarations, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(validate_dns_declarations, "DNS_DECLARATIONS_PATH", tmp_path / "missing.yml")
    monkeypatch.setattr(validate_dns_declarations, "load_registry", lambda: {})

    assert validate_dns_declarations.main(["--check"]) == 0
    assert "Skipping derived DNS declarations equality check" in capsys.readouterr().out


def test_dns_validator_rejects_present_malformed_deployment_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(validate_dns_declarations, "REPO_ROOT", tmp_path)
    declarations_path = tmp_path / "dns-declarations.yaml"
    declarations_path.write_text("dns_records: [\n")
    monkeypatch.setattr(validate_dns_declarations, "DNS_DECLARATIONS_PATH", declarations_path)
    monkeypatch.setattr(validate_dns_declarations, "load_registry", lambda: {})

    assert validate_dns_declarations.main(["--check"]) == 1


def test_sso_validator_skips_missing_deployment_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(validate_sso_clients, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(validate_sso_clients, "SSO_CLIENTS_PATH", tmp_path / "missing.yml")

    assert validate_sso_clients.main(["--check"]) == 0
    assert "Skipping derived SSO clients equality check" in capsys.readouterr().out


def test_sso_validator_rejects_present_malformed_deployment_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(validate_sso_clients, "REPO_ROOT", tmp_path)
    clients_path = tmp_path / "sso-clients.yaml"
    clients_path.write_text("sso_clients: [\n")
    monkeypatch.setattr(validate_sso_clients, "SSO_CLIENTS_PATH", clients_path)

    assert validate_sso_clients.main(["--check"]) == 1


def test_nginx_validator_skips_missing_deployment_output_after_source_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(validate_nginx_config, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(validate_nginx_config, "REGISTRY_PATH", tmp_path / "registry.yml")
    monkeypatch.setattr(validate_nginx_config, "SUBDOMAIN_CATALOG_PATH", tmp_path / "subdomains.json")
    monkeypatch.setattr(validate_nginx_config, "NGINX_UPSTREAMS_YAML", tmp_path / "missing.yml")
    monkeypatch.setattr(validate_nginx_config, "_load_registry", lambda: {})
    monkeypatch.setattr(validate_nginx_config, "_load_subdomain_catalog", lambda: {})

    assert validate_nginx_config.main(["--check"]) == 0
    assert "Skipping derived nginx upstreams equality check" in capsys.readouterr().out


def test_nginx_validator_rejects_present_drifted_deployment_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(validate_nginx_config, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(validate_nginx_config, "REGISTRY_PATH", tmp_path / "registry.yml")
    monkeypatch.setattr(validate_nginx_config, "SUBDOMAIN_CATALOG_PATH", tmp_path / "subdomains.json")
    upstreams_path = tmp_path / "nginx-upstreams.yaml"
    upstreams_path.write_text(
        "platform_nginx_upstreams:\n"
        "  - service_name: stale\n"
        "    fqdn: stale.example.com\n"
        "    extra_fqdns: []\n"
        "    port: 8080\n"
    )
    monkeypatch.setattr(validate_nginx_config, "NGINX_UPSTREAMS_YAML", upstreams_path)
    monkeypatch.setattr(validate_nginx_config, "_load_registry", lambda: {})
    monkeypatch.setattr(validate_nginx_config, "_load_subdomain_catalog", lambda: {})

    assert validate_nginx_config.main(["--check"]) == 1
