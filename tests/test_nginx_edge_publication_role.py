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
        self.assertEqual(
            self.defaults["public_edge_certbot_plugin_path"],
            "{{ public_edge_dns_hetzner_virtualenv }}/lib/python{{ ansible_python.version.major }}.{{ ansible_python.version.minor }}/site-packages",
        )
        self.assertEqual(self.defaults["public_edge_apex_hostname"], "lv3.org")
        self.assertEqual(self.defaults["public_edge_additional_certificate_domains"], ["{{ public_edge_apex_hostname }}"])
        self.assertEqual(self.defaults["public_edge_robots_meta_content"], "noindex, nofollow")
        self.assertEqual(
            self.defaults["public_edge_generated_build_root"],
            "{{ inventory_dir | dirname }}/build",
        )
        self.assertIn("User-agent: *", self.defaults["public_edge_robots_txt_content"])
        self.assertIn("Disallow: /", self.defaults["public_edge_robots_txt_content"])

    def test_ops_portal_defaults_use_authenticated_proxy_mode(self) -> None:
        extra_hostnames = [site["hostname"] for site in self.defaults["public_edge_extra_sites"]]
        protected_sites = self.defaults["public_edge_authenticated_sites"]

        self.assertNotIn("ops.lv3.org", extra_hostnames)
        self.assertEqual(
            sorted(protected_sites),
            ["changelog.lv3.org", "docs.lv3.org", "home.lv3.org", "langfuse.lv3.org", "logs.lv3.org", "n8n.lv3.org", "ops.lv3.org", "tasks.lv3.org"],
        )
        self.assertNotIn("unauthenticated_paths", protected_sites["langfuse.lv3.org"])
        self.assertEqual(protected_sites["n8n.lv3.org"]["unauthenticated_paths"], ["/healthz"])
        self.assertEqual(
            protected_sites["n8n.lv3.org"]["unauthenticated_prefix_paths"],
            ["/webhook/", "/webhook-test/", "/webhook-waiting/"],
        )
        self.assertEqual(protected_sites["ops.lv3.org"]["unauthenticated_paths"], ["/health"])
        self.assertNotIn("unauthenticated_paths", protected_sites["docs.lv3.org"])
        self.assertNotIn("unauthenticated_paths", protected_sites["changelog.lv3.org"])
        self.assertNotIn("unauthenticated_paths", protected_sites["logs.lv3.org"])
        self.assertNotIn("unauthenticated_paths", protected_sites["home.lv3.org"])
        self.assertEqual(protected_sites["tasks.lv3.org"]["auth_proxy_upstream"], "http://127.0.0.1:4180")

    def test_tasks_include_dns_hetzner_plugin_and_credentials_flow(self) -> None:
        task_names = {task["name"] for task in self.tasks}

        self.assertIn("Install the pinned Certbot Hetzner DNS plugin", task_names)
        self.assertIn(
            "Assert the Hetzner DNS credential file is available when DNS-01 is enabled",
            task_names,
        )
        self.assertIn("Render the crawl policy robots.txt", task_names)
        publish_task = next(
            task for task in self.tasks if task["name"] == "Publish generated static site directories"
        )
        self.assertIn("ansible.builtin.command", publish_task)
        self.assertEqual(publish_task["delegate_to"], "localhost")
        self.assertFalse(publish_task["become"])
        publish_argv = publish_task["ansible.builtin.command"]["argv"]
        self.assertIn("--rsync-path=sudo rsync", publish_argv)
        self.assertIn("ansible_ssh_common_args", publish_argv[6])
        self.assertIn("proxmox_guest_ssh_common_args[proxmox_guest_ssh_connection_mode]", publish_argv[6])
        ensure_packages_task = next(
            task for task in self.tasks if task["name"] == "Ensure public edge packages are present"
        )
        package_expr = ensure_packages_task["ansible.builtin.apt"]["name"]
        self.assertIn("rsync", package_expr)

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

    def test_defaults_publish_global_security_headers_with_host_overrides(self) -> None:
        security_defaults = self.defaults["public_edge_security_headers_default"]
        security_overrides = self.defaults["public_edge_security_headers_overrides"]

        self.assertEqual(
            security_defaults["strict_transport_security"],
            "max-age=63072000; includeSubDomains; preload",
        )
        self.assertEqual(security_defaults["cross_origin_resource_policy"], "same-origin")
        self.assertEqual(security_defaults["x_content_type_options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", security_defaults["content_security_policy"])
        self.assertIn("grafana.lv3.org", security_overrides)
        self.assertIn("logs.lv3.org", security_overrides)
        self.assertIn("tasks.lv3.org", security_overrides)
        self.assertIn("'unsafe-eval'", security_overrides["grafana.lv3.org"]["content_security_policy"])
        self.assertIn("wss://n8n.lv3.org", security_overrides["n8n.lv3.org"]["content_security_policy"])
        self.assertIn("https://fonts.googleapis.com", security_overrides["docs.lv3.org"]["content_security_policy"])
        self.assertIn("https://cdn.jsdelivr.net", security_overrides["logs.lv3.org"]["content_security_policy"])
        self.assertIn("https://unpkg.com", security_overrides["ops.lv3.org"]["content_security_policy"])
        self.assertIn("wss://tasks.lv3.org", security_overrides["tasks.lv3.org"]["content_security_policy"])

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
        self.assertIn("site.server_sent_events | default(false)", self.template)
        self.assertIn("proxy_hide_header {{ header_name }};", self.template)
        self.assertIn("protected_site.unauthenticated_prefix_paths | default([])", self.template)
        self.assertIn("location ^~ {{ path }} {", self.template)
        self.assertIn("proxy_buffering off;", self.template)

    def test_template_renders_security_headers_from_default_and_override_maps(self) -> None:
        self.assertIn("public_edge_security_headers_default | combine(", self.template)
        self.assertIn('add_header Strict-Transport-Security', self.template)
        self.assertIn('add_header Cross-Origin-Resource-Policy', self.template)
        self.assertIn('add_header Content-Security-Policy', self.template)
        self.assertIn('add_header Permissions-Policy', self.template)
        self.assertIn('proxy_hide_header Cross-Origin-Resource-Policy;', self.template)
        self.assertIn('proxy_hide_header Content-Security-Policy;', self.template)


if __name__ == "__main__":
    unittest.main()
