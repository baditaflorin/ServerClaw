import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "public_edge_oidc_auth" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "public_edge_oidc_auth" / "tasks" / "main.yml"
TEMPLATE_PATH = REPO_ROOT / "roles" / "public_edge_oidc_auth" / "templates" / "oauth2-proxy.cfg.j2"
WATCHDOG_TEMPLATE_PATH = (
    REPO_ROOT / "roles" / "public_edge_oidc_auth" / "templates" / "lv3-ops-portal-oauth2-proxy-watchdog.sh.j2"
)


class PublicEdgeOidcAuthRoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
        self.tasks = TASKS_PATH.read_text()
        self.template = TEMPLATE_PATH.read_text()
        self.watchdog_template = WATCHDOG_TEMPLATE_PATH.read_text()

    def test_ops_portal_proxy_requests_only_standard_oidc_scopes(self) -> None:
        self.assertEqual(self.defaults["public_edge_oidc_auth_scope"], "openid profile email")
        self.assertNotIn("groups", self.defaults["public_edge_oidc_auth_scope"].split())
        self.assertEqual(self.defaults["public_edge_oidc_auth_cookie_domain"], ".{{ platform_domain }}")
        self.assertEqual(self.defaults["public_edge_oidc_auth_probe_hostname"], "ops.{{ platform_domain }}")
        self.assertEqual(self.defaults["public_edge_oidc_auth_version"], "7.15.1")
        self.assertTrue(self.defaults["public_edge_oidc_auth_allow_unverified_email"])

    def test_template_renders_scope_and_group_filtering(self) -> None:
        self.assertIn('scope = "{{ public_edge_oidc_auth_scope }}"', self.template)
        self.assertIn("allowed_groups =", self.template)
        self.assertIn("pass_access_token = true", self.template)
        self.assertIn("pass_authorization_header = true", self.template)
        self.assertIn("set_authorization_header = true", self.template)
        self.assertIn("insecure_oidc_allow_unverified_email", self.template)

    def test_role_pins_public_issuer_to_local_edge_for_oidc_discovery(self) -> None:
        self.assertIn("urlsplit('hostname')", self.tasks)
        self.assertIn("path: /etc/hosts", self.tasks)
        self.assertIn('line: "{{ ansible_host }} {{ public_edge_oidc_auth_issuer_hostname }}"', self.tasks)

    def test_oauth2_proxy_pins_authentik_jwks_and_rsa_algorithm(self) -> None:
        config_template = (
            REPO_ROOT / "roles" / "public_edge_oidc_auth" / "templates" / "oauth2-proxy.cfg.j2"
        ).read_text()
        defaults = (REPO_ROOT / "roles" / "public_edge_oidc_auth" / "defaults" / "main.yml").read_text()
        self.assertIn('oidc_jwks_url = "{{ public_edge_oidc_auth_jwks_url }}"', config_template)
        self.assertIn("oidc_enabled_signing_algs", config_template)
        self.assertIn("- RS256", defaults)

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
