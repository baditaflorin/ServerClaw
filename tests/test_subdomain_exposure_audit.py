from __future__ import annotations

import json
import shutil
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
        by_fqdn = {entry["fqdn"]: entry for entry in registry["subdomains"]}

        self.assertEqual(by_fqdn["n8n.lv3.org"]["auth_requirement"], "edge_oidc")
        self.assertEqual(
            by_fqdn["n8n.lv3.org"]["unauthenticated_prefix_paths"],
            ["/webhook/", "/webhook-test/", "/webhook-waiting/"],
        )
        self.assertEqual(by_fqdn["ops.lv3.org"]["auth_requirement"], "edge_oidc")
        self.assertEqual(by_fqdn["ops.lv3.org"]["edge_auth"], "oauth2_proxy")
        self.assertEqual(by_fqdn["docs.lv3.org"]["route_source"], "public_edge_extra_sites")
        self.assertEqual(by_fqdn["database.lv3.org"]["auth_requirement"], "private_network")
        self.assertTrue(by_fqdn["changelog.lv3.org"]["live_tracking_expected"])
        self.assertGreater(registry["summary"]["active_total"], 0)

    def test_repo_findings_flag_edge_oidc_mismatch(self) -> None:
        registry = {
            "subdomains": [
                {
                    "fqdn": "ops.lv3.org",
                    "status": "active",
                    "auth_requirement": "edge_oidc",
                    "edge_auth": "none",
                }
            ]
        }

        findings = audit.collect_repo_findings(registry)

        self.assertEqual(findings[0]["severity"], "CRITICAL")
        self.assertIn("edge_oidc", findings[0]["detail"])

    def test_repo_findings_ignore_planned_edge_oidc_routes(self) -> None:
        registry = {
            "subdomains": [
                {
                    "fqdn": "ops.staging.lv3.org",
                    "status": "planned",
                    "auth_requirement": "edge_oidc",
                    "edge_auth": "none",
                }
            ]
        }

        findings = audit.collect_repo_findings(registry)

        self.assertEqual(findings, [])

    def test_resolution_findings_flag_planned_but_live(self) -> None:
        registry = {
            "subdomains": [
                {
                    "fqdn": "docs.lv3.org",
                    "environment": "production",
                    "status": "planned",
                    "exposure": "edge-published",
                    "target": "65.108.75.123",
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
            "subdomains": [
                {
                    "fqdn": "ops.lv3.org",
                    "status": "active",
                    "environment": "production",
                    "auth_requirement": "edge_oidc",
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

    def test_check_registry_current_detects_staleness(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="subdomain-exposure-"))
        try:
            registry_path = temp_dir / "subdomain-exposure-registry.json"
            registry_path.write_text(json.dumps({"schema_version": "1.0.0"}) + "\n", encoding="utf-8")

            original = audit.REGISTRY_PATH
            audit.REGISTRY_PATH = registry_path
            try:
                with self.assertRaisesRegex(ValueError, "out of date"):
                    audit.check_registry_current({"schema_version": "1.0.0", "summary": {}, "subdomains": [], "zone_name": "lv3.org"})
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
