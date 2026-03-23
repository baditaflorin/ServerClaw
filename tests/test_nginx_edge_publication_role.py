import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "nginx_edge_publication" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "nginx_edge_publication" / "tasks" / "main.yml"
TEMPLATE_PATH = REPO_ROOT / "roles" / "nginx_edge_publication" / "templates" / "lv3-edge.conf.j2"


class NginxEdgePublicationRoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
        self.tasks = yaml.safe_load(TASKS_PATH.read_text())
        self.template = TEMPLATE_PATH.read_text()

    def test_defaults_enable_pinned_dns_hetzner_acme(self) -> None:
        self.assertEqual(self.defaults["public_edge_acme_challenge_method"], "dns-hetzner")
        self.assertEqual(self.defaults["public_edge_dns_hetzner_plugin_version"], "3.0.0")
        self.assertEqual(
            self.defaults["public_edge_dns_hetzner_credentials_file"],
            "/etc/letsencrypt/hetzner.ini",
        )
        self.assertEqual(
            self.defaults["public_edge_dns_hetzner_virtualenv"],
            "/opt/certbot-dns-hetzner",
        )

    def test_ops_portal_defaults_use_authenticated_proxy_mode(self) -> None:
        extra_hostnames = [site["hostname"] for site in self.defaults["public_edge_extra_sites"]]

        self.assertNotIn("ops.lv3.org", extra_hostnames)
        self.assertEqual(
            self.defaults["public_edge_authenticated_sites"]["ops.lv3.org"]["unauthenticated_paths"],
            ["/health"],
        )

    def test_tasks_include_dns_hetzner_plugin_and_credentials_flow(self) -> None:
        task_names = {task["name"] for task in self.tasks}

        self.assertIn("Install the pinned Certbot Hetzner DNS plugin", task_names)
        self.assertIn(
            "Assert the Hetzner DNS credential file is available when DNS-01 is enabled",
            task_names,
        )

    def test_certificate_san_regex_preserves_domains_with_s_characters(self) -> None:
        derive_task = next(
            task
            for task in self.tasks
            if task["name"] == "Derive current and missing public edge certificate domains"
        )
        current_domains_expr = derive_task["ansible.builtin.set_fact"]["public_edge_current_certificate_domains"]

        self.assertIn("regex_findall('DNS:([^, ]+)')", current_domains_expr)

    def test_defaults_include_public_docs_site(self) -> None:
        docs_site = next(
            site for site in self.defaults["public_edge_extra_sites"] if site["hostname"] == "docs.lv3.org"
        )
        self.assertEqual(docs_site["source_dir"], "docs-portal")
        self.assertTrue(docs_site["noindex"])

    def test_template_supports_root_proxy_path_override(self) -> None:
        self.assertIn("site.root_proxy_path is defined", self.template)
        self.assertIn("location = / {", self.template)


if __name__ == "__main__":
    unittest.main()
