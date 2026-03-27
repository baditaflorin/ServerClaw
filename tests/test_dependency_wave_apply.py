from __future__ import annotations

import subprocess
import time
from pathlib import Path

from repo_package_loader import load_repo_package


WAVES_MODULE = load_repo_package(
    "lv3_dependency_waves_test",
    Path(__file__).resolve().parents[1] / "platform" / "ansible",
)
LOCKING_MODULE = load_repo_package(
    "lv3_dependency_waves_locking_test",
    Path(__file__).resolve().parents[1] / "platform" / "locking",
)

DependencyWaveExecutor = WAVES_MODULE.DependencyWaveExecutor
PlaybookApplyMetadata = WAVES_MODULE.PlaybookApplyMetadata
PlaybookApplyCatalog = WAVES_MODULE.PlaybookApplyCatalog
load_dependency_wave_manifest = WAVES_MODULE.load_dependency_wave_manifest
ResourceLockRegistry = DependencyWaveExecutor.__init__.__globals__["ResourceLockRegistry"]
LockType = DependencyWaveExecutor.execute.__globals__["LockType"]


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_repo(tmp_path: Path, *, playbooks: list[str]) -> Path:
    make_targets = sorted({f"converge-{Path(playbook).stem}" for playbook in playbooks})
    write(
        tmp_path / "Makefile",
        "\n".join(f"{target}:\n\t@echo {target}" for target in make_targets) + "\n",
    )
    write(
        tmp_path / "config" / "service-capability-catalog.json",
        '{"services":[{"id":"alpha","name":"Alpha","vm":"vm-alpha"},{"id":"beta","name":"Beta","vm":"vm-beta"}]}\n',
    )
    for playbook in playbooks:
        write(tmp_path / playbook, "---\n- hosts: localhost\n  gather_facts: false\n  tasks: []\n")
    return tmp_path


def build_catalog(entries: list[PlaybookApplyMetadata]) -> PlaybookApplyCatalog:
    return PlaybookApplyCatalog(entries={item.normalized_path: item for item in entries})


def metadata(playbook: str, *, lane: str, surface: str | None = None) -> PlaybookApplyMetadata:
    stem = Path(playbook).stem
    return PlaybookApplyMetadata(
        path=playbook,
        make_target=f"converge-{stem}",
        make_vars=(),
        mutation_scope="lane",
        execution_lane=lane,
        target_hosts=(lane,),
        shared_surfaces=((surface,) if surface else ()),
        lock_resources=(f"lane:{lane}",),
    )


def runner_factory(
    *,
    returncodes: dict[str, int] | None = None,
    sleeps: dict[str, float] | None = None,
    calls: list[str] | None = None,
) -> callable:
    returncodes = returncodes or {}
    sleeps = sleeps or {}
    calls = calls if calls is not None else []

    def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        target = command[1]
        calls.append(target)
        time.sleep(sleeps.get(target, 0.0))
        code = returncodes.get(target, 0)
        stdout = f"{target} ok\n"
        stderr = "" if code == 0 else f"{target} failed\n"
        return subprocess.CompletedProcess(command, code, stdout=stdout, stderr=stderr)

    return runner


def test_executor_orders_complex_dependency_graph(tmp_path: Path) -> None:
    repo = build_repo(
        tmp_path,
        playbooks=[
            "playbooks/foundation.yml",
            "playbooks/branch-a.yml",
            "playbooks/branch-b.yml",
            "playbooks/join.yml",
        ],
    )
    manifest_path = repo / "graph.yaml"
    write(
        manifest_path,
        """
plan_id: complex-graph
waves:
  - wave_id: foundation
    parallel:
      - playbooks/foundation.yml
  - wave_id: branch-a
    depends_on: [foundation]
    parallel:
      - playbooks/branch-a.yml
  - wave_id: branch-b
    depends_on: [foundation]
    parallel:
      - playbooks/branch-b.yml
  - wave_id: join
    depends_on: [branch-a, branch-b]
    parallel:
      - playbooks/join.yml
""".strip()
        + "\n",
    )
    catalog = build_catalog(
        [
            metadata("playbooks/foundation.yml", lane="lane-foundation"),
            metadata("playbooks/branch-a.yml", lane="lane-a"),
            metadata("playbooks/branch-b.yml", lane="lane-b"),
            metadata("playbooks/join.yml", lane="lane-join"),
        ]
    )
    executor = DependencyWaveExecutor(repo_root=repo, catalog=catalog)

    result = executor.execute(load_dependency_wave_manifest(manifest_path), env="production", dry_run=True)

    assert result.status == "planned"
    assert [wave.wave_id for wave in result.waves] == ["foundation", "branch-a", "branch-b", "join"]
    assert all(wave.status == "planned" for wave in result.waves)


def test_executor_runs_wave_items_in_parallel(tmp_path: Path) -> None:
    repo = build_repo(tmp_path, playbooks=["playbooks/alpha.yml", "playbooks/beta.yml"])
    manifest_path = repo / "parallel.yaml"
    write(
        manifest_path,
        """
plan_id: parallel-wave
waves:
  - wave_id: wave-1
    parallel:
      - playbooks/alpha.yml
      - playbooks/beta.yml
""".strip()
        + "\n",
    )
    catalog = build_catalog(
        [
            metadata("playbooks/alpha.yml", lane="lane-alpha"),
            metadata("playbooks/beta.yml", lane="lane-beta"),
        ]
    )
    calls: list[str] = []
    executor = DependencyWaveExecutor(
        repo_root=repo,
        catalog=catalog,
        command_runner=runner_factory(
            sleeps={"converge-alpha": 0.25, "converge-beta": 0.25},
            calls=calls,
        ),
    )

    started = time.monotonic()
    result = executor.execute(load_dependency_wave_manifest(manifest_path), env="production")
    elapsed = time.monotonic() - started

    assert result.status == "completed"
    assert elapsed < 0.45
    assert sorted(calls) == ["converge-alpha", "converge-beta"]


def test_executor_stops_after_failed_wave_and_skips_dependents(tmp_path: Path) -> None:
    repo = build_repo(
        tmp_path,
        playbooks=["playbooks/foundation.yml", "playbooks/failing.yml", "playbooks/follow-up.yml"],
    )
    manifest_path = repo / "failure.yaml"
    write(
        manifest_path,
        """
plan_id: failure-graph
waves:
  - wave_id: foundation
    parallel:
      - playbooks/foundation.yml
  - wave_id: failing
    depends_on: [foundation]
    parallel:
      - playbooks/failing.yml
  - wave_id: follow-up
    depends_on: [failing]
    parallel:
      - playbooks/follow-up.yml
""".strip()
        + "\n",
    )
    catalog = build_catalog(
        [
            metadata("playbooks/foundation.yml", lane="lane-foundation"),
            metadata("playbooks/failing.yml", lane="lane-failing"),
            metadata("playbooks/follow-up.yml", lane="lane-follow-up"),
        ]
    )
    executor = DependencyWaveExecutor(
        repo_root=repo,
        catalog=catalog,
        command_runner=runner_factory(returncodes={"converge-failing": 1}),
    )

    result = executor.execute(load_dependency_wave_manifest(manifest_path), env="production")

    assert result.status == "failed"
    assert [wave.status for wave in result.waves] == ["completed", "failed", "skipped"]
    assert result.waves[2].results[0].status == "skipped"


def test_executor_allows_partial_safe_wave_to_continue(tmp_path: Path) -> None:
    repo = build_repo(
        tmp_path,
        playbooks=["playbooks/failing.yml", "playbooks/recoverable.yml", "playbooks/follow-up.yml"],
    )
    manifest_path = repo / "partial.yaml"
    write(
        manifest_path,
        """
plan_id: partial-safe
waves:
  - wave_id: control-plane
    partial_safe: true
    parallel:
      - playbooks/failing.yml
      - playbooks/recoverable.yml
  - wave_id: follow-up
    depends_on: [control-plane]
    parallel:
      - playbooks/follow-up.yml
""".strip()
        + "\n",
    )
    catalog = build_catalog(
        [
            metadata("playbooks/failing.yml", lane="lane-failing"),
            metadata("playbooks/recoverable.yml", lane="lane-recoverable"),
            metadata("playbooks/follow-up.yml", lane="lane-follow-up"),
        ]
    )
    executor = DependencyWaveExecutor(
        repo_root=repo,
        catalog=catalog,
        command_runner=runner_factory(returncodes={"converge-failing": 1}),
    )

    result = executor.execute(load_dependency_wave_manifest(manifest_path), env="production")

    assert result.status == "partial_failed"
    assert [wave.status for wave in result.waves] == ["partial_failed", "completed"]


def test_executor_rejects_same_lane_shard_conflicts(tmp_path: Path) -> None:
    repo = build_repo(tmp_path, playbooks=["playbooks/alpha.yml", "playbooks/beta.yml"])
    manifest_path = repo / "conflict.yaml"
    write(
        manifest_path,
        """
plan_id: shard-conflict
waves:
  - wave_id: wave-1
    parallel:
      - playbooks/alpha.yml
      - playbooks/beta.yml
""".strip()
        + "\n",
    )
    catalog = build_catalog(
        [
            metadata("playbooks/alpha.yml", lane="shared-lane"),
            metadata("playbooks/beta.yml", lane="shared-lane"),
        ]
    )
    executor = DependencyWaveExecutor(repo_root=repo, catalog=catalog)

    result = executor.execute(load_dependency_wave_manifest(manifest_path), env="production", dry_run=True)

    assert result.status == "failed"
    assert result.waves[0].status == "invalid"
    assert "wave shard conflict" in (result.waves[0].error or "")


def test_executor_blocks_when_wave_lock_check_fails(tmp_path: Path) -> None:
    repo = build_repo(tmp_path, playbooks=["playbooks/alpha.yml"])
    manifest_path = repo / "blocked.yaml"
    write(
        manifest_path,
        """
plan_id: blocked-wave
waves:
  - wave_id: wave-1
    parallel:
      - playbooks/alpha.yml
""".strip()
        + "\n",
    )
    catalog = build_catalog([metadata("playbooks/alpha.yml", lane="lane-alpha")])
    registry = ResourceLockRegistry(repo_root=repo, state_path=repo / ".local" / "locks.json")
    registry.acquire(
        resource_path="lane:lane-alpha",
        lock_type=LockType.EXCLUSIVE,
        holder="external-holder",
        ttl_seconds=300,
    )
    calls: list[str] = []
    executor = DependencyWaveExecutor(
        repo_root=repo,
        catalog=catalog,
        registry=registry,
        command_runner=runner_factory(calls=calls),
    )

    result = executor.execute(load_dependency_wave_manifest(manifest_path), env="production")

    assert result.status == "failed"
    assert result.waves[0].status == "blocked"
    assert calls == []
