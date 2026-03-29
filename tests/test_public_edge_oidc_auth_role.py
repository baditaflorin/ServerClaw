import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "public_edge_oidc_auth" / "defaults" / "main.yml"
TEMPLATE_PATH = REPO_ROOT / "roles" / "public_edge_oidc_auth" / "templates" / "oauth2-proxy.cfg.j2"


class PublicEdgeOidcAuthRoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
        self.template = TEMPLATE_PATH.read_text()

    def test_ops_portal_proxy_requests_only_standard_oidc_scopes(self) -> None:
        self.assertEqual(self.defaults["public_edge_oidc_auth_scope"], "openid profile email")
        self.assertNotIn("groups", self.defaults["public_edge_oidc_auth_scope"].split())
        self.assertEqual(self.defaults["public_edge_oidc_auth_cookie_domain"], ".lv3.org")
        self.assertEqual(self.defaults["public_edge_oidc_auth_probe_hostname"], "ops.lv3.org")
        self.assertEqual(self.defaults["public_edge_oidc_auth_version"], "7.15.1")

    def test_template_renders_scope_and_group_filtering(self) -> None:
        self.assertIn('scope = "{{ public_edge_oidc_auth_scope }}"', self.template)
        self.assertIn("allowed_groups =", self.template)
        self.assertIn("pass_access_token = true", self.template)
        self.assertIn("pass_authorization_header = true", self.template)
        self.assertIn("set_authorization_header = true", self.template)


if __name__ == "__main__":
    unittest.main()
