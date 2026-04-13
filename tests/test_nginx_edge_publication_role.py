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

    def test_defaults_use_webroot_acme_with_pinned_hetzner_support(self) -> None:
        self.assertEqual(self.defaults["public_edge_acme_challenge_method"], "webroot")
        self.assertEqual(self.defaults["public_edge_control_plane_host"], "{{ groups['proxmox_hosts'][0] }}")
        self.assertEqual(self.defaults["public_edge_session_authority"], "{{ platform_session_authority }}")
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
        public_edge_service_topology_expr = self.defaults["public_edge_service_topology"]
        self.assertIn(
            "hostvars[public_edge_control_plane_host].public_edge_service_topology",
            public_edge_service_topology_expr,
        )
        self.assertIn(
            "hostvars[public_edge_control_plane_host].platform_service_topology",
            public_edge_service_topology_expr,
        )
        self.assertIn("default(platform_service_topology)", public_edge_service_topology_expr)
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
        self.assertEqual(self.defaults["public_edge_apex_hostname"], "{{ platform_domain }}")
        self.assertEqual(
            self.defaults["public_edge_additional_certificate_domains"], ["{{ public_edge_apex_hostname }}"]
        )
        self.assertEqual(self.defaults["public_edge_certbot_retries"], 6)
        self.assertEqual(self.defaults["public_edge_certbot_delay_seconds"], 15)
        self.assertEqual(self.defaults["public_edge_robots_meta_content"], "noindex, nofollow")
        self.assertEqual(
            self.defaults["public_edge_generated_build_root"],
            "{{ inventory_dir | dirname }}/build",
        )
        self.assertIn(
            "public_edge_service_topology.get('api_gateway', {})",
            self.defaults["public_edge_api_gateway_upstream"],
        )
        self.assertIn(
            "'internal',",
            self.defaults["public_edge_api_gateway_upstream"],
        )
        self.assertIn("User-agent: *", self.defaults["public_edge_robots_txt_content"])
        self.assertIn("Disallow: /", self.defaults["public_edge_robots_txt_content"])

    def test_ops_portal_defaults_use_authenticated_proxy_mode(self) -> None:
        extra_hostnames = [site["hostname"] for site in self.defaults["public_edge_extra_sites"]]
        protected_sites = self.defaults["public_edge_authenticated_sites"]

        self.assertIsNone(self.defaults.get("public_edge_ops_portal_publication"))
        self.assertNotIn("ops.{{ platform_domain }}", extra_hostnames)
        self.assertEqual(
            sorted(protected_sites),
            [
                "agents.{{ platform_domain }}",
                "analytics.{{ platform_domain }}",
                "annotate.{{ platform_domain }}",
                "billing.{{ platform_domain }}",
                "changelog.{{ platform_domain }}",
                "coolify.{{ platform_domain }}",
                "docs.{{ platform_domain }}",
                "draw.{{ platform_domain }}",
                "flags.{{ platform_domain }}",
                "home.{{ platform_domain }}",
                "langfuse.{{ platform_domain }}",
                "logs.{{ platform_domain }}",
                "minio-console.{{ platform_domain }}",
                "n8n.{{ platform_domain }}",
                "ops.{{ platform_domain }}",
                "tasks.{{ platform_domain }}",
            ],
        )
        self.assertEqual(
            protected_sites["analytics.{{ platform_domain }}"]["auth_proxy_upstream"], "http://127.0.0.1:4180"
        )
        self.assertEqual(
            protected_sites["annotate.{{ platform_domain }}"]["auth_proxy_upstream"], "http://127.0.0.1:4180"
        )
        self.assertNotIn("unauthenticated_paths", protected_sites["annotate.{{ platform_domain }}"])
        self.assertEqual(
            protected_sites["analytics.{{ platform_domain }}"]["unauthenticated_paths"],
            [
                "/api/error",
                "/api/event",
                "/api/health",
                "/api/system/health/live",
                "/api/system/health/ready",
            ],
        )
        self.assertEqual(
            protected_sites["analytics.{{ platform_domain }}"]["unauthenticated_prefix_paths"],
            ["/js/"],
        )
        self.assertEqual(protected_sites["flags.{{ platform_domain }}"]["auth_proxy_upstream"], "http://127.0.0.1:4180")
        self.assertEqual(protected_sites["flags.{{ platform_domain }}"]["unauthenticated_paths"], ["/health"])
        self.assertEqual(
            protected_sites["billing.{{ platform_domain }}"]["unauthenticated_proxy_routes"],
            [
                {"path": "/api/health", "upstream": "{{ public_edge_api_gateway_upstream }}/v1/billing/health"},
                {"path": "/api/v1/events", "upstream": "{{ public_edge_api_gateway_upstream }}/v1/billing/events"},
            ],
        )
        self.assertEqual(protected_sites["agents.{{ platform_domain }}"]["unauthenticated_paths"], ["/healthz"])
        self.assertEqual(
            protected_sites["agents.{{ platform_domain }}"]["auth_proxy_upstream"], "http://127.0.0.1:4180"
        )
        self.assertNotIn("unauthenticated_paths", protected_sites["coolify.{{ platform_domain }}"])
        self.assertNotIn("unauthenticated_paths", protected_sites["draw.{{ platform_domain }}"])
        self.assertNotIn("unauthenticated_paths", protected_sites["langfuse.{{ platform_domain }}"])
        self.assertNotIn("unauthenticated_paths", protected_sites["minio-console.{{ platform_domain }}"])
        self.assertEqual(protected_sites["n8n.{{ platform_domain }}"]["unauthenticated_paths"], ["/healthz"])
        self.assertEqual(
            protected_sites["n8n.{{ platform_domain }}"]["unauthenticated_prefix_paths"],
            ["/webhook/", "/webhook-test/", "/webhook-waiting/"],
        )
        self.assertEqual(protected_sites["ops.{{ platform_domain }}"]["unauthenticated_paths"], ["/health"])
        self.assertEqual(protected_sites["ops.{{ platform_domain }}"]["unauthenticated_prefix_paths"], ["/static/"])
        self.assertNotIn("unauthenticated_paths", protected_sites["docs.{{ platform_domain }}"])
        self.assertNotIn("unauthenticated_paths", protected_sites["changelog.{{ platform_domain }}"])
        self.assertNotIn("unauthenticated_paths", protected_sites["logs.{{ platform_domain }}"])
        self.assertNotIn("unauthenticated_paths", protected_sites["home.{{ platform_domain }}"])
        self.assertEqual(protected_sites["tasks.{{ platform_domain }}"]["auth_proxy_upstream"], "http://127.0.0.1:4180")

    def test_tasks_include_dns_hetzner_plugin_and_credentials_flow(self) -> None:
        task_names = {task["name"] for task in self.tasks}

        self.assertIn("Resolve public edge site and certificate catalogs", task_names)
        self.assertIn("Install the pinned Certbot Hetzner DNS plugin", task_names)
        self.assertIn(
            "Derive site-local certificate requests for hostnames missing from the shared certificate",
            task_names,
        )
        self.assertIn(
            "Ensure site-local Let's Encrypt certificates exist for hostnames missing from the shared certificate",
            task_names,
        )
        self.assertIn(
            "Assert the Hetzner DNS credential file is available when DNS-01 is enabled",
            task_names,
        )
        self.assertIn("Render the crawl policy robots.txt", task_names)
        publish_task = next(task for task in self.tasks if task["name"] == "Publish generated static site directories")
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
        obtain_task = next(
            task for task in self.tasks if task["name"] == "Obtain the public edge Let's Encrypt certificate"
        )
        site_local_task = next(
            task
            for task in self.tasks
            if task["name"]
            == "Ensure site-local Let's Encrypt certificates exist for hostnames missing from the shared certificate"
        )
        self.assertEqual(obtain_task["register"], "public_edge_certbot_issue")
        self.assertEqual(obtain_task["retries"], "{{ public_edge_certbot_retries }}")
        self.assertEqual(obtain_task["delay"], "{{ public_edge_certbot_delay_seconds }}")
        self.assertEqual(obtain_task["until"], "public_edge_certbot_issue.rc == 0")
        self.assertEqual(site_local_task["loop"], "{{ public_edge_site_certificate_requirements | default([]) }}")
        self.assertEqual(site_local_task["when"], "item.missing_domains | length > 0")

    def test_tasks_resolve_edge_catalogs_before_validation(self) -> None:
        task_names = [task["name"] for task in self.tasks]
        resolve_index = task_names.index("Resolve public edge site and certificate catalogs")
        validate_index = task_names.index("Validate public edge publication inputs")

        self.assertLess(resolve_index, validate_index)
        resolve_task = self.tasks[resolve_index]
        resolved_facts = resolve_task["ansible.builtin.set_fact"]
        self.assertIn("service_topology_edge_certificate_domains", resolved_facts["public_edge_certificate_domains"])
        self.assertIn("public_edge_extra_sites", resolved_facts["public_edge_certificate_domains"])
        self.assertIn("service_topology_edge_sites", resolved_facts["public_edge_sites"])
        self.assertIn("public_edge_extra_sites", resolved_facts["public_edge_sites"])

    def test_certificate_san_regex_preserves_domains_with_s_characters(self) -> None:
        derive_task = next(
            task for task in self.tasks if task["name"] == "Derive current and missing public edge certificate domains"
        )
        current_domains_expr = derive_task["ansible.builtin.set_fact"]["public_edge_current_certificate_domains"]

        self.assertIn("regex_findall('DNS:([^, ]+)')", current_domains_expr)

    def test_defaults_include_public_docs_site(self) -> None:
        docs_site = next(
            site
            for site in self.defaults["public_edge_extra_sites"]
            if site["hostname"] == "docs.{{ platform_domain }}"
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
        self.assertIn("annotate.{{ platform_domain }}", security_overrides)
        self.assertIn("coolify.{{ platform_domain }}", security_overrides)
        self.assertIn("draw.{{ platform_domain }}", security_overrides)
        self.assertIn("grafana.{{ platform_domain }}", security_overrides)
        self.assertIn("logs.{{ platform_domain }}", security_overrides)
        self.assertIn("tasks.{{ platform_domain }}", security_overrides)
        self.assertIn(
            "https://annotate.{{ platform_domain }}",
            security_overrides["annotate.{{ platform_domain }}"]["content_security_policy"],
        )
        self.assertIn("'unsafe-eval'", security_overrides["coolify.{{ platform_domain }}"]["content_security_policy"])
        self.assertIn(
            "wss://draw.{{ platform_domain }}",
            security_overrides["draw.{{ platform_domain }}"]["content_security_policy"],
        )
        self.assertIn("'unsafe-eval'", security_overrides["grafana.{{ platform_domain }}"]["content_security_policy"])
        self.assertIn(
            "wss://n8n.{{ platform_domain }}",
            security_overrides["n8n.{{ platform_domain }}"]["content_security_policy"],
        )
        self.assertIn(
            "https://fonts.googleapis.com",
            security_overrides["docs.{{ platform_domain }}"]["content_security_policy"],
        )
        self.assertIn(
            "https://cdn.jsdelivr.net",
            security_overrides["logs.{{ platform_domain }}"]["content_security_policy"],
        )
        self.assertIn("https://unpkg.com", security_overrides["ops.{{ platform_domain }}"]["content_security_policy"])
        self.assertIn(
            "style-src 'self' 'unsafe-inline' https://unpkg.com",
            security_overrides["ops.{{ platform_domain }}"]["content_security_policy"],
        )
        self.assertIn(
            "font-src 'self' data: https://unpkg.com",
            security_overrides["ops.{{ platform_domain }}"]["content_security_policy"],
        )
        self.assertIn("wiki.{{ platform_domain }}", security_overrides)
        self.assertIn("'unsafe-inline'", security_overrides["wiki.{{ platform_domain }}"]["content_security_policy"])
        self.assertIn(
            "https://wiki.{{ platform_domain }}",
            security_overrides["wiki.{{ platform_domain }}"]["content_security_policy"],
        )
        self.assertIn(
            "wss://tasks.{{ platform_domain }}",
            security_overrides["tasks.{{ platform_domain }}"]["content_security_policy"],
        )

    def test_template_supports_root_proxy_path_override(self) -> None:
        self.assertIn("site.root_proxy_path is defined", self.template)
        self.assertIn("location = / {", self.template)
        self.assertIn("_raw_key in public_edge_authenticated_sites", self.template)
        self.assertIn("protected_site.unauthenticated_proxy_routes | default([])", self.template)
        self.assertIn('add_header X-Robots-Tag "{{ public_edge_robots_meta_content }}" always;', self.template)
        self.assertIn("location = /robots.txt {", self.template)
        self.assertIn("server_name {{ public_edge_apex_hostname }};", self.template)
        self.assertIn("site_tls_certificate_name(site)", self.template)
        self.assertIn("public_edge_site_tls_materials.get(site.hostname, public_edge_cert_name)", self.template)

    def test_certificate_domain_expression_includes_additional_domains(self) -> None:
        certificate_domains_expr = self.defaults["public_edge_certificate_domains"]
        self.assertIn("public_edge_additional_certificate_domains", certificate_domains_expr)
        self.assertNotIn(
            "registry.example.com", [site["hostname"] for site in self.defaults["public_edge_extra_sites"]]
        )

    def test_static_pages_include_robots_meta_tag(self) -> None:
        self.assertIn('<meta name="robots" content="{{ public_edge_robots_meta_content }}">', self.static_template)

    def test_minio_console_is_published_with_large_upload_and_header_passthrough_overrides(self) -> None:
        minio_console = next(
            site
            for site in self.defaults["public_edge_extra_sites"]
            if site["hostname"] == "minio-console.{{ platform_domain }}"
        )

        self.assertEqual(
            minio_console["upstream"],
            "http://{{ hostvars[playbook_execution_host_patterns.docker_runtime[playbook_execution_env]].ansible_host }}:{{ platform_port_assignments.minio_console_port }}",
        )
        self.assertEqual(minio_console["client_max_body_size"], 0)
        self.assertFalse(minio_console["security_headers_enabled"])
        self.assertTrue(minio_console["preserve_upstream_security_headers"])

    def test_template_supports_proxy_header_stripping_and_blocked_paths(self) -> None:
        self.assertIn("site.proxy_hide_headers | default([])", self.template)
        self.assertIn("site.blocked_exact_paths | default([])", self.template)
        self.assertIn("site.exact_redirects | default([])", self.template)
        self.assertIn("site.server_sent_events | default(false)", self.template)
        self.assertIn("site.prefix_proxy_routes | default([])", self.template)
        self.assertIn("site.client_max_body_size | default(none)", self.template)
        self.assertIn("site.proxy_request_buffering | default(true)", self.template)
        self.assertIn("site.proxy_read_timeout_seconds | default(300)", self.template)
        self.assertIn("site.proxy_send_timeout_seconds | default(proxy_read_timeout_seconds)", self.template)
        self.assertIn("location = {{ redirect.path }} {", self.template)
        self.assertIn(
            "return {{ redirect.status | default(301) }} {{ redirect.target | default(redirect.location) }};",
            self.template,
        )
        self.assertIn("proxy_hide_header {{ header_name }};", self.template)
        self.assertIn("protected_site.unauthenticated_prefix_paths | default([])", self.template)
        self.assertIn("location ^~ {{ path }} {", self.template)
        self.assertIn("location ^~ {{ route.path }} {", self.template)
        self.assertIn("proxy_buffering off;", self.template)
        self.assertIn("site_tls_enabled = public_edge_tls_enabled or", self.template)
        self.assertIn(
            "ssl_certificate /etc/letsencrypt/live/{{ site_tls_certificate_name(site) }}/fullchain.pem;", self.template
        )

    def test_template_supports_plausible_tracker_injection(self) -> None:
        plausible_mapping_expr = self.defaults["public_edge_plausible_tracked_sites"]

        self.assertIn("items2dict(key_name='hostname', value_name='site_domain')", plausible_mapping_expr)
        self.assertIn("macro plausible_tracking_domain(hostname)", self.template)
        self.assertIn("macro plausible_tracking_snippet(hostname)", self.template)
        self.assertIn("macro render_plausible_proxy_injection(site)", self.template)
        self.assertIn('proxy_set_header Accept-Encoding "";', self.template)
        self.assertIn("sub_filter_once on;", self.template)
        self.assertIn("sub_filter '</head>' '{{ plausible_tracking_snippet(site.hostname) }}</head>';", self.template)
        self.assertIn("public_edge_plausible_base_url not in content_security_policy", self.template)
        self.assertIn('data-api="{{ public_edge_plausible_base_url }}/api/event"', self.static_template)
        self.assertIn('src="{{ public_edge_plausible_base_url }}/js/script.js"', self.static_template)

    def test_template_renders_security_headers_from_default_and_override_maps(self) -> None:
        self.assertIn("site.security_headers_enabled | default(true)", self.template)
        self.assertIn("public_edge_security_headers_default | combine(", self.template)
        self.assertIn("add_header Strict-Transport-Security", self.template)
        self.assertIn("add_header Cross-Origin-Resource-Policy", self.template)
        self.assertIn("add_header Content-Security-Policy", self.template)
        self.assertIn("add_header Permissions-Policy", self.template)
        self.assertIn("site.preserve_upstream_security_headers | default(false)", self.template)
        self.assertIn("site.crawl_policy_enabled | default(true)", self.template)
        self.assertIn("proxy_hide_header Cross-Origin-Resource-Policy;", self.template)
        self.assertIn("proxy_hide_header Content-Security-Policy;", self.template)

    def test_template_renders_shared_session_logout_contract(self) -> None:
        self.assertIn("public_edge_session_authority.shared_logout_path", self.template)
        self.assertIn("public_edge_session_authority.shared_proxy_cleanup_path", self.template)
        self.assertIn("public_edge_session_authority.shared_logged_out_path", self.template)
        self.assertIn("public_edge_session_authority.ops_portal_client_id", self.template)
        self.assertIn("oauth2_proxy_sign_out_url(", self.template)
        self.assertIn("keycloak_logout_url(", self.template)
        self.assertIn("site.hostname == public_edge_session_authority.authority_hostname", self.template)
        self.assertIn("map $http_authorization $lv3_logout_id_token", self.template)
        self.assertIn("location @lv3_shared_logout_without_session {", self.template)
        self.assertIn("id_token_hint={{ id_token_hint }}", self.template)
        self.assertIn("id_token_hint={id_token}", self.template)
        self.assertIn("'$lv3_logout_id_token'", self.template)
        self.assertIn('add_header Cache-Control "no-store" always;', self.template)
        self.assertIn('add_header Clear-Site-Data "\\"cache\\", \\"cookies\\", \\"storage\\"" always;', self.template)

    def test_template_renders_stale_session_recovery_contract(self) -> None:
        self.assertIn("location = /oauth2/callback {", self.template)
        self.assertIn("proxy_intercept_errors on;", self.template)
        self.assertIn("error_page 500 = @oauth2_stale_session_reset;", self.template)
        self.assertIn("location @oauth2_stale_session_reset {", self.template)
        self.assertIn("public_edge_session_authority.cookie_name }}_csrf", self.template)
        self.assertIn('add_header Cache-Control "no-store" always;', self.template)
        self.assertIn('public_edge_session_authority.authority_hostname ~ "/"', self.template)
        self.assertIn("public_edge_session_authority.ops_portal_client_id | urlencode", self.template)


if __name__ == "__main__":
    unittest.main()
