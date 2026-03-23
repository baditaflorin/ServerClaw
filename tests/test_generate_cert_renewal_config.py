from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import generate_cert_renewal_config as generator  # noqa: E402


def test_build_plan_splits_managed_and_unmanaged_entries(monkeypatch) -> None:
    monkeypatch.setattr(
        generator,
        "load_certificate_catalog",
        lambda: [
            {
                "id": "openbao-proxy",
                "service_id": "openbao",
                "status": "active",
                "renewal": {
                    "agent": "systemd-step-issue",
                    "managed_by_repo": True,
                    "host": "docker-runtime-lv3",
                    "unit_name": "lv3-openbao-cert-renew",
                    "on_calendar": "*:0/15",
                    "randomized_delay_seconds": 60,
                    "reload_command": "docker compose restart openbao",
                },
                "material": {
                    "certificate_file": "/opt/openbao/tls/server.crt",
                    "key_file": "/opt/openbao/tls/server.key",
                    "root_file": "/opt/step-ca/home/certs/root_ca.crt",
                    "subject": "100.118.189.95",
                    "sans": ["10.10.10.20", "100.118.189.95"],
                    "ca_url": "https://10.10.10.20:9000",
                    "provisioner": "services",
                    "password_file": "/opt/step-ca/secrets/services-password.txt",
                    "not_after": "24h",
                },
            },
            {
                "id": "grafana-edge",
                "service_id": "grafana",
                "status": "active",
                "renewal": {
                    "agent": "certbot-dns-hetzner",
                    "managed_by_repo": False,
                },
            },
        ],
    )

    plan = generator.build_plan()

    assert [item["certificate_id"] for item in plan["timers"]] == ["openbao-proxy"]
    assert [item["certificate_id"] for item in plan["unmanaged"]] == ["grafana-edge"]
