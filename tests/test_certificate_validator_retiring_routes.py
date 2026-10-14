"""Regression tests for certificate checks versus public-route lifecycle."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_SCRIPT = REPO_ROOT / "scripts" / "certificate_validator.py"


def _load_validator_module():
    spec = importlib.util.spec_from_file_location("certificate_validator_retiring_routes", VALIDATOR_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_retiring_edge_host_is_excluded_but_active_edge_host_remains():
    validator = _load_validator_module()
    certificates = [
        {"fqdn": "n8n.example.com", "service_id": "n8n"},
        {"fqdn": "browser.example.com", "service_id": "neko"},
    ]
    subdomains = [
        {
            "fqdn": "n8n.example.com",
            "status": "retiring",
            "exposure": "edge-published",
        },
        {
            "fqdn": "browser.example.com",
            "status": "active",
            "exposure": "edge-published",
        },
    ]

    assert validator.exclude_retiring_edge_certificates(certificates, subdomains) == [
        {"fqdn": "browser.example.com", "service_id": "neko"}
    ]


def test_private_only_and_informational_hosts_are_not_retiring_edge_routes():
    validator = _load_validator_module()
    certificates = [
        {"fqdn": "vault.example.com", "service_id": "vaultwarden"},
        {"fqdn": "proxmox.example.com", "service_id": "proxmox_ui"},
    ]
    subdomains = [
        {
            "fqdn": "vault.example.com",
            "status": "retiring",
            "exposure": "private-only",
        },
        {
            "fqdn": "proxmox.example.com",
            "status": "retiring",
            "exposure": "informational-only",
        },
    ]

    assert validator.exclude_retiring_edge_certificates(certificates, subdomains) == certificates


def test_subdomain_fallback_preserves_retiring_status(tmp_path):
    validator = _load_validator_module()
    catalog = tmp_path / "subdomains.json"
    catalog.write_text(
        '{"subdomains": [{"fqdn": "n8n.example.com", "target": "203.0.113.7", '
        '"service_id": "n8n", "status": "retiring", "exposure": "edge-published"}]}'
    )

    entries = validator.load_subdomain_catalog(str(catalog))

    assert entries[0]["status"] == "retiring"
    assert entries[0]["exposure"] == "edge-published"
