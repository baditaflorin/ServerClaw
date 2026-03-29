import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import service_catalog  # noqa: E402


class ValidateServiceCatalogTest(unittest.TestCase):
    def test_repo_catalog_validates(self) -> None:
        catalog = service_catalog.load_service_catalog()
        service_catalog.validate_service_catalog(catalog)

        service_ids = {item["id"] for item in catalog["services"]}
        self.assertIn("grafana", service_ids)
        self.assertIn("docs_portal", service_ids)
        self.assertIn("homepage", service_ids)
        self.assertGreaterEqual(len(service_ids), 24)

    def test_invalid_health_probe_fixture_fails(self) -> None:
        fixture_path = REPO_ROOT / "tests" / "fixtures" / "service-catalog-invalid-health-probe.json"
        catalog = service_catalog.load_json(fixture_path)

        with self.assertRaisesRegex(ValueError, "unknown health probe 'missing_probe'"):
            service_catalog.validate_service_catalog(catalog)

    def test_invalid_degradation_fixture_fails(self) -> None:
        fixture_path = REPO_ROOT / "tests" / "fixtures" / "service-catalog-invalid-degradation-mode.json"
        catalog = service_catalog.load_json(fixture_path)

        with self.assertRaisesRegex(ValueError, "must not declare duplicate dependency 'postgres'"):
            service_catalog.validate_service_catalog(catalog)

    def test_show_service_renders_expected_summary(self) -> None:
        catalog = service_catalog.load_service_catalog()
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = service_catalog.show_service(catalog, "api_gateway")
        output = buffer.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("Service: api_gateway", output)
        self.assertIn("Runbook: docs/runbooks/configure-api-gateway.md", output)
        self.assertIn("smoke suites (inherited):", output)
        self.assertIn("Degradation modes:", output)

    def test_n8n_service_entry_describes_serverclaw_connector_role(self) -> None:
        catalog = service_catalog.load_service_catalog()
        n8n = next(item for item in catalog["services"] if item["id"] == "n8n")

        self.assertIn("ServerClaw", n8n["description"])
        self.assertIn("connector-fabric", n8n["tags"])

    def test_invalid_explicit_smoke_suite_requires_matching_tokens(self) -> None:
        catalog = {
            "$schema": "docs/schema/service-capability-catalog.schema.json",
            "schema_version": "1.0.0",
            "services": [
                {
                    "id": "grafana",
                    "name": "Grafana",
                    "description": "Metrics dashboards and alerting for the platform.",
                    "category": "observability",
                    "lifecycle_status": "active",
                    "vm": "monitoring-lv3",
                    "vmid": 140,
                    "internal_url": "http://10.10.10.40:3000",
                    "public_url": "https://grafana.lv3.org",
                    "subdomain": "grafana.lv3.org",
                    "exposure": "edge-published",
                    "environments": {
                        "production": {
                            "status": "active",
                            "url": "https://grafana.lv3.org",
                            "subdomain": "grafana.lv3.org",
                            "smoke_suites": [
                                {
                                    "id": "broken-suite",
                                    "name": "Broken suite",
                                    "description": "Missing both receipt keywords and verification tokens."
                                }
                            ]
                        }
                    },
                    "uptime_monitor_name": "Grafana Public",
                    "health_probe_id": "grafana",
                    "adr": "0011",
                    "runbook": "docs/runbooks/monitoring-stack.md",
                    "tags": ["dashboards", "metrics", "monitoring"],
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "must declare at least one receipt keyword or verification check token"):
            service_catalog.validate_service_catalog(catalog)

    def test_stage_ready_environment_requires_smoke_suite_ids(self) -> None:
        catalog = {
            "$schema": "docs/schema/service-capability-catalog.schema.json",
            "schema_version": "1.0.0",
            "services": [
                {
                    "id": "demo",
                    "name": "Demo",
                    "description": "Demo service.",
                    "category": "automation",
                    "lifecycle_status": "active",
                    "vm": "docker-runtime-lv3",
                    "exposure": "private-only",
                    "internal_url": "http://10.10.10.20:9999",
                    "environments": {
                        "production": {
                            "status": "active",
                            "url": "http://10.10.10.20:9999",
                            "stage_ready": True,
                        }
                    },
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "stage_ready requires at least one smoke suite id"):
            service_catalog.validate_service_catalog(catalog)


if __name__ == "__main__":
    unittest.main()
