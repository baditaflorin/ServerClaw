import shutil
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from generate_ops_portal import render_portal  # noqa: E402
from service_catalog import load_service_catalog, validate_service_catalog  # noqa: E402


class ServiceCatalogTests(unittest.TestCase):
    def test_catalog_validates(self) -> None:
        catalog = load_service_catalog()
        validate_service_catalog(catalog)
        self.assertGreaterEqual(len(catalog["services"]), 12)


class OpsPortalRenderTests(unittest.TestCase):
    def test_render_portal_writes_expected_pages(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="ops-portal-test-"))
        try:
            render_portal(
                temp_dir,
                REPO_ROOT / "tests" / "fixtures" / "ops_portal_health.json",
                0,
            )
            index_html = (temp_dir / "index.html").read_text()
            dns_html = (temp_dir / "subdomains" / "index.html").read_text()
            agents_html = (temp_dir / "agents" / "index.html").read_text()

            self.assertIn("Platform Operations Portal", index_html)
            self.assertIn("Grafana", index_html)
            self.assertIn("healthy", index_html)
            self.assertIn("ops.lv3.org", dns_html)
            self.assertIn("get-platform-status", agents_html)
        finally:
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    unittest.main()
