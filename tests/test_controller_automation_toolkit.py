from __future__ import annotations

from pathlib import Path

import controller_automation_toolkit as toolkit
from platform import repo as repo_module


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
    original = repo_module._path_exists

    def fake_path_exists(path: Path) -> bool:
        if str(path) == inaccessible:
            return False
        return original(path)

    monkeypatch.setattr(repo_module, "_path_exists", fake_path_exists)

    resolved = toolkit.resolve_repo_local_path(inaccessible, repo_root=repo_root)

    assert resolved == mirrored_secret


def test_repo_path_handles_inaccessible_candidate(tmp_path: Path, monkeypatch) -> None:
    secret_path = tmp_path / ".local" / "keycloak" / "bootstrap-admin-password.txt"
    original_exists = Path.exists

    def fake_exists(path: Path) -> bool:
        if path == secret_path:
            raise PermissionError("permission denied")
        return original_exists(path)

    monkeypatch.setattr(repo_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(Path, "exists", fake_exists, raising=False)

    resolved = repo_module.repo_path(".local", "keycloak", "bootstrap-admin-password.txt")

    assert resolved == secret_path


def test_repo_path_prefers_shared_root_local_dir_from_worktree(tmp_path: Path, monkeypatch) -> None:
    worktree_root = tmp_path / ".worktrees" / "ws-0308-live-apply"
    shared_secret = tmp_path / ".local" / "keycloak" / "bootstrap-admin-password.txt"
    shared_secret.parent.mkdir(parents=True)
    shared_secret.write_text("secret", encoding="utf-8")
    worktree_root.mkdir(parents=True)

    monkeypatch.setattr(repo_module, "REPO_ROOT", worktree_root)

    resolved = repo_module.repo_path(".local", "keycloak", "bootstrap-admin-password.txt")

    assert resolved == shared_secret


def test_repo_path_routes_missing_dot_local_targets_to_shared_root_from_worktree(
    tmp_path: Path,
    monkeypatch,
) -> None:
    worktree_root = tmp_path / ".worktrees" / "ws-0333-live-apply"
    shared_local_root = tmp_path / ".local"
    worktree_root.mkdir(parents=True)
    shared_local_root.mkdir(parents=True)

    monkeypatch.setattr(repo_module, "REPO_ROOT", worktree_root)

    resolved = repo_module.repo_path(".local", "ssh", "bootstrap.id_ed25519")

    assert resolved == shared_local_root / "ssh" / "bootstrap.id_ed25519"
