from pathlib import Path

import yaml

import scripts.generate_platform_vars as generate_platform_vars


def write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_load_optional_cross_cutting_generated_inputs_returns_empty_when_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        generate_platform_vars, "CROSS_CUTTING_DNS_DECLARATIONS_PATH", tmp_path / "config/generated/dns.yml"
    )
    monkeypatch.setattr(
        generate_platform_vars, "CROSS_CUTTING_NGINX_UPSTREAMS_PATH", tmp_path / "config/generated/nginx.yml"
    )
    monkeypatch.setattr(generate_platform_vars, "CROSS_CUTTING_SSO_CLIENTS_PATH", tmp_path / "config/generated/sso.yml")
    monkeypatch.setattr(
        generate_platform_vars, "CROSS_CUTTING_HAIRPIN_PATH", tmp_path / "inventory/group_vars/hairpin.yml"
    )
    monkeypatch.setattr(
        generate_platform_vars, "CROSS_CUTTING_TLS_CERTS_PATH", tmp_path / "inventory/group_vars/tls.yml"
    )

    assert generate_platform_vars.load_optional_cross_cutting_generated_inputs() == {
        "dns_declarations": {},
        "nginx_upstreams": [],
        "sso_clients": {},
        "hairpin_hosts": [],
        "tls_certs": {},
    }


def test_load_optional_cross_cutting_generated_inputs_reads_generated_files(tmp_path, monkeypatch) -> None:
    dns_path = tmp_path / "config/generated/dns.yml"
    nginx_path = tmp_path / "config/generated/nginx.yml"
    sso_path = tmp_path / "config/generated/sso.yml"
    hairpin_path = tmp_path / "inventory/group_vars/hairpin.yml"
    tls_path = tmp_path / "inventory/group_vars/tls.yml"

    write_yaml(dns_path, {"dns_records": {"chat.example.com": {"service": "librechat", "target_host": "nginx"}}})
    write_yaml(
        nginx_path,
        {"platform_nginx_upstreams": [{"service_name": "librechat", "fqdn": "chat.example.com", "ip": "10.10.10.70"}]},
    )
    write_yaml(sso_path, {"sso_clients": {"serverclaw": {"service": "librechat", "provider": "keycloak"}}})
    write_yaml(
        hairpin_path,
        {"platform_hairpin_nat_hosts": [{"hostname": "chat.example.com", "address": "10.10.10.10"}]},
    )
    write_yaml(
        tls_path, {"platform_tls_certs": {"chat.example.com": {"service": "librechat", "source": "letsencrypt"}}}
    )

    monkeypatch.setattr(generate_platform_vars, "CROSS_CUTTING_DNS_DECLARATIONS_PATH", dns_path)
    monkeypatch.setattr(generate_platform_vars, "CROSS_CUTTING_NGINX_UPSTREAMS_PATH", nginx_path)
    monkeypatch.setattr(generate_platform_vars, "CROSS_CUTTING_SSO_CLIENTS_PATH", sso_path)
    monkeypatch.setattr(generate_platform_vars, "CROSS_CUTTING_HAIRPIN_PATH", hairpin_path)
    monkeypatch.setattr(generate_platform_vars, "CROSS_CUTTING_TLS_CERTS_PATH", tls_path)

    payload = generate_platform_vars.load_optional_cross_cutting_generated_inputs()

    assert payload["dns_declarations"]["chat.example.com"]["service"] == "librechat"
    assert payload["nginx_upstreams"][0]["fqdn"] == "chat.example.com"
    assert payload["sso_clients"]["serverclaw"]["provider"] == "keycloak"
    assert payload["hairpin_hosts"][0] == {"hostname": "chat.example.com", "address": "10.10.10.10"}
    assert payload["tls_certs"]["chat.example.com"]["source"] == "letsencrypt"
