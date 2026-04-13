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

    assert langfuse["public_hostname"] == "langfuse.example.com"
    assert langfuse["dns"]["name"] == "langfuse"
    assert langfuse["ports"]["internal"] == 3002
    assert langfuse["urls"]["public"] == "https://langfuse.example.com"
    assert langfuse["urls"]["internal"] == "http://10.10.10.20:3002"
    assert platform_vars["outline_port"] == 3006


def test_build_platform_vars_resolves_guest_ip_templates_in_platform_host_network() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    network = platform_vars["platform_host"]["network"]

    assert network["public_ingress_tcp_forwards"][0]["target_host"] == "10.10.10.92"
    assert network["public_ingress_tcp_forwards"][1]["target_host"] == "10.10.10.10"
    assert network["tailscale_operator_target_guest"] == "10.10.10.30"
    assert network["tailscale_tcp_proxies"][1]["upstream_host"] == "10.10.10.50"
    assert all("proxmox_guests" not in value for value in iter_strings(network))


def test_build_platform_vars_includes_minio_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    minio = platform_vars["platform_service_topology"]["minio"]
    dns_records = {
        (record["name"], record["type"], record["value"], record["ttl"])
        for record in platform_vars["hetzner_dns_records"]
    }

    assert minio["public_hostname"] == "minio.example.com"
    assert minio["console_public_hostname"] == "minio-console.example.com"
    assert minio["ports"]["internal"] == 9010
    assert minio["ports"]["console"] == 9011
    assert minio["urls"]["public"] == "https://minio.example.com"
    assert minio["urls"]["internal"] == "http://10.10.10.20:9010"
    assert minio["urls"]["console_internal"] == "http://10.10.10.20:9011"
    assert minio["urls"]["console_public"] == "https://minio-console.example.com"
    assert platform_vars["minio_public_url"] == "https://minio.example.com"
    assert platform_vars["minio_console_public_url"] == "https://minio-console.example.com"
    assert ("minio", "A", "203.0.113.1", 60) in dns_records
    assert ("minio-console", "A", "203.0.113.1", 60) in dns_records


def test_build_platform_vars_includes_livekit_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    livekit = platform_vars["platform_service_topology"]["livekit"]

    assert livekit["public_hostname"] == "livekit.example.com"
    assert livekit["dns"]["name"] == "livekit"
    assert livekit["ports"]["internal"] == 7880
    assert livekit["ports"]["media_tcp"] == 7881
    assert livekit["ports"]["media_udp"] == 7882
    assert livekit["urls"]["public"] == "https://livekit.example.com"
    assert livekit["urls"]["internal"] == "http://10.10.10.20:7880"
    assert livekit["edge"]["noindex"] is True
    assert livekit["edge"]["kind"] == "proxy"


def test_build_platform_vars_includes_ntfy_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    ntfy = platform_vars["platform_service_topology"]["ntfy"]
    dns_records = {
        (record["name"], record["type"], record["value"], record["ttl"])
        for record in platform_vars["hetzner_dns_records"]
    }

    assert ntfy["public_hostname"] == "ntfy.example.com"
    assert ntfy["dns"]["name"] == "ntfy"
    assert ntfy["ports"]["internal"] == 2586
    assert ntfy["urls"]["public"] == "https://ntfy.example.com"
    assert ntfy["urls"]["internal"] == "http://10.10.10.20:2586"
    assert ntfy["edge"]["kind"] == "proxy"
    assert ntfy["edge"]["upstream"] == "http://10.10.10.20:2586"
    assert ("ntfy", "A", "203.0.113.1", 60) in dns_records
    assert platform_vars["ntfy_port"] == 2586


def test_build_platform_vars_includes_dify_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    dify = platform_vars["platform_service_topology"]["dify"]

    assert dify["public_hostname"] == "agents.example.com"
    assert dify["dns"]["name"] == "agents"
    assert dify["ports"]["internal"] == 8094
    assert dify["urls"]["public"] == "https://agents.example.com"
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

    assert directus["public_hostname"] == "data.example.com"
    assert directus["dns"]["name"] == "data"
    assert directus["ports"]["internal"] == 8055
    assert directus["urls"]["public"] == "https://data.example.com"
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


def test_build_platform_vars_includes_falco_bridge_port() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()

    assert platform_vars["falco_event_bridge_port"] == 18084


def test_build_platform_vars_includes_paperless_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    paperless = platform_vars["platform_service_topology"]["paperless"]

    assert paperless["public_hostname"] == "paperless.example.com"
    assert paperless["dns"]["name"] == "paperless"
    assert paperless["ports"]["internal"] == 8018
    assert paperless["urls"]["public"] == "https://paperless.example.com"
    assert paperless["urls"]["internal"] == "http://10.10.10.20:8018"
    assert paperless["edge"]["client_max_body_size"] == "256m"
    assert paperless["edge"]["proxy_request_buffering"] is False
    assert paperless["edge"]["preserve_upstream_security_headers"] is True
    assert platform_vars["paperless_port"] == 8018


def test_build_platform_vars_includes_harbor_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    harbor = platform_vars["platform_service_topology"]["harbor"]

    assert harbor["public_hostname"] == "registry.example.com"
    assert harbor["dns"]["name"] == "registry"
    assert harbor["ports"]["internal"] == 8095
    assert harbor["urls"]["public"] == "https://registry.example.com"
    assert harbor["urls"]["internal"] == "http://10.10.10.92:8095"


def test_build_platform_vars_includes_openfga_private_controller_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    openfga = platform_vars["platform_service_topology"]["openfga"]

    assert openfga["ports"]["internal"] == 8098
    assert openfga["ports"]["controller"] == 8014
    assert openfga["urls"]["internal"] == "http://10.10.10.92:8098"
    assert openfga["urls"]["controller"] == "http://100.64.0.1:8014"
    assert platform_vars["openfga_controller_url"] == "http://100.64.0.1:8014"


def test_build_platform_vars_includes_temporal_private_loopback_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    temporal = platform_vars["platform_service_topology"]["temporal"]

    assert temporal["exposure_model"] == "private-only"
    assert temporal["private_ip"] == "10.10.10.92"
    assert temporal["access"]["kind"] == "ssh-tunnel"
    assert temporal["access"]["url"] == "grpc://127.0.0.1:7233"
    assert "urls" not in temporal or temporal["urls"] == {}


def test_build_platform_vars_includes_openbao_extra_bind_addresses() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()

    assert platform_vars["openbao_http_extra_bind_addresses"] == ["10.10.10.92"]


def test_build_platform_vars_includes_plausible_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    plausible = platform_vars["platform_service_topology"]["plausible"]

    assert plausible["public_hostname"] == "analytics.example.com"
    assert plausible["dns"]["name"] == "analytics"
    assert plausible["ports"]["internal"] == 8016
    assert plausible["urls"]["public"] == "https://analytics.example.com"
    assert plausible["urls"]["internal"] == "http://10.10.10.20:8016"
    assert plausible["edge"]["security_headers_enabled"] is False
    assert plausible["edge"]["preserve_upstream_security_headers"] is True


def test_build_platform_vars_includes_flagsmith_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    flagsmith = platform_vars["platform_service_topology"]["flagsmith"]

    assert flagsmith["public_hostname"] == "flags.example.com"
    assert flagsmith["dns"]["name"] == "flags"
    assert flagsmith["ports"]["internal"] == 8017
    assert flagsmith["urls"]["public"] == "https://flags.example.com"
    assert flagsmith["urls"]["internal"] == "http://10.10.10.20:8017"
    assert platform_vars["flagsmith_port"] == 8017


def test_build_platform_vars_includes_lago_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    lago = platform_vars["platform_service_topology"]["lago"]

    assert lago["public_hostname"] == "billing.example.com"
    assert lago["dns"]["name"] == "billing"
    assert lago["ports"]["internal"] == 8100
    assert lago["ports"]["api"] == 8099
    assert lago["urls"]["public"] == "https://billing.example.com"
    assert lago["urls"]["internal"] == "http://10.10.10.20:8100"
    assert lago["urls"]["api"] == "http://10.10.10.20:8099"
    assert lago["edge"]["prefix_proxy_routes"] == [{"path": "/api/", "upstream": "http://10.10.10.20:8099"}]
    assert platform_vars["lago_api_port"] == 8099
    assert platform_vars["lago_front_port"] == 8100


def test_build_platform_vars_includes_tika_private_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    tika = platform_vars["platform_service_topology"]["tika"]

    assert tika["ports"]["internal"] == 9998
    assert tika["urls"]["internal"] == "http://10.10.10.90:9998"
    assert tika["exposure_model"] == "private-only"
    assert tika["runtime_pool"] == "runtime-ai"
    assert tika["deployment_surface"] == "playbooks/services/tika.yml"


def test_build_platform_vars_includes_gotenberg_private_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    gotenberg = platform_vars["platform_service_topology"]["gotenberg"]

    assert gotenberg["ports"]["internal"] == 3007
    assert gotenberg["urls"]["internal"] == "http://10.10.10.90:3007"
    assert gotenberg["exposure_model"] == "private-only"
    assert gotenberg["runtime_pool"] == "runtime-ai"
    assert gotenberg["deployment_surface"] == "playbooks/services/gotenberg.yml"


def test_build_platform_vars_includes_tesseract_ocr_private_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    tesseract_ocr = platform_vars["platform_service_topology"]["tesseract_ocr"]

    assert tesseract_ocr["ports"]["internal"] == 3008
    assert tesseract_ocr["urls"]["internal"] == "http://10.10.10.90:3008"
    assert tesseract_ocr["exposure_model"] == "private-only"
    assert tesseract_ocr["runtime_pool"] == "runtime-ai"
    assert tesseract_ocr["deployment_surface"] == "playbooks/services/tesseract-ocr.yml"
    assert platform_vars["tesseract_ocr_port"] == 3008


def test_build_platform_vars_includes_superset_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    superset = platform_vars["platform_service_topology"]["superset"]

    assert superset["public_hostname"] == "bi.example.com"
    assert superset["dns"]["name"] == "bi"
    assert superset["ports"]["internal"] == 8105
    assert superset["urls"]["public"] == "https://bi.example.com"
    assert superset["urls"]["internal"] == "http://10.10.10.20:8105"
    assert superset["edge"]["upstream"] == superset["urls"]["internal"]
    assert platform_vars["superset_port"] == 8105


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


def test_build_platform_vars_includes_label_studio_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    label_studio = platform_vars["platform_service_topology"]["label_studio"]

    assert label_studio["public_hostname"] == "annotate.example.com"
    assert label_studio["dns"]["name"] == "annotate"
    assert label_studio["ports"]["internal"] == 8110
    assert label_studio["urls"]["public"] == "https://annotate.example.com"
    assert label_studio["urls"]["internal"] == "http://10.10.10.20:8110"
    assert platform_vars["label_studio_port"] == 8110


def test_build_platform_vars_includes_typesense_private_controller_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    typesense = platform_vars["platform_service_topology"]["typesense"]

    assert typesense["ports"]["internal"] == 8108
    assert typesense["ports"]["controller"] == 8016
    assert typesense["urls"]["internal"] == "http://10.10.10.20:8108"
    assert typesense["urls"]["controller"] == "http://100.64.0.1:8016"
    assert platform_vars["typesense_controller_url"] == "http://100.64.0.1:8016"


def test_build_platform_vars_includes_nextcloud_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    nextcloud = platform_vars["platform_service_topology"]["nextcloud"]

    assert nextcloud["public_hostname"] == "cloud.example.com"
    assert nextcloud["dns"]["name"] == "cloud"
    assert nextcloud["ports"]["internal"] == 8084
    assert nextcloud["urls"]["public"] == "https://cloud.example.com"
    assert nextcloud["urls"]["internal"] == "http://10.10.10.20:8084"
    assert nextcloud["edge"]["exact_redirects"] == [
        {"path": "/.well-known/carddav", "location": "/remote.php/dav/", "status": 301},
        {"path": "/.well-known/caldav", "location": "/remote.php/dav/", "status": 301},
    ]


def test_build_platform_vars_projects_control_and_dedicated_pool_metadata() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()

    keycloak = platform_vars["platform_service_topology"]["keycloak"]
    grafana = platform_vars["platform_service_topology"]["grafana"]

    assert keycloak["owning_vm"] == "runtime-control"
    assert keycloak["private_ip"] == "10.10.10.92"
    assert keycloak["edge"]["upstream"] == "http://10.10.10.92:8091"
    assert keycloak["runtime_pool"] == "runtime-control"
    assert keycloak["restart_domain"] == "runtime-control-identity"
    assert keycloak["mobility_tier"] == "anchor"
    assert grafana["runtime_pool"] == "dedicated-monitoring"
    assert grafana["mobility_tier"] == "anchor"


def test_build_platform_vars_includes_shared_session_authority_contract() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    authority = platform_vars["platform_session_authority"]

    assert authority["authority_hostname"] == "ops.example.com"
    assert authority["ops_portal_client_id"] == "ops-portal-oauth"
    assert authority["keycloak_logout_url"] == "https://sso.example.com/realms/lv3/protocol/openid-connect/logout"
    assert authority["oauth2_proxy_sign_out_url"] == "https://ops.example.com/oauth2/sign_out"
    assert authority["shared_logout_path"] == "/.well-known/lv3/session/logout"
    assert authority["shared_proxy_cleanup_path"] == "/.well-known/lv3/session/proxy-logout"
    assert authority["shared_logged_out_path"] == "/.well-known/lv3/session/logged-out"
    assert authority["shared_logged_out_url"] == "https://ops.example.com/.well-known/lv3/session/logged-out"


def test_build_service_urls_supports_private_gitea_proxy_and_root_url() -> None:
    ports = {
        "gitea_http_port": 3003,
        "gitea_host_proxy_port": 3009,
    }
    service = {
        "owning_vm": "docker-runtime",
        "public_hostname": "git.example.com",
    }
    port_map, urls = generate_platform_vars.build_service_urls(
        "gitea",
        service,
        {"management_tailscale_ipv4": "100.64.0.1"},
        {"docker-runtime": "10.10.10.20"},
        ports,
        {"desired_state": {"host_id": "proxmox-host"}},
    )

    assert port_map == {"internal": 3003, "controller": 3009}
    assert urls == {
        "public": "http://git.example.com:3009",
        "internal": "http://10.10.10.20:3003",
        "controller": "http://100.64.0.1:3009",
    }


def test_build_service_urls_supports_private_nomad_controller_url() -> None:
    ports = {
        "nomad_server_port": 4646,
        "nomad_host_proxy_port": 8013,
    }
    service = {
        "owning_vm": "monitoring",
    }
    host_vars = {"management_tailscale_ipv4": "100.64.0.1"}
    guest_ipv4_by_name = {"monitoring": "10.10.10.40"}
    stack = {"desired_state": {"host_id": "proxmox-host"}}

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
    service = {"owning_vm": "runtime-general"}
    host_vars = {"management_tailscale_ipv4": "100.118.189.95"}
    guest_ipv4_by_name = {"runtime-general": "10.10.10.91"}
    stack = {"desired_state": {"host_id": "proxmox-host"}}

    port_map, urls = generate_platform_vars.build_service_urls(
        "homepage",
        service,
        host_vars,
        guest_ipv4_by_name,
        ports,
        stack,
    )

    assert port_map == {"internal": 3090}
    assert urls == {"internal": "http://10.10.10.91:3090"}


def test_build_platform_vars_moves_support_surfaces_to_runtime_general() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    homepage = platform_vars["platform_service_topology"]["homepage"]
    mailpit = platform_vars["platform_service_topology"]["mailpit"]
    status_page = platform_vars["platform_service_topology"]["status_page"]
    uptime_kuma = platform_vars["platform_service_topology"]["uptime_kuma"]

    assert homepage["owning_vm"] == "runtime-general"
    assert homepage["urls"]["internal"] == "http://10.10.10.91:3090"
    assert homepage["edge"]["upstream"] == "http://10.10.10.91:9080"
    assert homepage["edge"]["root_proxy_path"] == "/homepage"
    assert mailpit["owning_vm"] == "runtime-general"
    assert mailpit["urls"]["internal"] == "http://10.10.10.91:8025"
    assert status_page["owning_vm"] == "runtime-general"
    assert status_page["edge"]["upstream"] == "http://10.10.10.91:3001"
    assert uptime_kuma["owning_vm"] == "runtime-general"
    assert uptime_kuma["urls"]["internal"] == "http://10.10.10.91:3001"


def test_build_service_urls_resolves_excalidraw_internal_url() -> None:
    ports = {"excalidraw_port": 3095}
    service = {"owning_vm": "docker-runtime", "public_hostname": "draw.example.com"}
    host_vars = {"management_tailscale_ipv4": "100.118.189.95"}
    guest_ipv4_by_name = {"docker-runtime": "10.10.10.20"}
    stack = {"desired_state": {"host_id": "proxmox-host"}}

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
        "public": "https://draw.example.com",
        "internal": "http://10.10.10.20:3095",
    }


def test_build_service_urls_resolves_outline_internal_url() -> None:
    ports = {"outline_port": 3006}
    service = {"owning_vm": "docker-runtime", "public_hostname": "wiki.example.com"}
    host_vars = {"management_tailscale_ipv4": "100.118.189.95"}
    guest_ipv4_by_name = {"docker-runtime": "10.10.10.20"}
    stack = {"desired_state": {"host_id": "proxmox-host"}}

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
        "public": "https://wiki.example.com",
        "internal": "http://10.10.10.20:3006",
    }


def test_build_service_urls_resolves_superset_internal_url() -> None:
    ports = {"superset_port": 8105}
    service = {"owning_vm": "docker-runtime", "public_hostname": "bi.example.com"}
    host_vars = {"management_tailscale_ipv4": "100.118.189.95"}
    guest_ipv4_by_name = {"docker-runtime": "10.10.10.20"}
    stack = {"desired_state": {"host_id": "proxmox-host"}}

    port_map, urls = generate_platform_vars.build_service_urls(
        "superset",
        service,
        host_vars,
        guest_ipv4_by_name,
        ports,
        stack,
    )

    assert port_map == {"internal": 8105}
    assert urls == {
        "public": "https://bi.example.com",
        "internal": "http://10.10.10.20:8105",
    }


def test_build_service_urls_resolves_paperless_internal_url() -> None:
    ports = {"paperless_port": 8018}
    service = {"owning_vm": "docker-runtime", "public_hostname": "paperless.example.com"}
    host_vars = {"management_tailscale_ipv4": "100.118.189.95"}
    guest_ipv4_by_name = {"docker-runtime": "10.10.10.20"}
    stack = {"desired_state": {"host_id": "proxmox-host"}}

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
        "public": "https://paperless.example.com",
        "internal": "http://10.10.10.20:8018",
    }


def test_build_service_urls_resolves_piper_internal_url() -> None:
    ports = {"piper_port": 8100}
    service = {"owning_vm": "docker-runtime"}
    host_vars = {"management_tailscale_ipv4": "100.118.189.95"}
    guest_ipv4_by_name = {"docker-runtime": "10.10.10.20"}
    stack = {"desired_state": {"host_id": "proxmox-host"}}

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
    host_vars = yaml.safe_load((REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml").read_text(encoding="utf-8"))
    allowed_inbound = host_vars["network_policy"]["guests"]["runtime-ai"]["allowed_inbound"]

    assert any(rule["source"] == "host" and 9998 in rule["ports"] for rule in allowed_inbound)


def test_build_platform_vars_includes_plane_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    plane = platform_vars["platform_service_topology"]["plane"]

    assert plane["public_hostname"] == "tasks.example.com"
    assert plane["dns"]["name"] == "tasks"
    assert plane["ports"]["internal"] == 8093
    assert plane["ports"]["controller"] == 8011
    assert plane["urls"]["public"] == "https://tasks.example.com"
    assert plane["urls"]["controller"] == "http://100.64.0.1:8011"


def test_build_platform_vars_includes_woodpecker_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    woodpecker = platform_vars["platform_service_topology"]["woodpecker"]

    assert woodpecker["public_hostname"] == "ci.example.com"
    assert woodpecker["dns"]["name"] == "ci"
    assert woodpecker["ports"]["internal"] == 8102
    assert woodpecker["ports"]["controller"] == 8017
    assert woodpecker["urls"]["public"] == "https://ci.example.com"
    assert woodpecker["urls"]["controller"] == "http://100.64.0.1:8017"


def test_woodpecker_network_policy_allows_host_and_edge_access() -> None:
    host_vars = yaml.safe_load((REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml").read_text(encoding="utf-8"))
    allowed_inbound = host_vars["network_policy"]["guests"]["docker-runtime"]["allowed_inbound"]

    assert any(rule["source"] == "host" and 8102 in rule["ports"] for rule in allowed_inbound)
    assert any(rule["source"] == "nginx-edge" and 8102 in rule["ports"] for rule in allowed_inbound)


def test_build_platform_vars_uses_loopback_for_guest_local_platform_context_verification() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()

    assert platform_vars["platform_context_private_url"] == "http://127.0.0.1:8010"


def test_build_platform_vars_includes_matrix_synapse_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    matrix_synapse = platform_vars["platform_service_topology"]["matrix_synapse"]

    assert matrix_synapse["public_hostname"] == "matrix.example.com"
    assert matrix_synapse["dns"]["name"] == "matrix"
    assert matrix_synapse["ports"]["internal"] == 8008
    assert matrix_synapse["ports"]["controller"] == 8015
    assert matrix_synapse["urls"]["public"] == "https://matrix.example.com"
    assert matrix_synapse["urls"]["controller"] == "http://100.64.0.1:8015"


def test_build_service_urls_include_coolify_controller_and_apps_endpoints() -> None:
    ports = {
        "coolify_dashboard_port": 8000,
        "coolify_proxy_port": 80,
        "coolify_proxy_tls_port": 443,
        "coolify_host_proxy_port": 8012,
    }
    host_vars = {"management_tailscale_ipv4": "100.64.0.1"}
    guest_ipv4_by_name = {"coolify": "10.10.10.70"}
    stack = {"desired_state": {"host_id": "proxmox-host"}}

    controller_port_map, controller_urls = generate_platform_vars.build_service_urls(
        "coolify",
        {"owning_vm": "coolify", "public_hostname": "coolify.example.com"},
        host_vars,
        guest_ipv4_by_name,
        ports,
        stack,
    )
    app_port_map, app_urls = generate_platform_vars.build_service_urls(
        "coolify_apps",
        {"owning_vm": "coolify", "public_hostname": "apps.example.com"},
        host_vars,
        guest_ipv4_by_name,
        ports,
        stack,
    )
    assert controller_port_map == {"internal": 8000, "controller": 8012}
    assert controller_urls == {
        "public": "https://coolify.example.com",
        "internal": "http://10.10.10.70:8000",
        "controller": "http://100.64.0.1:8012",
    }
    assert app_port_map == {"internal": 443}
    assert app_urls == {
        "public": "https://apps.example.com",
        "internal": "https://10.10.10.70:443",
    }


def test_build_platform_vars_includes_coolify_wildcard_dns_record() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()

    wildcard_record = next(record for record in platform_vars["hetzner_dns_records"] if record["name"] == "*.apps")

    assert wildcard_record == {
        "name": "*.apps",
        "type": "A",
        "value": "203.0.113.1",
        "ttl": 60,
    }


def test_build_platform_vars_includes_glitchtip_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    glitchtip = platform_vars["platform_service_topology"]["glitchtip"]

    assert glitchtip["public_hostname"] == "errors.example.com"
    assert glitchtip["dns"]["name"] == "errors"
    assert glitchtip["ports"]["internal"] == 3005
    assert glitchtip["urls"]["public"] == "https://errors.example.com"
    assert glitchtip["urls"]["internal"] == "http://10.10.10.20:3005"
    assert glitchtip["edge"]["upstream"] == glitchtip["urls"]["internal"]
    assert platform_vars["glitchtip_port"] == 3005
