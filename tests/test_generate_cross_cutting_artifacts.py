from pathlib import Path

import generate_cross_cutting_artifacts


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_load_guest_catalog_falls_back_to_topology_host_vars() -> None:
    catalog = generate_cross_cutting_artifacts._load_guest_catalog(REPO_ROOT)

    assert catalog["nginx"]["ipv4"] == "10.10.10.10"
    assert catalog["coolify"]["ipv4"] == "10.10.10.70"


def test_generate_nginx_upstreams_matches_live_librechat_surface() -> None:
    registry = generate_cross_cutting_artifacts._load_registry()

    upstreams = generate_cross_cutting_artifacts.generate_nginx_upstreams(
        registry,
        write=False,
        repo_root=REPO_ROOT,
    )

    librechat = next(entry for entry in upstreams if entry["service_name"] == "librechat")
    assert librechat["fqdn"] == "chat.example.com"
    assert librechat["host"] == "coolify"
    assert librechat["ip"] == "10.10.10.70"
    assert librechat["port"] == 8096


def test_generate_sso_clients_tracks_librechat_serverclaw_client() -> None:
    registry = generate_cross_cutting_artifacts._load_registry()

    clients = generate_cross_cutting_artifacts.generate_sso_clients(
        registry,
        write=False,
        repo_root=REPO_ROOT,
    )

    assert clients["serverclaw"]["service"] == "librechat"
    assert clients["serverclaw"]["redirect_uris"] == ["https://chat.example.com/oauth/openid/callback"]
