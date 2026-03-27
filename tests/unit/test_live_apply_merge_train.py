from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

from platform.live_apply.merge_train import enqueue_workstreams, execute_merge_train, plan_merge_train


def run(command: list[str], *, cwd: Path) -> str:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=True)
    return completed.stdout.strip()


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def python_step(step_id: str, code: str) -> dict[str, object]:
    return {"id": step_id, "argv": [sys.executable, "-c", code]}


def seed_repo(tmp_path: Path) -> None:
    run(["git", "init", "-b", "main"], cwd=tmp_path)
    run(["git", "config", "user.name", "Codex Test"], cwd=tmp_path)
    run(["git", "config", "user.email", "codex@example.com"], cwd=tmp_path)
    write(tmp_path / "VERSION", "0.1.0\n")
    write(tmp_path / "runtime-state.txt", "stable\n")
    write(tmp_path / "docs" / "adr" / "0001-placeholder.md", "# ADR 0001\n")
    write(tmp_path / "docs" / "runbooks" / "placeholder.md", "# Placeholder\n")
    write(tmp_path / "workstreams.yaml", "schema_version: 1.0.0\nworkstreams: []\n")
    run(["git", "add", "."], cwd=tmp_path)
    run(["git", "commit", "-m", "initial"], cwd=tmp_path)


def create_branch_commit(repo_root: Path, branch: str, relative_path: str, content: str) -> None:
    run(["git", "checkout", "-b", branch], cwd=repo_root)
    write(repo_root / relative_path, content)
    run(["git", "add", relative_path], cwd=repo_root)
    run(["git", "commit", "-m", f"add {relative_path}"], cwd=repo_root)
    run(["git", "checkout", "main"], cwd=repo_root)


def write_workstreams(repo_root: Path, payload: dict[str, object]) -> None:
    write(repo_root / "workstreams.yaml", yaml.safe_dump(payload, sort_keys=False))
    run(["git", "add", "."], cwd=repo_root)
    run(["git", "commit", "-m", "define workstreams"], cwd=repo_root)


def test_plan_serializes_shared_surfaces_and_keeps_disjoint_workstreams_parallel(tmp_path: Path) -> None:
    seed_repo(tmp_path)
    create_branch_commit(tmp_path, "codex/adr-a", "feature-a.txt", "A\n")
    create_branch_commit(tmp_path, "codex/adr-b", "feature-b.txt", "B\n")
    create_branch_commit(tmp_path, "codex/adr-c", "feature-c.txt", "C\n")
    write(tmp_path / "docs" / "adr" / "0182-a.md", "# ADR A\n")
    write(tmp_path / "docs" / "adr" / "0182-b.md", "# ADR B\n")
    write(tmp_path / "docs" / "adr" / "0182-c.md", "# ADR C\n")
    write(tmp_path / "docs" / "runbooks" / "live-train.md", "# Live Train\n")
    write_workstreams(
        tmp_path,
        {
            "schema_version": "1.0.0",
            "workstreams": [
                {
                    "id": "adr-a",
                    "branch": "codex/adr-a",
                    "doc": "docs/adr/0182-a.md",
                    "shared_surfaces": ["surface:shared"],
                    "depends_on": [],
                    "ready_to_merge": True,
                    "live_apply": {
                        "docs": {"adrs": ["docs/adr/0182-a.md"], "runbooks": ["docs/runbooks/live-train.md"]},
                        "ownership": {
                            "surfaces": [{"id": "surface:shared", "mode": "exclusive", "paths": ["feature-a.txt"]}]
                        },
                        "validation_checks": [python_step("check-a", "print('a')")],
                        "apply_plan": {"waves": [{"wave_id": "deploy", "steps": [python_step("apply-a", "print('a')")]}]},
                        "rollback_bundle": {
                            "strategy": "git_revert_only",
                            "steps": [python_step("rollback-a", "print('rollback-a')") | {"kind": "shell"}],
                        },
                    },
                },
                {
                    "id": "adr-b",
                    "branch": "codex/adr-b",
                    "doc": "docs/adr/0182-b.md",
                    "shared_surfaces": ["surface:shared"],
                    "depends_on": [],
                    "ready_to_merge": True,
                    "live_apply": {
                        "docs": {"adrs": ["docs/adr/0182-b.md"], "runbooks": ["docs/runbooks/live-train.md"]},
                        "ownership": {
                            "surfaces": [{"id": "surface:shared", "mode": "exclusive", "paths": ["feature-b.txt"]}]
                        },
                        "validation_checks": [python_step("check-b", "print('b')")],
                        "apply_plan": {"waves": [{"wave_id": "deploy", "steps": [python_step("apply-b", "print('b')")]}]},
                        "rollback_bundle": {
                            "strategy": "git_revert_only",
                            "steps": [python_step("rollback-b", "print('rollback-b')") | {"kind": "shell"}],
                        },
                    },
                },
                {
                    "id": "adr-c",
                    "branch": "codex/adr-c",
                    "doc": "docs/adr/0182-c.md",
                    "shared_surfaces": ["surface:isolated"],
                    "depends_on": [],
                    "ready_to_merge": True,
                    "live_apply": {
                        "docs": {"adrs": ["docs/adr/0182-c.md"], "runbooks": ["docs/runbooks/live-train.md"]},
                        "ownership": {
                            "surfaces": [{"id": "surface:isolated", "mode": "exclusive", "paths": ["feature-c.txt"]}]
                        },
                        "validation_checks": [python_step("check-c", "print('c')")],
                        "apply_plan": {"waves": [{"wave_id": "deploy", "steps": [python_step("apply-c", "print('c')")]}]},
                        "rollback_bundle": {
                            "strategy": "git_revert_only",
                            "steps": [python_step("rollback-c", "print('rollback-c')") | {"kind": "shell"}],
                        },
                    },
                },
            ],
        },
    )

    enqueue_workstreams(["adr-a", "adr-b", "adr-c"], requested_by="operator:test", repo_root=tmp_path)
    plan = plan_merge_train(repo_root=tmp_path)

    assert plan["waves"] == [
        {"wave_id": "wave-01", "workstreams": ["adr-a", "adr-c"]},
        {"wave_id": "wave-02", "workstreams": ["adr-b"]},
    ]


def test_failed_apply_runs_rollback_bundle_and_reverts_merged_branches(tmp_path: Path, monkeypatch) -> None:
    seed_repo(tmp_path)
    create_branch_commit(tmp_path, "codex/adr-a", "feature-a.txt", "A\n")
    create_branch_commit(tmp_path, "codex/adr-b", "feature-b.txt", "B\n")
    write(tmp_path / "docs" / "adr" / "0182-a.md", "# ADR A\n")
    write(tmp_path / "docs" / "adr" / "0182-b.md", "# ADR B\n")
    write(tmp_path / "docs" / "runbooks" / "live-train.md", "# Live Train\n")
    bundle_dir = tmp_path.parent / "rollback-artifacts"
    monkeypatch.setenv("LV3_ROLLBACK_BUNDLE_DIR", str(bundle_dir))
    write_workstreams(
        tmp_path,
        {
            "schema_version": "1.0.0",
            "workstreams": [
                {
                    "id": "adr-a",
                    "branch": "codex/adr-a",
                    "doc": "docs/adr/0182-a.md",
                    "shared_surfaces": ["surface:a"],
                    "depends_on": [],
                    "ready_to_merge": True,
                    "live_apply": {
                        "docs": {"adrs": ["docs/adr/0182-a.md"], "runbooks": ["docs/runbooks/live-train.md"]},
                        "ownership": {
                            "surfaces": [{"id": "surface:a", "mode": "exclusive", "paths": ["feature-a.txt"]}]
                        },
                        "validation_checks": [python_step("check-a", "print('a')")],
                        "apply_plan": {
                            "waves": [
                                {
                                    "wave_id": "deploy",
                                    "steps": [
                                        python_step(
                                            "apply-a",
                                            "from pathlib import Path; Path('runtime-state.txt').write_text('applied-a\\n')",
                                        )
                                    ],
                                }
                            ]
                        },
                        "rollback_bundle": {
                            "strategy": "restore_rendered_config_and_rerun",
                            "steps": [{"id": "restore-a", "kind": "file_restore", "paths": ["runtime-state.txt"]}],
                        },
                    },
                },
                {
                    "id": "adr-b",
                    "branch": "codex/adr-b",
                    "doc": "docs/adr/0182-b.md",
                    "shared_surfaces": ["surface:b"],
                    "depends_on": [],
                    "ready_to_merge": True,
                    "live_apply": {
                        "docs": {"adrs": ["docs/adr/0182-b.md"], "runbooks": ["docs/runbooks/live-train.md"]},
                        "ownership": {
                            "surfaces": [{"id": "surface:b", "mode": "exclusive", "paths": ["feature-b.txt"]}]
                        },
                        "validation_checks": [python_step("check-b", "print('b')")],
                        "apply_plan": {
                            "waves": [
                                {
                                    "wave_id": "deploy",
                                    "steps": [
                                        python_step(
                                            "apply-b",
                                            "from pathlib import Path; Path('runtime-state.txt').write_text('broken\\n'); raise SystemExit(7)",
                                        )
                                    ],
                                }
                            ]
                        },
                        "rollback_bundle": {
                            "strategy": "restore_rendered_config_and_rerun",
                            "steps": [{"id": "restore-b", "kind": "file_restore", "paths": ["runtime-state.txt"]}],
                        },
                    },
                },
            ],
        },
    )

    enqueue_workstreams(["adr-a", "adr-b"], requested_by="operator:test", repo_root=tmp_path)
    result = execute_merge_train(repo_root=tmp_path, requested_by="operator:test")

    assert result["status"] == "failed"
    assert result["rollback"]["status"] == "rolled_back"
    assert (tmp_path / "runtime-state.txt").read_text(encoding="utf-8") == "stable\n"
    assert not (tmp_path / "feature-a.txt").exists()
    assert not (tmp_path / "feature-b.txt").exists()
    assert run(["git", "status", "--short"], cwd=tmp_path) == ""
    bundle_files = sorted(bundle_dir.glob("*.json"))
    assert bundle_files
    bundle = yaml.safe_load(bundle_files[0].read_text(encoding="utf-8"))
    assert bundle["status"] == "rolled_back"
    assert len(bundle["merge_commits"]) == 2
