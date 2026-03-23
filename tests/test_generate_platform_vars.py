import generate_platform_vars


def test_resolve_tcp_proxy_port_supports_platform_port_assignments_templates() -> None:
    ports = {"platform_context_host_proxy_port": 8010}
    resolved = generate_platform_vars.resolve_tcp_proxy_port(
        "{{ platform_port_assignments.platform_context_host_proxy_port }}",
        ports,
    )
    assert resolved == 8010
