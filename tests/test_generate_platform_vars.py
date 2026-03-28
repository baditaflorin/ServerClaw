import generate_platform_vars


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


def test_build_platform_vars_includes_plane_publication_topology() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    plane = platform_vars["platform_service_topology"]["plane"]

    assert plane["public_hostname"] == "tasks.lv3.org"
    assert plane["dns"]["name"] == "tasks"
    assert plane["ports"]["internal"] == 8093
    assert plane["ports"]["controller"] == 8011
    assert plane["urls"]["public"] == "https://tasks.lv3.org"
    assert plane["urls"]["controller"] == "http://100.64.0.1:8011"

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
