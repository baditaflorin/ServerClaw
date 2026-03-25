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
        self.assertIn("Degradation modes:", output)


if __name__ == "__main__":
    unittest.main()
