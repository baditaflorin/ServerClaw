from pathlib import Path

import generate_platform_vars
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def iter_strings(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from iter_strings(item)
        return
    if isinstance(value, list):
        for item in value:
            yield from iter_strings(item)
        return
    if isinstance(value, str):
        yield value


def test_resolve_tcp_proxy_port_supports_platform_port_assignments_templates() -> None:
    ports = {"platform_context_host_proxy_port": 8010}
    resolved = generate_platform_vars.resolve_tcp_proxy_port(
        "{{ platform_port_assignments.platform_context_host_proxy_port }}",
        ports,
    )
    assert resolved == 8010


def test_build_platform_vars_includes_langfuse_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    langfuse = platform_vars["platform_service_topology"]["langfuse"]

    assert langfuse["public_hostname"] == "langfuse.lv3.org"
    assert langfuse["dns"]["name"] == "langfuse"
    assert langfuse["ports"]["internal"] == 3002
    assert langfuse["urls"]["public"] == "https://langfuse.lv3.org"
    assert langfuse["urls"]["internal"] == "http://10.10.10.20:3002"
    assert platform_vars["outline_port"] == 3006


def test_build_platform_vars_includes_dify_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    dify = platform_vars["platform_service_topology"]["dify"]

    assert dify["public_hostname"] == "agents.lv3.org"
    assert dify["dns"]["name"] == "agents"
    assert dify["ports"]["internal"] == 8094
    assert dify["urls"]["public"] == "https://agents.lv3.org"
    assert dify["urls"]["internal"] == "http://10.10.10.20:8094"


def test_build_platform_vars_includes_changedetection_private_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    changedetection = platform_vars["platform_service_topology"]["changedetection"]

    assert changedetection["ports"]["internal"] == 5000
    assert changedetection["urls"]["internal"] == "http://10.10.10.20:5000"
    assert changedetection["exposure_model"] == "private-only"
    assert platform_vars["changedetection_port"] == 5000


def test_build_platform_vars_includes_directus_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    directus = platform_vars["platform_service_topology"]["directus"]

    assert directus["public_hostname"] == "data.lv3.org"
    assert directus["dns"]["name"] == "data"
    assert directus["ports"]["internal"] == 8055
    assert directus["urls"]["public"] == "https://data.lv3.org"
    assert directus["urls"]["internal"] == "http://10.10.10.20:8055"
    assert directus["edge"]["upstream"] == directus["urls"]["internal"]
    assert platform_vars["directus_port"] == 8055


def test_build_platform_vars_includes_crawl4ai_private_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    crawl4ai = platform_vars["platform_service_topology"]["crawl4ai"]

    assert crawl4ai["ports"]["internal"] == 11235
    assert crawl4ai["urls"]["internal"] == "http://10.10.10.20:11235"
    assert crawl4ai["exposure_model"] == "private-only"
    assert platform_vars["crawl4ai_port"] == 11235


def test_build_platform_vars_includes_paperless_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    paperless = platform_vars["platform_service_topology"]["paperless"]

    assert paperless["public_hostname"] == "paperless.lv3.org"
    assert paperless["dns"]["name"] == "paperless"
    assert paperless["ports"]["internal"] == 8018
    assert paperless["urls"]["public"] == "https://paperless.lv3.org"
    assert paperless["urls"]["internal"] == "http://10.10.10.20:8018"
    assert paperless["edge"]["client_max_body_size"] == "256m"
    assert paperless["edge"]["proxy_request_buffering"] is False
    assert paperless["edge"]["preserve_upstream_security_headers"] is True
    assert platform_vars["paperless_port"] == 8018


def test_build_platform_vars_includes_harbor_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    harbor = platform_vars["platform_service_topology"]["harbor"]

    assert harbor["public_hostname"] == "registry.lv3.org"
    assert harbor["dns"]["name"] == "registry"
    assert harbor["ports"]["internal"] == 8095
    assert harbor["urls"]["public"] == "https://registry.lv3.org"
    assert harbor["urls"]["internal"] == "http://10.10.10.20:8095"


def test_build_platform_vars_includes_openfga_private_controller_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    openfga = platform_vars["platform_service_topology"]["openfga"]

    assert openfga["ports"]["internal"] == 8098
    assert openfga["ports"]["controller"] == 8014
    assert openfga["urls"]["internal"] == "http://10.10.10.20:8098"
    assert openfga["urls"]["controller"] == "http://100.64.0.1:8014"
    assert platform_vars["openfga_controller_url"] == "http://100.64.0.1:8014"


def test_build_platform_vars_includes_temporal_private_loopback_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    temporal = platform_vars["platform_service_topology"]["temporal"]

    assert temporal["exposure_model"] == "private-only"
    assert temporal["private_ip"] == "10.10.10.20"
    assert temporal["access"]["kind"] == "ssh-tunnel"
    assert temporal["access"]["url"] == "grpc://127.0.0.1:7233"
    assert "urls" not in temporal or temporal["urls"] == {}

def test_build_platform_vars_includes_openbao_extra_bind_addresses() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()

    assert platform_vars["openbao_http_extra_bind_addresses"] == ["10.10.10.20"]


def test_build_platform_vars_includes_plausible_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    plausible = platform_vars["platform_service_topology"]["plausible"]

    assert plausible["public_hostname"] == "analytics.lv3.org"
    assert plausible["dns"]["name"] == "analytics"
    assert plausible["ports"]["internal"] == 8016
    assert plausible["urls"]["public"] == "https://analytics.lv3.org"
    assert plausible["urls"]["internal"] == "http://10.10.10.20:8016"
    assert plausible["edge"]["security_headers_enabled"] is False
    assert plausible["edge"]["preserve_upstream_security_headers"] is True


def test_build_platform_vars_includes_flagsmith_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    flagsmith = platform_vars["platform_service_topology"]["flagsmith"]

    assert flagsmith["public_hostname"] == "flags.lv3.org"
    assert flagsmith["dns"]["name"] == "flags"
    assert flagsmith["ports"]["internal"] == 8017
    assert flagsmith["urls"]["public"] == "https://flags.lv3.org"
    assert flagsmith["urls"]["internal"] == "http://10.10.10.20:8017"
    assert platform_vars["flagsmith_port"] == 8017


def test_build_platform_vars_includes_tika_private_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    tika = platform_vars["platform_service_topology"]["tika"]

    assert tika["ports"]["internal"] == 9998
    assert tika["urls"]["internal"] == "http://10.10.10.20:9998"
    assert tika["exposure_model"] == "private-only"


def test_build_platform_vars_includes_tesseract_ocr_private_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    tesseract_ocr = platform_vars["platform_service_topology"]["tesseract_ocr"]

    assert tesseract_ocr["ports"]["internal"] == 3008
    assert tesseract_ocr["urls"]["internal"] == "http://10.10.10.20:3008"
    assert tesseract_ocr["exposure_model"] == "private-only"
    assert platform_vars["tesseract_ocr_port"] == 3008


def test_build_platform_vars_includes_jupyterhub_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    jupyterhub = platform_vars["platform_service_topology"]["jupyterhub"]

    assert jupyterhub["public_hostname"] == "notebooks.lv3.org"
    assert jupyterhub["dns"]["name"] == "notebooks"
    assert jupyterhub["ports"]["internal"] == 8097
    assert jupyterhub["urls"]["public"] == "https://notebooks.lv3.org"
    assert jupyterhub["urls"]["internal"] == "http://10.10.10.20:8097"
    assert jupyterhub["edge"]["client_max_body_size"] == "2g"


def test_build_platform_vars_includes_piper_private_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    piper = platform_vars["platform_service_topology"]["piper"]

    assert piper["ports"]["internal"] == 8100
    assert piper["urls"]["internal"] == "http://10.10.10.20:8100"
    assert piper["exposure_model"] == "private-only"
    assert platform_vars["piper_port"] == 8100

def test_build_platform_vars_includes_redpanda_private_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    redpanda = platform_vars["platform_service_topology"]["redpanda"]

    assert redpanda["exposure_model"] == "private-only"
    assert redpanda["ports"]["internal"] == 9092
    assert redpanda["ports"]["admin"] == 9644
    assert redpanda["ports"]["http_proxy"] == 8103
    assert redpanda["ports"]["schema_registry"] == 8104
    assert redpanda["urls"]["internal"] == "kafka://10.10.10.20:9092"
    assert redpanda["urls"]["admin"] == "http://10.10.10.20:9644"
    assert redpanda["urls"]["http_proxy"] == "http://10.10.10.20:8103"
    assert redpanda["urls"]["schema_registry"] == "http://10.10.10.20:8104"
    assert platform_vars["redpanda_http_proxy_port"] == 8103
    assert platform_vars["redpanda_schema_registry_port"] == 8104


def test_build_platform_vars_includes_nextcloud_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    nextcloud = platform_vars["platform_service_topology"]["nextcloud"]

    assert nextcloud["public_hostname"] == "cloud.lv3.org"
    assert nextcloud["dns"]["name"] == "cloud"
    assert nextcloud["ports"]["internal"] == 8084
    assert nextcloud["urls"]["public"] == "https://cloud.lv3.org"
    assert nextcloud["urls"]["internal"] == "http://10.10.10.20:8084"
    assert nextcloud["edge"]["exact_redirects"] == [
        {"path": "/.well-known/carddav", "location": "/remote.php/dav/", "status": 301},
        {"path": "/.well-known/caldav", "location": "/remote.php/dav/", "status": 301},
    ]


def test_build_platform_vars_includes_shared_session_authority_contract() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    authority = platform_vars["platform_session_authority"]

    assert authority["authority_hostname"] == "ops.lv3.org"
    assert authority["ops_portal_client_id"] == "ops-portal-oauth"
    assert authority["keycloak_logout_url"] == "https://sso.lv3.org/realms/lv3/protocol/openid-connect/logout"
    assert authority["oauth2_proxy_sign_out_url"] == "https://ops.lv3.org/oauth2/sign_out"
    assert authority["shared_logout_path"] == "/.well-known/lv3/session/logout"
    assert authority["shared_proxy_cleanup_path"] == "/.well-known/lv3/session/proxy-logout"
    assert authority["shared_logged_out_path"] == "/.well-known/lv3/session/logged-out"
    assert authority["shared_logged_out_url"] == "https://ops.lv3.org/.well-known/lv3/session/logged-out"


def test_build_service_urls_supports_private_gitea_proxy_and_root_url() -> None:
    ports = {
        "gitea_http_port": 3003,
        "gitea_host_proxy_port": 3009,
    }
    service = {
        "owning_vm": "docker-runtime-lv3",
        "public_hostname": "git.lv3.org",
    }
    port_map, urls = generate_platform_vars.build_service_urls(
        "gitea",
        service,
        {"management_tailscale_ipv4": "100.64.0.1"},
        {"docker-runtime-lv3": "10.10.10.20"},
        ports,
        {"desired_state": {"host_id": "proxmox_florin"}},
    )

    assert port_map == {"internal": 3003, "controller": 3009}
    assert urls == {
        "public": "http://git.lv3.org:3009",
        "internal": "http://10.10.10.20:3003",
        "controller": "http://100.64.0.1:3009",
    }


def test_build_service_urls_supports_private_nomad_controller_url() -> None:
    ports = {
        "nomad_server_port": 4646,
        "nomad_host_proxy_port": 8013,
    }
    service = {
        "owning_vm": "monitoring-lv3",
    }
    host_vars = {"management_tailscale_ipv4": "100.64.0.1"}
    guest_ipv4_by_name = {"monitoring-lv3": "10.10.10.40"}
    stack = {"desired_state": {"host_id": "proxmox_florin"}}

    port_map, urls = generate_platform_vars.build_service_urls(
        "nomad",
        service,
        host_vars,
        guest_ipv4_by_name,
        ports,
        stack,
    )

    assert port_map == {"internal": 4646, "controller": 8013}
    assert urls == {
        "internal": "https://10.10.10.40:4646",
        "controller": "https://100.64.0.1:8013",
    }


def test_build_service_urls_resolves_homepage_internal_url() -> None:
    ports = {"homepage_port": 3090}
    service = {"owning_vm": "docker-runtime-lv3"}
    host_vars = {"management_tailscale_ipv4": "100.118.189.95"}
    guest_ipv4_by_name = {"docker-runtime-lv3": "10.10.10.20"}
    stack = {"desired_state": {"host_id": "proxmox_florin"}}

    port_map, urls = generate_platform_vars.build_service_urls(
        "homepage",
        service,
        host_vars,
        guest_ipv4_by_name,
        ports,
        stack,
    )

    assert port_map == {"internal": 3090}
    assert urls == {"internal": "http://10.10.10.20:3090"}


def test_build_service_urls_resolves_excalidraw_internal_url() -> None:
    ports = {"excalidraw_port": 3095}
    service = {"owning_vm": "docker-runtime-lv3", "public_hostname": "draw.lv3.org"}
    host_vars = {"management_tailscale_ipv4": "100.118.189.95"}
    guest_ipv4_by_name = {"docker-runtime-lv3": "10.10.10.20"}
    stack = {"desired_state": {"host_id": "proxmox_florin"}}

    port_map, urls = generate_platform_vars.build_service_urls(
        "excalidraw",
        service,
        host_vars,
        guest_ipv4_by_name,
        ports,
        stack,
    )

    assert port_map == {"internal": 3095}
    assert urls == {
        "public": "https://draw.lv3.org",
        "internal": "http://10.10.10.20:3095",
    }


def test_build_service_urls_resolves_outline_internal_url() -> None:
    ports = {"outline_port": 3006}
    service = {"owning_vm": "docker-runtime-lv3", "public_hostname": "wiki.lv3.org"}
    host_vars = {"management_tailscale_ipv4": "100.118.189.95"}
    guest_ipv4_by_name = {"docker-runtime-lv3": "10.10.10.20"}
    stack = {"desired_state": {"host_id": "proxmox_florin"}}

    port_map, urls = generate_platform_vars.build_service_urls(
        "outline",
        service,
        host_vars,
        guest_ipv4_by_name,
        ports,
        stack,
    )

    assert port_map == {"internal": 3006}
    assert urls == {
        "public": "https://wiki.lv3.org",
        "internal": "http://10.10.10.20:3006",
    }


def test_build_service_urls_resolves_jupyterhub_internal_url() -> None:
    ports = {"jupyterhub_port": 8097}
    service = {"owning_vm": "docker-runtime-lv3", "public_hostname": "notebooks.lv3.org"}
    host_vars = {"management_tailscale_ipv4": "100.118.189.95"}
    guest_ipv4_by_name = {"docker-runtime-lv3": "10.10.10.20"}
    stack = {"desired_state": {"host_id": "proxmox_florin"}}

    port_map, urls = generate_platform_vars.build_service_urls(
        "jupyterhub",
        service,
        host_vars,
        guest_ipv4_by_name,
        ports,
        stack,
    )

    assert port_map == {"internal": 8097}
    assert urls == {
        "public": "https://notebooks.lv3.org",
        "internal": "http://10.10.10.20:8097",
    }

def test_build_service_urls_resolves_paperless_internal_url() -> None:
    ports = {"paperless_port": 8018}
    service = {"owning_vm": "docker-runtime-lv3", "public_hostname": "paperless.lv3.org"}
    host_vars = {"management_tailscale_ipv4": "100.118.189.95"}
    guest_ipv4_by_name = {"docker-runtime-lv3": "10.10.10.20"}
    stack = {"desired_state": {"host_id": "proxmox_florin"}}

    port_map, urls = generate_platform_vars.build_service_urls(
        "paperless",
        service,
        host_vars,
        guest_ipv4_by_name,
        ports,
        stack,
    )

    assert port_map == {"internal": 8018}
    assert urls == {
        "public": "https://paperless.lv3.org",
        "internal": "http://10.10.10.20:8018",
    }


def test_build_service_urls_resolves_piper_internal_url() -> None:
    ports = {"piper_port": 8100}
    service = {"owning_vm": "docker-runtime-lv3"}
    host_vars = {"management_tailscale_ipv4": "100.118.189.95"}
    guest_ipv4_by_name = {"docker-runtime-lv3": "10.10.10.20"}
    stack = {"desired_state": {"host_id": "proxmox_florin"}}

    port_map, urls = generate_platform_vars.build_service_urls(
        "piper",
        service,
        host_vars,
        guest_ipv4_by_name,
        ports,
        stack,
    )

    assert port_map == {"internal": 8100}
    assert urls == {"internal": "http://10.10.10.20:8100"}


def test_build_platform_vars_renders_service_topology_without_unresolved_templates() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    service_topology = platform_vars["platform_service_topology"]

    assert all("{{" not in value and "}}" not in value for value in iter_strings(service_topology))
    assert service_topology["headscale"]["private_ip"] == platform_vars["platform_host"]["network"]["internal_ipv4"]
    assert service_topology["outline"]["edge"]["upstream"] == service_topology["outline"]["urls"]["internal"]
    assert service_topology["excalidraw"]["edge"]["prefix_proxy_routes"][0]["upstream"] == "http://10.10.10.20:3096"


def test_tika_network_policy_allows_proxmox_host_private_probe() -> None:
    host_vars = yaml.safe_load((REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml").read_text(encoding="utf-8"))
    allowed_inbound = host_vars["network_policy"]["guests"]["docker-runtime-lv3"]["allowed_inbound"]

    assert any(rule["source"] == "host" and 9998 in rule["ports"] for rule in allowed_inbound)


def test_build_platform_vars_includes_plane_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    plane = platform_vars["platform_service_topology"]["plane"]

    assert plane["public_hostname"] == "tasks.lv3.org"
    assert plane["dns"]["name"] == "tasks"
    assert plane["ports"]["internal"] == 8093
    assert plane["ports"]["controller"] == 8011
    assert plane["urls"]["public"] == "https://tasks.lv3.org"
    assert plane["urls"]["controller"] == "http://100.64.0.1:8011"


def test_build_platform_vars_includes_woodpecker_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    woodpecker = platform_vars["platform_service_topology"]["woodpecker"]

    assert woodpecker["public_hostname"] == "ci.lv3.org"
    assert woodpecker["dns"]["name"] == "ci"
    assert woodpecker["ports"]["internal"] == 8102
    assert woodpecker["ports"]["controller"] == 8017
    assert woodpecker["urls"]["public"] == "https://ci.lv3.org"
    assert woodpecker["urls"]["controller"] == "http://100.64.0.1:8017"


def test_woodpecker_network_policy_allows_host_and_edge_access() -> None:
    host_vars = yaml.safe_load((REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml").read_text(encoding="utf-8"))
    allowed_inbound = host_vars["network_policy"]["guests"]["docker-runtime-lv3"]["allowed_inbound"]

    assert any(rule["source"] == "host" and 8102 in rule["ports"] for rule in allowed_inbound)
    assert any(rule["source"] == "nginx-lv3" and 8102 in rule["ports"] for rule in allowed_inbound)


def test_build_platform_vars_uses_loopback_for_guest_local_platform_context_verification() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()

    assert platform_vars["platform_context_private_url"] == "http://127.0.0.1:8010"


def test_build_platform_vars_includes_matrix_synapse_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    matrix_synapse = platform_vars["platform_service_topology"]["matrix_synapse"]

    assert matrix_synapse["public_hostname"] == "matrix.lv3.org"
    assert matrix_synapse["dns"]["name"] == "matrix"
    assert matrix_synapse["ports"]["internal"] == 8008
    assert matrix_synapse["ports"]["controller"] == 8015
    assert matrix_synapse["urls"]["public"] == "https://matrix.lv3.org"
    assert matrix_synapse["urls"]["controller"] == "http://100.64.0.1:8015"


def test_build_service_urls_resolves_realtime_internal_url() -> None:
    ports = {"netdata_port": 19999}
    service = {"owning_vm": "monitoring-lv3"}
    host_vars = {"management_tailscale_ipv4": "100.118.189.95"}
    guest_ipv4_by_name = {"monitoring-lv3": "10.10.10.40"}
    stack = {"desired_state": {"host_id": "proxmox_florin"}}

    port_map, urls = generate_platform_vars.build_service_urls(
        "realtime",
        service,
        host_vars,
        guest_ipv4_by_name,
        ports,
        stack,
    )

    assert port_map == {"internal": 19999}
    assert urls == {"internal": "http://10.10.10.40:19999"}


def test_build_service_urls_include_coolify_controller_and_apps_endpoints() -> None:
    ports = {
        "coolify_dashboard_port": 8000,
        "coolify_proxy_port": 80,
        "coolify_proxy_tls_port": 443,
        "coolify_host_proxy_port": 8012,
    }
    host_vars = {"management_tailscale_ipv4": "100.64.0.1"}
    guest_ipv4_by_name = {"coolify-lv3": "10.10.10.70"}
    stack = {"desired_state": {"host_id": "proxmox_florin"}}

    controller_port_map, controller_urls = generate_platform_vars.build_service_urls(
        "coolify",
        {"owning_vm": "coolify-lv3", "public_hostname": "coolify.lv3.org"},
        host_vars,
        guest_ipv4_by_name,
        ports,
        stack,
    )
    app_port_map, app_urls = generate_platform_vars.build_service_urls(
        "coolify_apps",
        {"owning_vm": "coolify-lv3", "public_hostname": "apps.lv3.org"},
        host_vars,
        guest_ipv4_by_name,
        ports,
        stack,
    )
    assert controller_port_map == {"internal": 8000, "controller": 8012}
    assert controller_urls == {
        "public": "https://coolify.lv3.org",
        "internal": "http://10.10.10.70:8000",
        "controller": "http://100.64.0.1:8012",
    }
    assert app_port_map == {"internal": 443}
    assert app_urls == {
        "public": "https://apps.lv3.org",
        "internal": "https://10.10.10.70:443",
    }


def test_build_platform_vars_includes_coolify_wildcard_dns_record() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()

    wildcard_record = next(
        record for record in platform_vars["hetzner_dns_records"] if record["name"] == "*.apps"
    )

    assert wildcard_record == {
        "name": "*.apps",
        "type": "A",
        "value": "65.108.75.123",
        "ttl": 60,
    }
