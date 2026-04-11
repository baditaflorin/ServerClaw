from __future__ import annotations

import json
from pathlib import Path

import yaml

from platform.agent import coordination
from platform.maintenance import windows


REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_INVENTORY_ROOT = REPO_ROOT / "inventory" / "examples" / "reference-platform"
REFERENCE_CONFIG_ROOT = REPO_ROOT / "config" / "examples"

LIVE_MARKERS = (
    "example.com",
    "203.0.113.1",
    "10.10.10.",
    "proxmox-host",
    "/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server",
)


def test_reference_inventory_examples_parse() -> None:
    hosts = yaml.safe_load((REFERENCE_INVENTORY_ROOT / "hosts.yml").read_text(encoding="utf-8"))
    platform_vars = yaml.safe_load(
        (REFERENCE_INVENTORY_ROOT / "group_vars" / "platform.yml").read_text(encoding="utf-8")
    )
    host_vars = yaml.safe_load(
        (REFERENCE_INVENTORY_ROOT / "host_vars" / "proxmox_reference.yml").read_text(encoding="utf-8")
    )

    proxmox_hosts = hosts["all"]["children"]["proxmox_hosts"]["hosts"]
    guests = hosts["all"]["children"]["lv3_guests"]["hosts"]

    assert "proxmox_reference" in proxmox_hosts
    assert {"nginx-edge-reference", "runtime-control-reference", "runtime-general-reference"} <= set(guests)
    assert platform_vars["reference_platform"]["publication_domain"] == "platform.example.com"
    assert host_vars["management_ipv4"] == "203.0.113.10"


def test_reference_config_examples_parse() -> None:
    provider_profile = yaml.safe_load(
        (REFERENCE_CONFIG_ROOT / "reference-provider-profile.yaml").read_text(encoding="utf-8")
    )
    publication_profile = json.loads(
        (REFERENCE_CONFIG_ROOT / "reference-publication-profile.json").read_text(encoding="utf-8")
    )
    secret_manifest = json.loads(
        (REFERENCE_CONFIG_ROOT / "reference-controller-local-secrets.json").read_text(encoding="utf-8")
    )

    assert provider_profile["profile"]["public_domain"] == "platform.example.com"
    assert publication_profile["profile_id"] == "public-github-proxmox"
    assert secret_manifest["secrets"]["bootstrap_ssh_private_key"]["path"].startswith(".local/")


def test_public_reference_samples_do_not_embed_live_values() -> None:
    sample_paths = [
        REFERENCE_INVENTORY_ROOT / "README.md",
        REFERENCE_INVENTORY_ROOT / "hosts.yml",
        REFERENCE_INVENTORY_ROOT / "group_vars" / "platform.yml",
        REFERENCE_INVENTORY_ROOT / "host_vars" / "proxmox_reference.yml",
        REFERENCE_CONFIG_ROOT / "reference-provider-profile.yaml",
        REFERENCE_CONFIG_ROOT / "reference-publication-profile.json",
        REFERENCE_CONFIG_ROOT / "reference-controller-local-secrets.json",
        REPO_ROOT / "docs" / "reference-deployments" / "README.md",
        REPO_ROOT / "docs" / "runbooks" / "fork-reference-platform.md",
    ]

    for path in sample_paths:
        text = path.read_text(encoding="utf-8")
        for marker in LIVE_MARKERS:
            assert marker not in text, f"{path} leaked live marker {marker!r}"


def test_controller_secret_manifest_uses_repo_local_paths() -> None:
    payload = json.loads((REPO_ROOT / "config" / "controller-local-secrets.json").read_text(encoding="utf-8"))
    file_paths = [
        secret["path"]
        for secret in payload["secrets"].values()
        if isinstance(secret, dict) and secret.get("kind") == "file"
    ]

    assert file_paths
    assert all(isinstance(path, str) and path.startswith(".local/") for path in file_paths)


def test_agent_coordination_resolves_repo_relative_nats_secret(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    secret_path = repo_root / ".local" / "nats" / "jetstream-admin-password.txt"
    secret_path.parent.mkdir(parents=True)
    secret_path.write_text("jetstream-secret\n", encoding="utf-8")
    manifest_path = repo_root / "config" / "controller-local-secrets.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "secrets": {
                    "nats_jetstream_admin_password": {
                        "kind": "file",
                        "path": ".local/nats/jetstream-admin-password.txt",
                    }
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert coordination._resolve_nats_credentials(repo_root) == {
        "user": "jetstream-admin",
        "password": "jetstream-secret",
    }


def test_maintenance_windows_resolves_repo_relative_nats_secret(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    secret_path = repo_root / ".local" / "nats" / "jetstream-admin-password.txt"
    secret_path.parent.mkdir(parents=True)
    secret_path.write_text("jetstream-secret\n", encoding="utf-8")

    credentials = windows.resolve_nats_credentials(
        {
            "repo_root": repo_root,
            "secret_manifest": {
                "secrets": {
                    "nats_jetstream_admin_password": {
                        "kind": "file",
                        "path": ".local/nats/jetstream-admin-password.txt",
                    }
                }
            },
        }
    )

    assert credentials == {"user": "jetstream-admin", "password": "jetstream-secret"}
