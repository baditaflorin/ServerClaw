import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "nginx_edge_publication" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "nginx_edge_publication" / "tasks" / "main.yml"
TEMPLATE_PATH = REPO_ROOT / "roles" / "nginx_edge_publication" / "templates" / "lv3-edge.conf.j2"
STATIC_TEMPLATE_PATH = REPO_ROOT / "roles" / "nginx_edge_publication" / "templates" / "static-page.html.j2"


class NginxEdgePublicationRoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
        self.tasks = yaml.safe_load(TASKS_PATH.read_text())
        self.template = TEMPLATE_PATH.read_text()
        self.static_template = STATIC_TEMPLATE_PATH.read_text()

    def test_defaults_enable_pinned_dns_hetzner_acme(self) -> None:
        self.assertEqual(self.defaults["public_edge_acme_challenge_method"], "dns-hetzner")
        self.assertEqual(self.defaults["public_edge_control_plane_host"], "{{ groups['proxmox_hosts'][0] }}")
        self.assertEqual(
            self.defaults["proxmox_guests"],
            "{{ hostvars[public_edge_control_plane_host].proxmox_guests }}",
        )
        self.assertEqual(
            self.defaults["management_tailscale_ipv4"],
            "{{ hostvars[public_edge_control_plane_host].management_tailscale_ipv4 }}",
        )
        self.assertEqual(
            self.defaults["platform_port_assignments"],
            "{{ hostvars[public_edge_control_plane_host].platform_port_assignments }}",
        )
        self.assertEqual(
            self.defaults["postgres_ha"],
            "{{ hostvars[public_edge_control_plane_host].postgres_ha }}",
        )
        self.assertEqual(self.defaults["public_edge_service_topology"], "{{ platform_service_topology }}")
        self.assertEqual(self.defaults["public_edge_dns_hetzner_plugin_version"], "3.0.0")
        self.assertEqual(
            self.defaults["public_edge_dns_hetzner_credentials_file"],
            "/etc/letsencrypt/hetzner.ini",
        )
        self.assertEqual(
            self.defaults["public_edge_dns_hetzner_virtualenv"],
            "/opt/certbot-dns-hetzner",
        )
        self.assertEqual(self.defaults["public_edge_apex_hostname"], "lv3.org")
        self.assertEqual(self.defaults["public_edge_additional_certificate_domains"], ["{{ public_edge_apex_hostname }}"])
        self.assertEqual(self.defaults["public_edge_robots_meta_content"], "noindex, nofollow")
        self.assertIn("User-agent: *", self.defaults["public_edge_robots_txt_content"])
        self.assertIn("Disallow: /", self.defaults["public_edge_robots_txt_content"])

    def test_ops_portal_defaults_use_authenticated_proxy_mode(self) -> None:
        extra_hostnames = [site["hostname"] for site in self.defaults["public_edge_extra_sites"]]
        protected_sites = self.defaults["public_edge_authenticated_sites"]

        self.assertNotIn("ops.lv3.org", extra_hostnames)
        self.assertEqual(sorted(protected_sites), ["changelog.lv3.org", "docs.lv3.org", "ops.lv3.org"])
        self.assertEqual(protected_sites["ops.lv3.org"]["unauthenticated_paths"], ["/health"])
        self.assertNotIn("unauthenticated_paths", protected_sites["docs.lv3.org"])
        self.assertNotIn("unauthenticated_paths", protected_sites["changelog.lv3.org"])

    def test_tasks_include_dns_hetzner_plugin_and_credentials_flow(self) -> None:
        task_names = {task["name"] for task in self.tasks}

        self.assertIn("Install the pinned Certbot Hetzner DNS plugin", task_names)
        self.assertIn(
            "Assert the Hetzner DNS credential file is available when DNS-01 is enabled",
            task_names,
        )
        self.assertIn("Render the crawl policy robots.txt", task_names)

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
        self.assertNotIn("noindex", docs_site)

    def test_template_supports_root_proxy_path_override(self) -> None:
        self.assertIn("site.root_proxy_path is defined", self.template)
        self.assertIn("location = / {", self.template)
        self.assertIn("site.hostname in public_edge_authenticated_sites", self.template)
        self.assertIn('add_header X-Robots-Tag "{{ public_edge_robots_meta_content }}" always;', self.template)
        self.assertIn("location = /robots.txt {", self.template)
        self.assertIn("server_name {{ public_edge_apex_hostname }};", self.template)

    def test_certificate_domain_expression_includes_additional_domains(self) -> None:
        certificate_domains_expr = self.defaults["public_edge_certificate_domains"]
        self.assertIn("public_edge_additional_certificate_domains", certificate_domains_expr)

    def test_static_pages_include_robots_meta_tag(self) -> None:
        self.assertIn('<meta name="robots" content="{{ public_edge_robots_meta_content }}">', self.static_template)

    def test_template_supports_proxy_header_stripping_and_blocked_paths(self) -> None:
        self.assertIn("site.proxy_hide_headers | default([])", self.template)
        self.assertIn("site.blocked_exact_paths | default([])", self.template)
        self.assertIn("proxy_hide_header {{ header_name }};", self.template)


if __name__ == "__main__":
    unittest.main()
