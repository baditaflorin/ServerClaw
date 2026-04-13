import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "public_edge_oidc_auth" / "defaults" / "main.yml"
TEMPLATE_PATH = REPO_ROOT / "roles" / "public_edge_oidc_auth" / "templates" / "oauth2-proxy.cfg.j2"
WATCHDOG_TEMPLATE_PATH = (
    REPO_ROOT / "roles" / "public_edge_oidc_auth" / "templates" / "lv3-ops-portal-oauth2-proxy-watchdog.sh.j2"
)


class PublicEdgeOidcAuthRoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
        self.template = TEMPLATE_PATH.read_text()
        self.watchdog_template = WATCHDOG_TEMPLATE_PATH.read_text()

    def test_ops_portal_proxy_requests_only_standard_oidc_scopes(self) -> None:
        self.assertEqual(self.defaults["public_edge_oidc_auth_scope"], "openid profile email")
        self.assertNotIn("groups", self.defaults["public_edge_oidc_auth_scope"].split())
        self.assertEqual(self.defaults["public_edge_oidc_auth_cookie_domain"], ".{{ platform_domain }}")
        self.assertEqual(self.defaults["public_edge_oidc_auth_probe_hostname"], "ops.{{ platform_domain }}")
        self.assertEqual(self.defaults["public_edge_oidc_auth_version"], "7.15.1")

    def test_template_renders_scope_and_group_filtering(self) -> None:
        self.assertIn('scope = "{{ public_edge_oidc_auth_scope }}"', self.template)
        self.assertIn("allowed_groups =", self.template)
        self.assertIn("pass_access_token = true", self.template)
        self.assertIn("pass_authorization_header = true", self.template)
        self.assertIn("set_authorization_header = true", self.template)

    def test_watchdog_template_probes_auth_endpoint_and_recovers_service(self) -> None:
        self.assertIn('PROBE_URL="http://{{ public_edge_oidc_auth_http_address }}/oauth2/auth"', self.watchdog_template)
        self.assertIn('PROBE_HOST="{{ public_edge_oidc_auth_probe_hostname }}"', self.watchdog_template)
        self.assertIn(
            'FAILURE_THRESHOLD="{{ public_edge_oidc_auth_watchdog_failure_threshold }}"', self.watchdog_template
        )
        self.assertIn('status_code=$(curl -s -o /dev/null -w "%{http_code}" -m 5 \\', self.watchdog_template)
        self.assertIn('systemctl restart "${SERVICE}" || true', self.watchdog_template)
        self.assertIn('send_ntfy "oauth2-proxy unhealthy (status=${status_code}) — restarting"', self.watchdog_template)


if __name__ == "__main__":
    unittest.main()
