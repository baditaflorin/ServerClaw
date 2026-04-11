from pathlib import Path

import yaml

from scripts.dify_smoke import candidate_repo_roots, maybe_langfuse_trace_config


def test_langfuse_trace_config_prefers_internal_service_url(tmp_path: Path) -> None:
    local_dir = tmp_path / ".local" / "langfuse"
    local_dir.mkdir(parents=True)
    (local_dir / "project-public-key.txt").write_text("public", encoding="utf-8")
    (local_dir / "project-secret-key.txt").write_text("secret", encoding="utf-8")

    platform_vars_path = tmp_path / "inventory" / "group_vars"
    platform_vars_path.mkdir(parents=True)
    (platform_vars_path / "platform.yml").write_text(
        yaml.safe_dump(
            {
                "platform_service_topology": {
                    "langfuse": {
                        "urls": {
                            "internal": "http://10.10.10.20:3002",
                            "public": "https://langfuse.example.com",
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    assert maybe_langfuse_trace_config(tmp_path) == {
        "public_key": "public",
        "secret_key": "secret",
        "host": "http://10.10.10.20:3002",
    }


def test_candidate_repo_roots_includes_common_root_for_linked_worktree(tmp_path: Path) -> None:
    common_root = tmp_path / "repo"
    worktree_root = common_root / ".worktrees" / "ws-0197"
    worktree_root.mkdir(parents=True)
    gitdir = common_root / ".git" / "worktrees" / "ws-0197"
    gitdir.mkdir(parents=True)
    (worktree_root / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")

    assert candidate_repo_roots(worktree_root) == [worktree_root, common_root]


def test_langfuse_trace_config_falls_back_to_common_root_for_linked_worktree(tmp_path: Path) -> None:
    common_root = tmp_path / "repo"
    worktree_root = common_root / ".worktrees" / "ws-0197"
    worktree_root.mkdir(parents=True)
    gitdir = common_root / ".git" / "worktrees" / "ws-0197"
    gitdir.mkdir(parents=True)
    (worktree_root / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")

    local_dir = common_root / ".local" / "langfuse"
    local_dir.mkdir(parents=True)
    (local_dir / "project-public-key.txt").write_text("public", encoding="utf-8")
    (local_dir / "project-secret-key.txt").write_text("secret", encoding="utf-8")

    platform_vars_path = common_root / "inventory" / "group_vars"
    platform_vars_path.mkdir(parents=True)
    (platform_vars_path / "platform.yml").write_text(
        yaml.safe_dump(
            {
                "platform_service_topology": {
                    "langfuse": {
                        "urls": {
                            "internal": "http://10.10.10.20:3002",
                            "public": "https://langfuse.example.com",
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    assert maybe_langfuse_trace_config(worktree_root) == {
        "public_key": "public",
        "secret_key": "secret",
        "host": "http://10.10.10.20:3002",
    }
