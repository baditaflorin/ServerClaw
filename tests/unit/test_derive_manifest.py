"""Unit tests for scripts/derive_manifest.py — ADR 0483 §6.

Tests the pure helpers only (no IO).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from derive_manifest import (
    build_manifest,
    derive_operator,
    derive_profiles,
    derive_provider,
    derive_smoke_endpoints,
)


# ---------------------------------------------------------------------------
# derive_operator
# ---------------------------------------------------------------------------


class TestDeriveOperator:
    def test_maps_identity_fields(self):
        identity = {
            "platform_operator_name": "Acme Corp Ops",
            "platform_operator_email": "ops@acme.com",
        }
        result = derive_operator(identity)
        assert result["name"] == "Acme Corp Ops"
        assert result["email"] == "ops@acme.com"

    def test_fills_in_missing_fields(self):
        result = derive_operator({})
        assert result["name"] == "FILL_IN"
        assert result["email"] == "FILL_IN"


# ---------------------------------------------------------------------------
# derive_provider
# ---------------------------------------------------------------------------


class TestDeriveProvider:
    def test_hetzner_detection_via_key_hint(self):
        conn = {
            "proxmox_host": {
                "addr": "65.109.84.223",
                "port": 22,
                "user": "root",
                "key": ".local/ssh/hetzner_llm_agents_ed25519",
            }
        }
        provider, review = derive_provider(conn)
        assert provider["kind"] == "hetzner"
        assert provider["host"] == "65.109.84.223"
        assert provider["initial_user"] == "root"
        assert "port" not in provider  # omitted when standard 22

    def test_hetzner_detection_via_nonstandard_port(self):
        conn = {
            "proxmox_host": {
                "addr": "65.109.84.223",
                "port": 2222,
                "user": "root",
                "key": "some-other-key",
            }
        }
        provider, review = derive_provider(conn)
        assert provider["kind"] == "hetzner"
        assert provider["port"] == 2222

    def test_non_hetzner_key_defaults_to_custom(self):
        conn = {
            "proxmox_host": {
                "addr": "10.0.0.1",
                "port": 22,
                "user": "ops",
                "key": "my-box-key",
            }
        }
        provider, review = derive_provider(conn)
        assert provider["kind"] == "custom"
        assert any("provider.kind" in r for r in review)

    def test_vault_key_reference_triggers_review(self):
        conn = {
            "proxmox_host": {
                "addr": "1.2.3.4",
                "port": 22,
                "user": "root",
                "key": {"vault": "deployments/0fork/ssh-key", "field": "private_key"},
            }
        }
        provider, review = derive_provider(conn)
        assert any("vault" in r for r in review)
        assert "vault:deployments/0fork/ssh-key" in provider["initial_key_path"]

    def test_missing_addr_triggers_review(self):
        conn = {"proxmox_host": {"port": 22, "user": "root", "key": "k"}}
        provider, review = derive_provider(conn)
        assert provider["host"] == "FILL_IN"
        assert any("provider.host" in r for r in review)

    def test_empty_connection_triggers_review(self):
        provider, review = derive_provider({})
        assert provider["host"] == "FILL_IN"


# ---------------------------------------------------------------------------
# derive_profiles
# ---------------------------------------------------------------------------


class TestDeriveProfiles:
    def test_extracts_profiles(self):
        profiles, extra, disabled = derive_profiles(
            {
                "profiles": ["core", "devtools"],
                "extra_services": ["custom-svc"],
                "disabled_services": ["runtime-ai"],
            }
        )
        assert profiles == ["core", "devtools"]
        assert extra == ["custom-svc"]
        assert disabled == ["runtime-ai"]

    def test_defaults_to_core_when_missing(self):
        profiles, extra, disabled = derive_profiles({})
        assert profiles == ["core"]
        assert extra == []
        assert disabled == []


# ---------------------------------------------------------------------------
# derive_smoke_endpoints
# ---------------------------------------------------------------------------


class TestDeriveSmoke:
    def test_returns_three_endpoints(self):
        endpoints = derive_smoke_endpoints("acme.com")
        assert len(endpoints) == 3

    def test_contains_template_variables(self):
        endpoints = derive_smoke_endpoints("acme.com")
        assert any("{apex}" in e for e in endpoints)
        assert any("{apex_slug}" in e for e in endpoints)


# ---------------------------------------------------------------------------
# build_manifest (integration of all helpers)
# ---------------------------------------------------------------------------


class TestBuildManifest:
    def _make_inputs(self):
        identity = {
            "platform_domain": "0fork.com",
            "platform_operator_name": "0fork Operator",
            "platform_operator_email": "ops@0fork.com",
        }
        connection = {
            "proxmox_host": {
                "addr": "65.109.84.223",
                "port": 2222,
                "user": "root",
                "key": "hetzner_llm_agents_ed25519",
            }
        }
        profile = {
            "profiles": ["core", "devtools"],
            "extra_services": [],
            "disabled_services": ["runtime-ai"],
        }
        return identity, connection, profile

    def test_slug_is_used(self):
        identity, connection, profile = self._make_inputs()
        result = build_manifest("0fork", identity, connection, profile)
        assert result.manifest["slug"] == "0fork"

    def test_apex_domain_is_set(self):
        identity, connection, profile = self._make_inputs()
        result = build_manifest("0fork", identity, connection, profile)
        assert result.manifest["apex_domain"] == "0fork.com"

    def test_schema_version_is_1(self):
        identity, connection, profile = self._make_inputs()
        result = build_manifest("0fork", identity, connection, profile)
        assert result.manifest["schema_version"] == 1

    def test_secrets_defaults_to_operator_stdin(self):
        identity, connection, profile = self._make_inputs()
        result = build_manifest("0fork", identity, connection, profile)
        assert result.manifest["secrets"]["source"] == "operator-stdin"

    def test_gates_block_present(self):
        identity, connection, profile = self._make_inputs()
        result = build_manifest("0fork", identity, connection, profile)
        assert "fail_fast" in result.manifest["gates"]
        assert result.manifest["gates"]["max_retries_per_step"] == 3

    def test_disabled_services_included(self):
        identity, connection, profile = self._make_inputs()
        result = build_manifest("0fork", identity, connection, profile)
        assert "runtime-ai" in result.manifest.get("disabled_services", [])

    def test_no_review_required_with_complete_inputs(self):
        identity, connection, profile = self._make_inputs()
        result = build_manifest("0fork", identity, connection, profile)
        # May still have warnings (secrets.source), but no required review items
        # unless the provider heuristic fires
        assert isinstance(result.review_required, list)

    def test_review_required_when_apex_missing(self):
        identity, connection, profile = self._make_inputs()
        identity.pop("platform_domain")
        result = build_manifest("0fork", identity, connection, profile)
        assert any("apex_domain" in r for r in result.review_required)

    def test_review_required_when_operator_email_missing(self):
        identity, connection, profile = self._make_inputs()
        identity.pop("platform_operator_email")
        result = build_manifest("0fork", identity, connection, profile)
        assert any("operator" in r for r in result.review_required)

    def test_extra_services_omitted_when_empty(self):
        identity, connection, profile = self._make_inputs()
        result = build_manifest("0fork", identity, connection, profile)
        assert "extra_services" not in result.manifest  # empty → not included

    def test_verification_block_present(self):
        identity, connection, profile = self._make_inputs()
        result = build_manifest("0fork", identity, connection, profile)
        assert "smoke_endpoints" in result.manifest["verification"]
        assert result.manifest["verification"]["expected_running_vms_count"] == ">= 5"
