from __future__ import annotations

import json
import shutil
import ssl
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import subdomain_exposure_audit as audit  # noqa: E402


class SubdomainExposureAuditTests(unittest.TestCase):
    def test_repo_registry_tracks_known_hostnames(self) -> None:
        registry = audit.build_registry()
        by_fqdn = {entry["fqdn"]: entry for entry in registry["publications"]}

        self.assertEqual(by_fqdn["lv3.org"]["adapter"]["routing"]["source"], "public_edge_apex")
        self.assertEqual(by_fqdn["lv3.org"]["adapter"]["dns"]["records"], [{"type": "A", "value": "65.108.75.123"}])
        self.assertEqual(by_fqdn["n8n.lv3.org"]["publication"]["access_model"], "platform-sso")
        self.assertEqual(
            by_fqdn["n8n.lv3.org"]["adapter"]["edge_auth"]["unauthenticated_prefix_paths"],
            ["/webhook/", "/webhook-test/", "/webhook-waiting/"],
        )
        self.assertEqual(by_fqdn["ops.lv3.org"]["publication"]["access_model"], "platform-sso")
        self.assertEqual(by_fqdn["ops.lv3.org"]["adapter"]["edge_auth"]["provider"], "oauth2_proxy")
        self.assertEqual(by_fqdn["docs.lv3.org"]["adapter"]["routing"]["source"], "public_edge_extra_sites")
        self.assertEqual(by_fqdn["database.lv3.org"]["publication"]["access_model"], "private-network")
        self.assertEqual(by_fqdn["vault.lv3.org"]["adapter"]["dns"]["visibility"], "tailnet")
        self.assertTrue(by_fqdn["vault.lv3.org"]["evidence_plan"]["private_route"])
        self.assertTrue(by_fqdn["changelog.lv3.org"]["live_tracking_expected"])
        self.assertGreater(registry["summary"]["active_total"], 0)

    def test_repo_findings_flag_edge_oidc_mismatch(self) -> None:
        registry = {
            "publications": [
                {
                    "fqdn": "ops.lv3.org",
                    "status": "active",
                    "publication": {"access_model": "platform-sso"},
                    "adapter": {"edge_auth": {"provider": "none"}},
                }
            ]
        }

        findings = audit.collect_repo_findings(registry)

        self.assertEqual(findings[0]["severity"], "CRITICAL")
        self.assertIn("platform-sso", findings[0]["detail"])

    def test_repo_findings_ignore_planned_edge_oidc_routes(self) -> None:
        registry = {
            "publications": [
                {
                    "fqdn": "ops.staging.lv3.org",
                    "status": "planned",
                    "publication": {"access_model": "platform-sso"},
                    "adapter": {"edge_auth": {"provider": "none"}},
                }
            ]
        }

        findings = audit.collect_repo_findings(registry)

        self.assertEqual(findings, [])

    def test_zone_findings_compare_full_record_sets(self) -> None:
        registry = {
            "zone_name": "lv3.org",
            "publications": [
                {
                    "fqdn": "lv3.org",
                    "environment": "production",
                    "status": "active",
                    "publication": {"delivery_model": "informational-edge"},
                    "adapter": {
                        "dns": {
                            "records": [{"type": "A", "value": "65.108.75.123"}],
                            "zone_expected": True,
                        }
                    },
                }
            ],
        }

        findings = audit.collect_zone_findings(
            registry,
            [
                {"name": "@", "type": "A", "value": "65.108.75.123"},
                {"name": "@", "type": "AAAA", "value": "2a01:db8::1"},
            ],
        )

        self.assertEqual(findings[0]["finding"], "zone_record_differs_from_catalog")
        self.assertIn("Unexpected", findings[0]["detail"])

    def test_resolution_findings_flag_planned_but_live(self) -> None:
        registry = {
            "publications": [
                {
                    "fqdn": "docs.lv3.org",
                    "environment": "production",
                    "status": "planned",
                    "publication": {"delivery_model": "shared-edge"},
                    "adapter": {
                        "dns": {
                            "target": "65.108.75.123",
                            "records": [{"type": "A", "value": "65.108.75.123"}],
                            "zone_expected": True,
                        }
                    },
                }
            ]
        }

        original = audit.resolve_public_records
        audit.resolve_public_records = lambda fqdn: ["65.108.75.123"]
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
                    "fqdn": "ops.lv3.org",
                    "status": "active",
                    "environment": "production",
                    "publication": {"access_model": "platform-sso"},
                }
            ]
        }

        original = audit.http_probe
        audit.http_probe = lambda url: (200, "https://ops.lv3.org/", {})
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
                    "fqdn": "mail.lv3.org",
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
                    "fqdn": "database.lv3.org",
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
                    "fqdn": "mail.lv3.org",
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
                    "fqdn": "vault.lv3.org",
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
                    "fqdn": "vault.lv3.org",
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
                        {"schema_version": "2.0.0", "summary": {}, "publications": [], "zone_name": "lv3.org"}
                    )
            finally:
                audit.REGISTRY_PATH = original
        finally:
            shutil.rmtree(temp_dir)

    def test_wildcard_edge_alias_matches_catalog_hostname(self) -> None:
        route = {
            "hostname": "apps.lv3.org",
            "aliases": ["*.apps.lv3.org"],
        }

        self.assertEqual(audit.resolve_route_for_hostname("repo-smoke.apps.lv3.org", [route]), route)


if __name__ == "__main__":
    unittest.main()
