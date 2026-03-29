from __future__ import annotations

from pathlib import Path

import controller_automation_toolkit as toolkit


def test_yaml_fallback_keeps_colon_scalars_in_lists(tmp_path: Path) -> None:
    payload_path = tmp_path / "operators.yaml"
    payload_path.write_text(
        """
operators:
  - tailscale:
      tags:
        - tag:platform-operator
        - https://example.com/path
""".strip()
        + "\n",
        encoding="utf-8",
    )

    payload = toolkit._load_yaml_without_pyyaml(payload_path)

    assert payload["operators"][0]["tailscale"]["tags"] == [
        "tag:platform-operator",
        "https://example.com/path",
    ]


def test_yaml_fallback_still_parses_inline_list_mappings(tmp_path: Path) -> None:
    payload_path = tmp_path / "items.yaml"
    payload_path.write_text(
        """
items:
  - id: sample
    enabled: true
""".strip()
        + "\n",
        encoding="utf-8",
    )

    payload = toolkit._load_yaml_without_pyyaml(payload_path)

    assert payload["items"] == [{"id": "sample", "enabled": True}]


def test_resolve_repo_local_path_maps_missing_controller_secret_into_repo_local(tmp_path: Path) -> None:
    repo_root = tmp_path / "runtime"
    mirrored_secret = repo_root / ".local" / "nats" / "jetstream-admin-password.txt"
    mirrored_secret.parent.mkdir(parents=True)
    mirrored_secret.write_text("secret", encoding="utf-8")

    resolved = toolkit.resolve_repo_local_path(
        "/tmp/nonexistent-controller-root/.local/nats/jetstream-admin-password.txt",
        repo_root=repo_root,
    )

    assert resolved == mirrored_secret


def test_resolve_repo_local_path_maps_inaccessible_controller_secret_into_repo_local(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "runtime"
    mirrored_secret = repo_root / ".local" / "windmill" / "superadmin-secret.txt"
    mirrored_secret.parent.mkdir(parents=True)
    mirrored_secret.write_text("secret", encoding="utf-8")
    inaccessible = "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt"
    original = toolkit._path_exists

    def fake_path_exists(path: Path) -> bool:
        if str(path) == inaccessible:
            return False
        return original(path)

    monkeypatch.setattr(toolkit, "_path_exists", fake_path_exists)

    resolved = toolkit.resolve_repo_local_path(inaccessible, repo_root=repo_root)

    assert resolved == mirrored_secret
