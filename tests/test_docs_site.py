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
import generate_dependency_diagram as dependency_diagram  # noqa: E402


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
            self.assertIn("sensitivity: INTERNAL", keycloak_md)
            self.assertIn("sensitivity: PUBLIC", api_md)
            self.assertIn("portal_display: full", keycloak_md)
            subdomains_md = (temp_dir / "reference" / "subdomains.md").read_text(encoding="utf-8")
            self.assertIn("edge_oidc", subdomains_md)
            self.assertIn("upstream_auth", subdomains_md)
            dependency_graph_md = (temp_dir / "architecture" / "dependency-graph.md").read_text(encoding="utf-8")
            self.assertEqual(dependency_graph_md, dependency_diagram.render())
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

    def test_write_mode_can_target_explicit_output_dir(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="docs-site-cli-test-"))
        try:
            exit_code = docs_site.main(["--write", "--output-dir", str(temp_dir), "--openapi-url", ""])

            self.assertEqual(exit_code, 0)
            docs_site.validate_site(temp_dir)
        finally:
            shutil.rmtree(temp_dir)

    def test_build_portal_document_defaults_to_internal_sensitivity(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="docs-site-test-"))
        try:
            path = temp_dir / "example.md"
            path.write_text("# Example\n\nInternal by default.\n", encoding="utf-8")

            document = docs_site.build_portal_document(path)

            self.assertEqual(document.sensitivity, "INTERNAL")
            self.assertEqual(document.portal_display, "full")
            self.assertTrue(document.publish_in_portal)
        finally:
            shutil.rmtree(temp_dir)

    def test_restricted_document_renders_summary_only_page(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="docs-site-test-"))
        try:
            path = temp_dir / "restricted.md"
            path.write_text(
                "---\n"
                "sensitivity: RESTRICTED\n"
                "portal_summary: Safe operator summary.\n"
                "justification: Contains sensitive recovery steps.\n"
                "---\n"
                "# Restricted Runbook\n\n"
                "Full recovery token format and privileged steps.\n",
                encoding="utf-8",
            )

            document = docs_site.build_portal_document(path)
            rendered = docs_site.render_portal_document(document, Path("runbooks/restricted.md"))

            self.assertEqual(document.sensitivity, "RESTRICTED")
            self.assertEqual(document.portal_display, "summary")
            self.assertIn("sensitivity: RESTRICTED", rendered)
            self.assertIn("portal_display: summary", rendered)
            self.assertIn("Safe operator summary.", rendered)
            self.assertNotIn("Full recovery token format", rendered)
        finally:
            shutil.rmtree(temp_dir)

    def test_mkdocs_build_uses_global_robots_override(self) -> None:
        mkdocs_config = (REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8")
        override_template = (REPO_ROOT / "docs" / "theme-overrides" / "main.html").read_text(encoding="utf-8")

        self.assertIn("custom_dir: docs/theme-overrides", mkdocs_config)
        self.assertIn('<meta name="robots" content="noindex, nofollow">', override_template)


if __name__ == "__main__":
    unittest.main()
