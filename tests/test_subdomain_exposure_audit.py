from __future__ import annotations

import json
import os
import shutil
import ssl
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import subdomain_exposure_audit as audit  # noqa: E402


class SubdomainExposureAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self._disable_overlay = patch.dict(os.environ, {"LV3_DISABLE_SHARED_LOCAL_IDENTITY": "1"})
        self._disable_overlay.start()
        self.addCleanup(self._disable_overlay.stop)

    def test_build_registry_resolves_placeholder_domains_for_private_overlay(self) -> None:
        catalog = {
            "subdomains": [
                {
                    "fqdn": "api.lv3.org",
                    "environment": "production",
                    "status": "active",
                    "owner_adr": "0371",
                    "exposure": "edge-published",
                    "auth_requirement": "none",
                    "target": "203.0.113.1",
                    "target_port": 443,
                    "tls": {"provider": "letsencrypt", "auto_renew": True},
                }
            ]
        }
        host_vars = {"lv3_service_topology": {}}
        public_edge_defaults = {
            "public_edge_authenticated_sites": {},
            "public_edge_extra_sites": [],
        }
        service_catalog = {
            "services": [
                {
                    "id": "api_gateway",
                    "environments": {
                        "production": {
                            "status": "active",
                            "url": "https://api.example.com",
                        }
                    },
                }
            ]
        }

        with (
            patch.object(audit.subdomain_catalog, "load_json", return_value=service_catalog),
            patch.object(
                audit.subdomain_catalog,
                "resolve_public_domain_placeholders",
                side_effect=_replace_example_domain,
            ),
            patch.object(
                audit.subdomain_catalog,
                "validate_subdomain_catalog",
                side_effect=lambda catalog, resolved_service_catalog, *_args: self.assertEqual(
                    resolved_service_catalog["services"][0]["environments"]["production"]["url"],
                    "https://api.lv3.org",
                ),
            ),
        ):
            registry = audit.build_registry(
                catalog=catalog,
                host_vars=host_vars,
                public_edge_defaults=public_edge_defaults,
            )

        self.assertEqual(registry["publications"][0]["fqdn"], "api.lv3.org")

    def test_load_certificate_catalog_resolves_placeholder_domains_for_private_overlay(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="certificate-catalog-"))
        try:
            certificate_catalog_path = temp_dir / "certificate-catalog.json"
            certificate_catalog_path.write_text(
                json.dumps(
                    {
                        "certificates": [
                            {
                                "endpoint": {
                                    "host": "docs.example.com",
                                    "server_name": "docs.example.com",
                                }
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            original = audit.CERTIFICATE_CATALOG_PATH
            audit.CERTIFICATE_CATALOG_PATH = certificate_catalog_path
            try:
                with patch.object(
                    audit.subdomain_catalog,
                    "resolve_public_domain_placeholders",
                    side_effect=_replace_example_domain,
                ):
                    certificate_catalog = audit.load_certificate_catalog()
            finally:
                audit.CERTIFICATE_CATALOG_PATH = original
        finally:
            shutil.rmtree(temp_dir)

        self.assertEqual(
            certificate_catalog["certificates"][0]["endpoint"]["host"],
            "docs.lv3.org",
        )

    def test_repo_registry_tracks_known_hostnames(self) -> None:
        registry = audit.build_registry()
        by_fqdn = {entry["fqdn"]: entry for entry in registry["publications"]}

        self.assertEqual(by_fqdn["example.com"]["adapter"]["routing"]["source"], "public_edge_apex")
        self.assertEqual(by_fqdn["example.com"]["adapter"]["dns"]["records"], [{"type": "A", "value": "203.0.113.1"}])
        self.assertEqual(by_fqdn["n8n.example.com"]["publication"]["access_model"], "platform-sso")
        self.assertEqual(
            by_fqdn["n8n.example.com"]["adapter"]["edge_auth"]["unauthenticated_prefix_paths"],
            ["/webhook/", "/webhook-test/", "/webhook-waiting/"],
        )
        self.assertEqual(by_fqdn["ops.example.com"]["publication"]["access_model"], "platform-sso")
        self.assertEqual(by_fqdn["ops.example.com"]["adapter"]["edge_auth"]["provider"], "oauth2_proxy")
        self.assertEqual(by_fqdn["docs.example.com"]["adapter"]["routing"]["source"], "public_edge_extra_sites")
        self.assertEqual(by_fqdn["database.example.com"]["publication"]["access_model"], "private-network")
        self.assertEqual(by_fqdn["vault.example.com"]["adapter"]["dns"]["visibility"], "tailnet")
        self.assertTrue(by_fqdn["vault.example.com"]["evidence_plan"]["private_route"])
        self.assertTrue(by_fqdn["changelog.example.com"]["live_tracking_expected"])
        self.assertGreater(registry["summary"]["active_total"], 0)

    def test_repo_findings_flag_edge_oidc_mismatch(self) -> None:
        registry = {
            "publications": [
                {
                    "fqdn": "ops.example.com",
                    "status": "active",
                    "publication": {"access_model": "platform-sso"},
                    "adapter": {"edge_auth": {"provider": "none"}},
                }
            ]
        }

        findings = audit.collect_repo_findings(
            registry,
            certificate_catalog={"certificates": []},
            edge_certificate_domains=set(),
        )

        self.assertEqual(findings[0]["severity"], "CRITICAL")
        self.assertIn("platform-sso", findings[0]["detail"])

    def test_repo_findings_ignore_planned_edge_oidc_routes(self) -> None:
        registry = {
            "publications": [
                {
                    "fqdn": "ops.staging.example.com",
                    "status": "planned",
                    "publication": {"access_model": "platform-sso"},
                    "adapter": {"edge_auth": {"provider": "none"}},
                }
            ]
        }

        findings = audit.collect_repo_findings(
            registry,
            certificate_catalog={"certificates": []},
            edge_certificate_domains=set(),
        )

        self.assertEqual(findings, [])

    def test_repo_findings_flag_missing_certificate_catalog_entry_for_public_hostname(self) -> None:
        registry = {
            "zone_name": "example.com",
            "publications": [
                {
                    "fqdn": "docs.example.com",
                    "service_id": "docs_portal",
                    "status": "active",
                    "environment": "production",
                    "publication": {"access_model": "platform-sso", "delivery_model": "shared-edge"},
                    "adapter": {
                        "edge_auth": {"provider": "oauth2_proxy"},
                        "tls": {"provider": "letsencrypt"},
                    },
                }
            ],
        }

        findings = audit.collect_repo_findings(
            registry,
            certificate_catalog={"certificates": []},
            edge_certificate_domains={"docs.example.com"},
        )

        self.assertEqual(findings[0]["check"], "certificate_plan")
        self.assertEqual(findings[0]["severity"], "CRITICAL")
        self.assertEqual(findings[0]["finding"], "catalog_public_hostname_missing_from_certificate_catalog")

    def test_repo_findings_flag_public_certificate_catalog_entry_without_catalogued_hostname(self) -> None:
        registry = {
            "zone_name": "example.com",
            "publications": [],
        }

        findings = audit.collect_repo_findings(
            registry,
            certificate_catalog={
                "certificates": [
                    {
                        "id": "docs-edge",
                        "service_id": "docs_portal",
                        "endpoint": {
                            "host": "docs.example.com",
                            "port": 443,
                            "server_name": "docs.example.com",
                        },
                    }
                ]
            },
            edge_certificate_domains=set(),
        )

        self.assertEqual(findings[0]["finding"], "certificate_catalog_public_hostname_missing_from_endpoint_catalog")

    def test_repo_findings_flag_shared_edge_hostname_missing_from_rendered_certificate_domains(self) -> None:
        registry = {
            "zone_name": "example.com",
            "publications": [
                {
                    "fqdn": "ops.example.com",
                    "service_id": "ops_portal",
                    "status": "active",
                    "environment": "production",
                    "publication": {"access_model": "platform-sso", "delivery_model": "shared-edge"},
                    "adapter": {
                        "edge_auth": {"provider": "oauth2_proxy"},
                        "tls": {"provider": "letsencrypt"},
                    },
                }
            ],
        }

        findings = audit.collect_repo_findings(
            registry,
            certificate_catalog={
                "certificates": [
                    {
                        "id": "ops-edge",
                        "service_id": "ops_portal",
                        "expected_issuer": "letsencrypt",
                        "endpoint": {
                            "host": "ops.example.com",
                            "port": 443,
                            "server_name": "ops.example.com",
                        },
                    }
                ]
            },
            edge_certificate_domains=set(),
        )

        self.assertEqual(findings[0]["finding"], "catalog_public_hostname_missing_from_shared_edge_certificate_domains")

    def test_zone_findings_compare_full_record_sets(self) -> None:
        registry = {
            "zone_name": "example.com",
            "publications": [
                {
                    "fqdn": "example.com",
                    "environment": "production",
                    "status": "active",
                    "publication": {"delivery_model": "informational-edge"},
                    "adapter": {
                        "dns": {
                            "records": [{"type": "A", "value": "203.0.113.1"}],
                            "zone_expected": True,
                        }
                    },
                }
            ],
        }

        findings = audit.collect_zone_findings(
            registry,
            [
                {"name": "@", "type": "A", "value": "203.0.113.1"},
                {"name": "@", "type": "AAAA", "value": "2a01:db8::1"},
            ],
        )

        self.assertEqual(findings[0]["finding"], "zone_record_differs_from_catalog")
        self.assertIn("Unexpected", findings[0]["detail"])

    def test_resolution_findings_flag_planned_but_live(self) -> None:
        registry = {
            "publications": [
                {
                    "fqdn": "docs.example.com",
                    "environment": "production",
                    "status": "planned",
                    "publication": {"delivery_model": "shared-edge"},
                    "adapter": {
                        "dns": {
                            "target": "203.0.113.1",
                            "records": [{"type": "A", "value": "203.0.113.1"}],
                            "zone_expected": True,
                        }
                    },
                }
            ]
        }

        original = audit.resolve_public_records
        audit.resolve_public_records = lambda fqdn: ["203.0.113.1"]
        try:
            findings = audit.collect_resolution_findings(registry)
        finally:
            audit.resolve_public_records = original

        self.assertEqual(findings[0]["severity"], "CRITICAL")
        self.assertEqual(findings[0]["finding"], "subdomain_resolves_publicly_but_is_not_tracked_active")

    def test_http_auth_findings_flag_missing_redirect(self) -> None:
        registry = {
            "publications": [
                {
                    "fqdn": "ops.example.com",
                    "status": "active",
                    "environment": "production",
                    "publication": {"access_model": "platform-sso"},
                }
            ]
        }

        original = audit.http_probe
        audit.http_probe = lambda url: (200, "https://ops.example.com/", {})
        try:
            findings = audit.collect_http_auth_findings(registry)
        finally:
            audit.http_probe = original

        self.assertEqual(findings[0]["severity"], "CRITICAL")
        self.assertIn("Keycloak", findings[0]["detail"])

    def test_tls_findings_record_hostname_mismatch_without_crashing(self) -> None:
        registry = {
            "publications": [
                {
                    "fqdn": "mail.example.com",
                    "status": "active",
                    "environment": "production",
                    "adapter": {
                        "tls": {"provider": "letsencrypt"},
                        "dns": {"target_port": 443},
                    },
                }
            ]
        }

        original = audit.fetch_tls_metadata
        audit.fetch_tls_metadata = lambda hostname, **kwargs: {
            "expires_at": "2026-04-30T00:00:00Z",
            "seconds_remaining": 30 * 86400,
            "hours_remaining": 30 * 24,
            "days_remaining": 30,
            "issuer": "CN=Test",
            "verification_error": "hostname mismatch",
        }
        try:
            findings = audit.collect_tls_findings(registry)
        finally:
            audit.fetch_tls_metadata = original

        self.assertEqual(findings[0]["severity"], "CRITICAL")
        self.assertEqual(findings[0]["finding"], "certificate_hostname_mismatch")
        self.assertIn("hostname mismatch", findings[0]["detail"])

    def test_private_route_findings_record_unreachable_targets(self) -> None:
        registry = {
            "publications": [
                {
                    "fqdn": "database.example.com",
                    "evidence_plan": {"private_route": True},
                    "adapter": {"dns": {"target": "100.64.0.1", "target_port": 5432}},
                }
            ]
        }

        original = audit.socket.create_connection

        def fail_connect(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise OSError("timed out")

        audit.socket.create_connection = fail_connect
        try:
            findings = audit.collect_private_route_findings(registry)
        finally:
            audit.socket.create_connection = original

        self.assertEqual(findings[0]["severity"], "CRITICAL")
        self.assertEqual(findings[0]["finding"], "private_route_unreachable")
        self.assertIn("100.64.0.1:5432", findings[0]["detail"])

    def test_tls_findings_record_probe_failures_without_crashing(self) -> None:
        registry = {
            "publications": [
                {
                    "fqdn": "mail.example.com",
                    "status": "active",
                    "environment": "production",
                    "adapter": {
                        "tls": {"provider": "letsencrypt"},
                        "dns": {"target_port": 443},
                    },
                }
            ]
        }

        original = audit.fetch_tls_metadata

        def fail_probe(hostname: str, **kwargs) -> dict[str, object]:
            raise ssl.SSLError("certificate verify failed")

        audit.fetch_tls_metadata = fail_probe
        try:
            findings = audit.collect_tls_findings(registry)
        finally:
            audit.fetch_tls_metadata = original

        self.assertEqual(findings[0]["severity"], "CRITICAL")
        self.assertEqual(findings[0]["finding"], "tls_probe_failed")
        self.assertIn("certificate verify failed", findings[0]["detail"])

    def test_tls_findings_ignore_short_lived_step_ca_certs_outside_renew_window(self) -> None:
        registry = {
            "publications": [
                {
                    "fqdn": "vault.example.com",
                    "status": "active",
                    "environment": "production",
                    "adapter": {
                        "tls": {"provider": "step-ca", "auto_renew": True},
                        "dns": {"target": "100.64.0.1", "target_port": 443},
                    },
                    "publication": {"delivery_model": "private-network"},
                }
            ]
        }

        original = audit.fetch_tls_metadata
        audit.fetch_tls_metadata = lambda hostname, **kwargs: {
            "expires_at": "2026-03-29T11:15:05Z",
            "seconds_remaining": 11 * 3600,
            "hours_remaining": 11,
            "days_remaining": 0,
            "issuer": "CN=Test",
            "verification_error": None,
        }
        try:
            findings = audit.collect_tls_findings(registry)
        finally:
            audit.fetch_tls_metadata = original

        self.assertEqual(findings, [])

    def test_tls_findings_warn_when_step_ca_cert_enters_renew_window(self) -> None:
        registry = {
            "publications": [
                {
                    "fqdn": "vault.example.com",
                    "status": "active",
                    "environment": "production",
                    "adapter": {
                        "tls": {"provider": "step-ca", "auto_renew": True},
                        "dns": {"target": "100.64.0.1", "target_port": 443},
                    },
                    "publication": {"delivery_model": "private-network"},
                }
            ]
        }

        original = audit.fetch_tls_metadata
        audit.fetch_tls_metadata = lambda hostname, **kwargs: {
            "expires_at": "2026-03-29T04:15:05Z",
            "seconds_remaining": 5 * 3600,
            "hours_remaining": 5,
            "days_remaining": 0,
            "issuer": "CN=Test",
            "verification_error": None,
        }
        try:
            findings = audit.collect_tls_findings(registry)
        finally:
            audit.fetch_tls_metadata = original

        self.assertEqual(findings[0]["severity"], "WARN")
        self.assertIn("5 hours remaining", findings[0]["detail"])

    def test_check_registry_current_detects_staleness(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="subdomain-exposure-"))
        try:
            registry_path = temp_dir / "subdomain-exposure-registry.json"
            registry_path.write_text(json.dumps({"schema_version": "1.0.0"}) + "\n", encoding="utf-8")

            original = audit.REGISTRY_PATH
            audit.REGISTRY_PATH = registry_path
            try:
                with self.assertRaisesRegex(ValueError, "out of date"):
                    audit.check_registry_current(
                        {"schema_version": "2.0.0", "summary": {}, "publications": [], "zone_name": "example.com"}
                    )
            finally:
                audit.REGISTRY_PATH = original
        finally:
            shutil.rmtree(temp_dir)

    def test_wildcard_edge_alias_matches_catalog_hostname(self) -> None:
        route = {
            "hostname": "apps.example.com",
            "aliases": ["*.apps.example.com"],
        }

        self.assertEqual(audit.resolve_route_for_hostname("repo-smoke.apps.example.com", [route]), route)


def _replace_example_domain(value):
    if isinstance(value, str):
        return value.replace("example.com", "lv3.org")
    if isinstance(value, list):
        return [_replace_example_domain(item) for item in value]
    if isinstance(value, dict):
        return {key: _replace_example_domain(item) for key, item in value.items()}
    return value


if __name__ == "__main__":
    unittest.main()
