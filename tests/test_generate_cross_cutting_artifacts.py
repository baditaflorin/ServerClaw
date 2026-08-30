import pytest
from pathlib import Path

import generate_cross_cutting_artifacts


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def disable_shared_identity_overlay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LV3_DISABLE_SHARED_LOCAL_IDENTITY", "1")


def test_load_guest_catalog_falls_back_to_topology_host_vars(tmp_path: Path) -> None:
    host_vars_path = tmp_path / "inventory" / "host_vars" / "proxmox-host.yml"
    host_vars_path.parent.mkdir(parents=True)
    host_vars_path.write_text(
        """\
proxmox_guests:
  - name: nginx
    ipv4: 10.10.10.10
  - name: coolify
    ipv4: 10.10.10.70
"""
    )

    catalog = generate_cross_cutting_artifacts._load_guest_catalog(tmp_path)

    assert catalog["nginx"]["ipv4"] == "10.10.10.10"
    assert catalog["coolify"]["ipv4"] == "10.10.10.70"


def test_explicit_topology_file_overrides_existing_platform_catalog(tmp_path: Path) -> None:
    platform_path = tmp_path / "inventory" / "group_vars" / "platform.yml"
    platform_path.parent.mkdir(parents=True)
    platform_path.write_text("platform_guest_catalog:\n  by_name:\n    nginx:\n      ipv4: 10.1.0.10\n")
    topology_path = tmp_path / "selected-topology.yml"
    topology_path.write_text("proxmox_guests:\n  - name: nginx\n    ipv4: 10.2.0.10\n")

    catalog = generate_cross_cutting_artifacts._load_guest_catalog(
        tmp_path,
        topology_path=topology_path,
    )

    assert catalog == {"nginx": {"ipv4": "10.2.0.10"}}


def test_generate_nginx_upstreams_uses_catalog_for_librechat_surface() -> None:
    registry = generate_cross_cutting_artifacts._load_registry()
    guest_catalog = generate_cross_cutting_artifacts._load_guest_catalog(REPO_ROOT)

    upstreams = generate_cross_cutting_artifacts.generate_nginx_upstreams(
        registry,
        write=False,
        repo_root=REPO_ROOT,
    )

    librechat = next(entry for entry in upstreams if entry["service_name"] == "librechat")
    assert librechat["fqdn"] == "chat.example.com"
    assert librechat["host"] == "coolify"
    assert librechat["ip"] == guest_catalog["coolify"]["ipv4"]
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


def test_explicit_identity_file_drives_registry_interpolation(tmp_path: Path) -> None:
    identity_file = tmp_path / "identity.yml"
    identity_file.write_text("platform_domain: selected.example.net\n")

    identity_vars = generate_cross_cutting_artifacts._load_identity_file(identity_file)
    registry = generate_cross_cutting_artifacts._load_registry(identity_vars)

    assert registry["authentik"]["dns"]["records"][0]["fqdn"] == "id.selected.example.net"
    assert registry["glitchtip"]["hairpin"]["publish"][1]["hostname"] == "id.selected.example.net"
    assert registry["outline"]["sso"]["redirect_uris"] == ["https://wiki.selected.example.net/auth/oidc.callback"]


def test_main_passes_explicit_identity_to_registry_and_hairpin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity_file = tmp_path / "identity.yml"
    identity_file.write_text("platform_domain: selected.example.net\n")
    captured: dict[str, object] = {}

    def fake_load_registry(identity_vars: dict[str, str] | None = None) -> dict:
        captured["registry_identity"] = identity_vars
        return {}

    def fake_generate_hairpin(
        registry: dict,
        write: bool = False,
        repo_root: Path = REPO_ROOT,
        identity_vars: dict[str, str] | None = None,
        topology_path: Path | None = None,
    ) -> list[dict]:
        captured["hairpin_identity"] = identity_vars
        captured["write"] = write
        captured["topology_path"] = topology_path
        return []

    monkeypatch.setattr(generate_cross_cutting_artifacts, "_load_registry", fake_load_registry)
    monkeypatch.setattr(generate_cross_cutting_artifacts, "generate_hairpin", fake_generate_hairpin)

    result = generate_cross_cutting_artifacts.main(
        ["--write", "--only", "hairpin", "--identity-file", str(identity_file)]
    )

    expected = {"platform_domain": "selected.example.net"}
    assert result == 0
    assert captured == {
        "registry_identity": expected,
        "hairpin_identity": expected,
        "write": True,
        "topology_path": None,
    }


def test_main_passes_explicit_topology_to_hairpin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity_file = tmp_path / "identity.yml"
    identity_file.write_text("platform_domain: selected.example.net\n")
    topology_file = tmp_path / "topology.yml"
    topology_file.write_text("proxmox_guests: []\n")
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        generate_cross_cutting_artifacts,
        "_load_registry",
        lambda identity_vars=None: {},
    )

    def fake_generate_hairpin(registry, **kwargs) -> list[dict]:
        captured["registry"] = registry
        captured.update(kwargs)
        return []

    monkeypatch.setattr(generate_cross_cutting_artifacts, "generate_hairpin", fake_generate_hairpin)

    result = generate_cross_cutting_artifacts.main(
        [
            "--write",
            "--only",
            "hairpin",
            "--identity-file",
            str(identity_file),
            "--topology-file",
            str(topology_file),
        ]
    )

    assert result == 0
    assert captured["topology_path"] == topology_file


def test_check_prefers_tracked_identity_snapshot_over_shared_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    platform_path = tmp_path / "platform.yml"
    platform_path.write_text("platform_generation:\n  identity_overlay:\n    platform_domain: tracked.example.net\n")
    monkeypatch.setattr(generate_cross_cutting_artifacts, "PLATFORM_YML_PATH", platform_path)
    monkeypatch.delenv("LV3_DISABLE_SHARED_LOCAL_IDENTITY", raising=False)
    monkeypatch.setattr(
        generate_cross_cutting_artifacts,
        "load_identity_vars",
        lambda: {"platform_domain": "shared.example.net"},
    )

    identity = generate_cross_cutting_artifacts._resolve_generation_identity(
        None,
        prefer_tracked_snapshot=True,
    )

    assert identity == {"platform_domain": "tracked.example.net"}


def test_generate_sso_clients_accepts_authentik_provider() -> None:
    registry = {
        "example": {
            "sso": {
                "enabled": True,
                "provider": "authentik",
                "client_id": "example",
                "redirect_uris": ["https://example.example.com/auth/callback"],
                "scopes": ["openid", "profile", "email"],
                "public_client": False,
            }
        }
    }

    clients = generate_cross_cutting_artifacts.generate_sso_clients(registry)

    assert clients["example"] == {
        "service": "example",
        "provider": "authentik",
        "redirect_uris": ["https://example.example.com/auth/callback"],
        "scopes": ["openid", "profile", "email"],
        "public_client": False,
    }


def test_authentik_registry_declares_canonical_edge_surface() -> None:
    registry = generate_cross_cutting_artifacts._load_registry()

    authentik = registry["authentik"]
    assert authentik["internal_port"] == 9010
    assert authentik["dns"]["records"] == [
        {
            "fqdn": "id.example.com",
            "type": "public",
            "target_host": "nginx",
            "ttl": 60,
        }
    ]
    assert authentik["tls"] == {
        "domains": ["id.example.com"],
        "cert_source": "letsencrypt",
        "wildcard": False,
        "cert_validity_days": 90,
    }
    assert authentik["proxy"] == {
        "enabled": True,
        "upstream_port": 9010,
        "upstream_host": "runtime-control",
        "public_fqdn": "id.example.com",
        "auth_proxy": False,
    }


def test_cross_cutting_generators_include_authentik_edge_surface() -> None:
    registry = generate_cross_cutting_artifacts._load_registry()
    guest_catalog = generate_cross_cutting_artifacts._load_guest_catalog(REPO_ROOT)

    dns_records = generate_cross_cutting_artifacts.generate_dns_declarations(registry)
    certificates = generate_cross_cutting_artifacts.generate_tls_certificates(registry)
    upstreams = generate_cross_cutting_artifacts.generate_nginx_upstreams(
        registry,
        repo_root=REPO_ROOT,
    )
    authentik_upstream = next(entry for entry in upstreams if entry["service_name"] == "authentik")

    assert dns_records["id.example.com"] == {
        "service": "authentik",
        "type": "public",
        "target_host": "nginx",
        "ttl": 60,
    }
    assert certificates["id.example.com"] == {
        "service": "authentik",
        "source": "letsencrypt",
        "wildcard": False,
        "cert_validity_days": 90,
    }
    assert authentik_upstream == {
        "name": "authentik_upstream",
        "service_name": "authentik",
        "fqdn": "id.example.com",
        "extra_fqdns": [],
        "port": 9010,
        "host": "runtime-control",
        "ip": guest_catalog["runtime-control"]["ipv4"],
        "auth_proxy": False,
        "websocket": False,
        "max_body_size": "10m",
        "path_prefix": "/",
    }


def test_glitchtip_and_outline_select_authentik_with_per_client_rollback() -> None:
    registry = generate_cross_cutting_artifacts._load_registry()

    glitchtip_hairpins = registry["glitchtip"]["hairpin"]["publish"]
    assert glitchtip_hairpins == [
        {"hostname": "errors.example.com", "address_host": "nginx"},
        {"hostname": "id.example.com", "address_host": "nginx"},
    ]
    assert registry["glitchtip"]["sso"] == {
        "enabled": True,
        "provider": "authentik",
        "client_id": "glitchtip",
        "client_secret_local_file": ".local/authentik/glitchtip-client-secret.txt",
        "redirect_uris": ["https://errors.example.com/accounts/oidc/authentik/login/callback/"],
        "scopes": ["openid", "profile", "email"],
        "public_client": False,
    }
    assert registry["outline"]["sso"] == {
        "enabled": True,
        "provider": "authentik",
        "client_id": "outline",
        "client_secret_local_file": ".local/authentik/outline-client-secret.txt",
        "redirect_uris": ["https://wiki.example.com/auth/oidc.callback"],
        "scopes": ["openid", "profile", "email"],
        "public_client": False,
    }
    assert {entry["hostname"] for entry in registry["outline"]["hairpin"]["publish"]} == {
        "wiki.example.com",
        "id.example.com",
        "sso.example.com",
    }
