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
