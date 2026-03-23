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

import generate_docs_site as docs_site  # noqa: E402


class DocsSiteTests(unittest.TestCase):
    def test_render_site_writes_expected_pages(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="docs-site-test-"))
        try:
            docs_site.render_site(temp_dir, openapi_url=None)
            docs_site.validate_site(temp_dir)

            index_md = (temp_dir / "index.md").read_text(encoding="utf-8")
            keycloak_md = (temp_dir / "services" / "keycloak.md").read_text(encoding="utf-8")
            ports_md = (temp_dir / "reference" / "ports.md").read_text(encoding="utf-8")
            api_md = (temp_dir / "api" / "index.md").read_text(encoding="utf-8")

            self.assertIn("LV3 Platform Docs", index_md)
            self.assertIn("https://sso.lv3.org", keycloak_md)
            self.assertIn("ADR 0056", keycloak_md)
            self.assertIn("18080", ports_md)
            self.assertIn("docs.lv3.org", ports_md)
            self.assertIn("OpenAPI browser", api_md)
        finally:
            shutil.rmtree(temp_dir)

    def test_render_site_writes_openapi_snapshot(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="docs-site-test-"))
        try:
            docs_site.render_site(temp_dir, openapi_url=None)
            payload = json.loads((temp_dir / "api" / "openapi.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["openapi"], "3.1.0")
            self.assertIn("paths", payload)
        finally:
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    unittest.main()
