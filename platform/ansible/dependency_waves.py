from __future__ import annotations

import concurrent.futures
import json
import re
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from platform.datetime_compat import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import yaml

from platform.locking import LockType, ResourceLockRegistry, ResourceLocked


MAKE_TARGET_PATTERN = re.compile(r"^([A-Za-z0-9_-]+):")
VALID_MUTATION_SCOPES = {"host", "lane", "platform"}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: Any, path: str) -> tuple[str, ...]:
    items = _require_list(value, path)
    result: list[str] = []
    for index, item in enumerate(items):
        result.append(_require_str(item, f"{path}[{index}]"))
    return tuple(result)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_playbook_path(playbook_path: str | Path) -> str:
    candidate = Path(playbook_path)
    text = candidate.as_posix().lstrip("./")
    if not text.startswith("playbooks/"):
        raise ValueError(f"dependency-wave entries must point at playbooks/, got {playbook_path}")
    if not text.endswith(".yml"):
        raise ValueError(f"dependency-wave entries must point at a .yml playbook, got {playbook_path}")
    return text


def _parse_make_targets(repo_root: Path) -> set[str]:
    targets = set()
    makefile_path = repo_root / "Makefile"
    for line in makefile_path.read_text(encoding="utf-8").splitlines():
        match = MAKE_TARGET_PATTERN.match(line)
        if match and match.group(1) != ".PHONY":
            targets.add(match.group(1))
    return targets


def _load_service_map(repo_root: Path) -> dict[str, dict[str, Any]]:
    payload = _load_json(repo_root / "config" / "service-capability-catalog.json")
    services = _require_list(payload.get("services"), "config/service-capability-catalog.json.services")
    return {
        _require_str(service.get("id"), f"config/service-capability-catalog.json.services[{index}].id"): service
        for index, service in enumerate(services)
        if isinstance(service, dict)
    }


def _match_service_id(stem: str, service_map: dict[str, dict[str, Any]]) -> str | None:
    normalized = stem.replace("-", "_")
    for candidate in (stem, normalized):
        if candidate in service_map:
            return candidate
    for service_id in service_map:
        if service_id.replace("-", "_") == normalized:
            return service_id
    return None


@dataclass(frozen=True)
class PlaybookApplyMetadata:
    path: str
    make_target: str
    make_vars: tuple[tuple[str, str], ...]
    mutation_scope: str
    target_hosts: tuple[str, ...] = ()
    execution_lane: str | None = None
    shared_surfaces: tuple[str, ...] = ()
    lock_resources: tuple[str, ...] = ()
    workflow_id: str | None = None

    def __post_init__(self) -> None:
        if self.mutation_scope not in VALID_MUTATION_SCOPES:
            raise ValueError(f"unsupported mutation_scope '{self.mutation_scope}' for {self.path}")
        if self.mutation_scope == "host" and not self.target_hosts:
            raise ValueError(f"{self.path} must declare target_hosts for host-scoped execution")
        if self.mutation_scope == "lane" and not self.execution_lane:
            raise ValueError(f"{self.path} must declare execution_lane for lane-scoped execution")

    @property
    def normalized_path(self) -> str:
        return _normalize_playbook_path(self.path)

    def make_command(self, *, env: str, extra_args: str = "") -> list[str]:
        command = ["make", self.make_target]
        command.extend(f"{key}={value}" for key, value in self.make_vars)
        command.append(f"env={env}")
        if extra_args.strip():
            command.append(f"EXTRA_ARGS={extra_args.strip()}")
        return command

    def shard_keys(self) -> set[str]:
        if self.mutation_scope == "host":
            return {f"host:{item}" for item in self.target_hosts}
        if self.mutation_scope == "lane" and self.execution_lane:
            return {f"lane:{self.execution_lane}"}
        return {f"surface:{item}" for item in (self.shared_surfaces or (self.normalized_path,))}

    def effective_lock_resources(self) -> tuple[str, ...]:
        if self.lock_resources:
            return self.lock_resources
        if self.mutation_scope == "host":
            return tuple(f"host:{item}" for item in self.target_hosts)
        if self.mutation_scope == "lane" and self.execution_lane:
            return (f"lane:{self.execution_lane}",)
        return (f"playbook:{self.normalized_path}",)

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "path": self.normalized_path,
            "make_target": self.make_target,
            "make_vars": {key: value for key, value in self.make_vars},
            "mutation_scope": self.mutation_scope,
            "target_hosts": list(self.target_hosts),
            "shared_surfaces": list(self.shared_surfaces),
            "lock_resources": list(self.effective_lock_resources()),
        }
        if self.execution_lane:
            payload["execution_lane"] = self.execution_lane
        if self.workflow_id:
            payload["workflow_id"] = self.workflow_id
        return payload


@dataclass(frozen=True)
class PlaybookApplyCatalog:
    entries: dict[str, PlaybookApplyMetadata]

    def resolve(self, playbook_path: str, *, repo_root: Path) -> PlaybookApplyMetadata:
        normalized = _normalize_playbook_path(playbook_path)
        if not (repo_root / normalized).exists():
            raise ValueError(f"playbook does not exist: {normalized}")
        explicit = self.entries.get(normalized)
        if explicit is not None:
            return explicit

        stem = Path(normalized).stem
        service_map = _load_service_map(repo_root)
        service_id = _match_service_id(stem, service_map)
        if normalized.startswith("playbooks/services/") and service_id is not None:
            service = service_map[service_id]
            vm = _require_str(service.get("vm"), f"service '{service_id}'.vm")
            return PlaybookApplyMetadata(
                path=normalized,
                make_target="live-apply-service",
                make_vars=(("service", service_id),),
                mutation_scope="lane",
                execution_lane=vm,
                target_hosts=(vm,),
                shared_surfaces=(f"service:{service_id}",),
                lock_resources=(f"vm:{vm}/service:{service_id}",),
            )

        if normalized.startswith("playbooks/groups/"):
            return PlaybookApplyMetadata(
                path=normalized,
                make_target="live-apply-group",
                make_vars=(("group", stem),),
                mutation_scope="platform",
                shared_surfaces=(f"group:{stem}",),
                lock_resources=(f"group:{stem}",),
            )

        if normalized == "playbooks/site.yml":
            return PlaybookApplyMetadata(
                path=normalized,
                make_target="live-apply-site",
                make_vars=(),
                mutation_scope="platform",
                shared_surfaces=("site",),
                lock_resources=("site",),
            )

        make_targets = _parse_make_targets(repo_root)
        for candidate in (f"converge-{stem}", f"deploy-{stem}"):
            if candidate in make_targets:
                return PlaybookApplyMetadata(
                    path=normalized,
                    make_target=candidate,
                    make_vars=(),
                    mutation_scope="platform",
                    shared_surfaces=(f"playbook:{normalized}",),
                    lock_resources=(f"playbook:{normalized}",),
                )

        raise ValueError(
            f"no playbook apply metadata found for {normalized}; add it to config/dependency-wave-playbooks.yaml"
        )


@dataclass(frozen=True)
class DependencyWave:
    wave_id: str
    depends_on: tuple[str, ...]
    parallel: tuple[str, ...]
    partial_safe: bool = False

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "wave_id": self.wave_id,
            "depends_on": list(self.depends_on),
            "parallel": list(self.parallel),
        }
        if self.partial_safe:
            payload["partial_safe"] = True
        return payload


@dataclass(frozen=True)
class DependencyWaveManifest:
    plan_id: str
    waves: tuple[DependencyWave, ...]

    def ordered_waves(self) -> tuple[DependencyWave, ...]:
        original_order = {wave.wave_id: index for index, wave in enumerate(self.waves)}
        remaining = {wave.wave_id: set(wave.depends_on) for wave in self.waves}
        wave_map = {wave.wave_id: wave for wave in self.waves}
        ready = deque(sorted((wave.wave_id for wave in self.waves if not wave.depends_on), key=original_order.get))
        ordered: list[DependencyWave] = []

        while ready:
            wave_id = ready.popleft()
            if wave_id not in remaining:
                continue
            ordered.append(wave_map[wave_id])
            remaining.pop(wave_id, None)
            newly_ready: list[str] = []
            for candidate, dependencies in remaining.items():
                if wave_id in dependencies:
                    dependencies.discard(wave_id)
                    if not dependencies:
                        newly_ready.append(candidate)
            for candidate in sorted(newly_ready, key=original_order.get):
                ready.append(candidate)

        if remaining:
            cycle_nodes = ", ".join(sorted(remaining))
            raise ValueError(f"dependency-wave manifest contains a cycle involving: {cycle_nodes}")
        return tuple(ordered)

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "waves": [wave.as_dict() for wave in self.waves],
        }


@dataclass(frozen=True)
class WaveCommandResult:
    playbook: str
    wave_id: str
    metadata: PlaybookApplyMetadata
    command: tuple[str, ...]
    status: str
    returncode: int | None
    started_at: str | None
    finished_at: str | None
    elapsed_ms: int | None
    stdout: str
    stderr: str
    lock_resources: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "playbook": self.playbook,
            "wave_id": self.wave_id,
            "metadata": self.metadata.as_dict(),
            "command": list(self.command),
            "status": self.status,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "lock_resources": list(self.lock_resources),
        }
        if self.returncode is not None:
            payload["returncode"] = self.returncode
        if self.started_at is not None:
            payload["started_at"] = self.started_at
        if self.finished_at is not None:
            payload["finished_at"] = self.finished_at
        if self.elapsed_ms is not None:
            payload["elapsed_ms"] = self.elapsed_ms
        return payload


@dataclass(frozen=True)
class WaveExecutionResult:
    wave_id: str
    status: str
    partial_safe: bool
    depends_on: tuple[str, ...]
    results: tuple[WaveCommandResult, ...]
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "wave_id": self.wave_id,
            "status": self.status,
            "partial_safe": self.partial_safe,
            "depends_on": list(self.depends_on),
            "results": [result.as_dict() for result in self.results],
        }
        if self.error:
            payload["error"] = self.error
        return payload


@dataclass(frozen=True)
class DependencyWaveApplyResult:
    plan_id: str
    status: str
    waves: tuple[WaveExecutionResult, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "status": self.status,
            "waves": [wave.as_dict() for wave in self.waves],
        }


def load_playbook_apply_catalog(path: Path, *, repo_root: Path) -> PlaybookApplyCatalog:
    if not path.exists():
        return PlaybookApplyCatalog(entries={})
    payload = _require_mapping(yaml.safe_load(path.read_text(encoding="utf-8")) or {}, str(path))
    schema_version = _require_str(payload.get("schema_version"), f"{path}.schema_version")
    if schema_version != "1.0.0":
        raise ValueError(f"{path} must declare schema_version 1.0.0")
    playbooks = _require_list(payload.get("playbooks"), f"{path}.playbooks")
    make_targets = _parse_make_targets(repo_root)
    entries: dict[str, PlaybookApplyMetadata] = {}
    for index, raw_entry in enumerate(playbooks):
        entry = _require_mapping(raw_entry, f"{path}.playbooks[{index}]")
        normalized_path = _normalize_playbook_path(_require_str(entry.get("path"), f"{path}.playbooks[{index}].path"))
        if normalized_path in entries:
            raise ValueError(f"{path}.playbooks contains duplicate path {normalized_path}")
        make_target = _require_str(entry.get("make_target"), f"{path}.playbooks[{index}].make_target")
        if make_target not in make_targets:
            raise ValueError(f"{path}.playbooks[{index}].make_target references unknown target {make_target}")
        raw_make_vars = entry.get("make_vars") or {}
        make_vars_mapping = _require_mapping(raw_make_vars, f"{path}.playbooks[{index}].make_vars")
        metadata = PlaybookApplyMetadata(
            path=normalized_path,
            make_target=make_target,
            make_vars=tuple(
                sorted(
                    (
                        _require_str(key, f"{path}.playbooks[{index}].make_vars key"),
                        _require_str(value, f"{path}.playbooks[{index}].make_vars[{key}]"),
                    )
                    for key, value in make_vars_mapping.items()
                )
            ),
            mutation_scope=_require_str(entry.get("mutation_scope"), f"{path}.playbooks[{index}].mutation_scope"),
            target_hosts=_string_list(entry.get("target_hosts", []), f"{path}.playbooks[{index}].target_hosts"),
            execution_lane=_optional_str(entry.get("execution_lane")),
            shared_surfaces=_string_list(entry.get("shared_surfaces", []), f"{path}.playbooks[{index}].shared_surfaces"),
            lock_resources=_string_list(entry.get("lock_resources", []), f"{path}.playbooks[{index}].lock_resources"),
            workflow_id=_optional_str(entry.get("workflow_id")),
        )
        entries[normalized_path] = metadata
    return PlaybookApplyCatalog(entries=entries)


def load_dependency_wave_manifest(path: Path) -> DependencyWaveManifest:
    payload = _require_mapping(yaml.safe_load(path.read_text(encoding="utf-8")) or {}, str(path))
    plan_id = _require_str(payload.get("plan_id"), f"{path}.plan_id")
    waves_payload = _require_list(payload.get("waves"), f"{path}.waves")
    waves: list[DependencyWave] = []
    seen_wave_ids: set[str] = set()
    seen_playbooks: set[str] = set()
    for index, raw_wave in enumerate(waves_payload):
        wave = _require_mapping(raw_wave, f"{path}.waves[{index}]")
        wave_id = _require_str(wave.get("wave_id"), f"{path}.waves[{index}].wave_id")
        if wave_id in seen_wave_ids:
            raise ValueError(f"{path}.waves contains duplicate wave_id {wave_id}")
        seen_wave_ids.add(wave_id)
        playbooks = tuple(
            _normalize_playbook_path(_require_str(item, f"{path}.waves[{index}].parallel[{item_index}]"))
            for item_index, item in enumerate(_require_list(wave.get("parallel"), f"{path}.waves[{index}].parallel"))
        )
        if not playbooks:
            raise ValueError(f"{path}.waves[{index}].parallel must not be empty")
        for playbook in playbooks:
            if playbook in seen_playbooks:
                raise ValueError(f"{path} references {playbook} more than once; use one wave entry per playbook")
            seen_playbooks.add(playbook)
        waves.append(
            DependencyWave(
                wave_id=wave_id,
                depends_on=_string_list(wave.get("depends_on", []), f"{path}.waves[{index}].depends_on"),
                parallel=playbooks,
                partial_safe=bool(wave.get("partial_safe", False)),
            )
        )

    manifest = DependencyWaveManifest(plan_id=plan_id, waves=tuple(waves))
    known_wave_ids = {wave.wave_id for wave in manifest.waves}
    for wave in manifest.waves:
        missing = sorted(set(wave.depends_on) - known_wave_ids)
        if missing:
            raise ValueError(f"wave {wave.wave_id} depends on unknown waves: {', '.join(missing)}")
    manifest.ordered_waves()
    return manifest


CommandRunner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


class DependencyWaveExecutor:
    def __init__(
        self,
        *,
        repo_root: Path,
        catalog: PlaybookApplyCatalog,
        registry: ResourceLockRegistry | None = None,
        command_runner: CommandRunner | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.catalog = catalog
        self.registry = registry or ResourceLockRegistry(repo_root=repo_root)
        self.command_runner = command_runner or self._default_runner
        self.now_fn = now_fn or _utc_now

    def execute(
        self,
        manifest: DependencyWaveManifest,
        *,
        env: str,
        extra_args: str = "",
        lock_ttl_seconds: int = 1800,
        heartbeat_seconds: int | None = None,
        dry_run: bool = False,
    ) -> DependencyWaveApplyResult:
        if lock_ttl_seconds <= 0:
            raise ValueError("lock_ttl_seconds must be positive")
        heartbeat_interval = heartbeat_seconds or max(5, lock_ttl_seconds // 3)
        wave_results: list[WaveExecutionResult] = []
        blocked = False

        for wave in manifest.ordered_waves():
            if blocked:
                skipped = tuple(
                    WaveCommandResult(
                        playbook=playbook,
                        wave_id=wave.wave_id,
                        metadata=self.catalog.resolve(playbook, repo_root=self.repo_root),
                        command=tuple(),
                        status="skipped",
                        returncode=None,
                        started_at=None,
                        finished_at=None,
                        elapsed_ms=None,
                        stdout="",
                        stderr="skipped because an earlier wave failed",
                        lock_resources=(),
                    )
                    for playbook in wave.parallel
                )
                wave_results.append(
                    WaveExecutionResult(
                        wave_id=wave.wave_id,
                        status="skipped",
                        partial_safe=wave.partial_safe,
                        depends_on=wave.depends_on,
                        results=skipped,
                        error="earlier wave failed",
                    )
                )
                continue

            metadata = [self.catalog.resolve(playbook, repo_root=self.repo_root) for playbook in wave.parallel]
            shard_error = self._check_wave_shards(metadata)
            if shard_error is not None:
                wave_results.append(
                    WaveExecutionResult(
                        wave_id=wave.wave_id,
                        status="invalid",
                        partial_safe=wave.partial_safe,
                        depends_on=wave.depends_on,
                        results=tuple(),
                        error=shard_error,
                    )
                )
                blocked = True
                continue

            if dry_run:
                dry_results = tuple(
                    WaveCommandResult(
                        playbook=item.normalized_path,
                        wave_id=wave.wave_id,
                        metadata=item,
                        command=tuple(item.make_command(env=env, extra_args=extra_args)),
                        status="planned",
                        returncode=None,
                        started_at=None,
                        finished_at=None,
                        elapsed_ms=None,
                        stdout="",
                        stderr="",
                        lock_resources=item.effective_lock_resources(),
                    )
                    for item in metadata
                )
                wave_results.append(
                    WaveExecutionResult(
                        wave_id=wave.wave_id,
                        status="planned",
                        partial_safe=wave.partial_safe,
                        depends_on=wave.depends_on,
                        results=dry_results,
                    )
                )
                continue

            acquired_holders: list[str] = []
            acquired_lock_ids: list[str] = []
            try:
                for index, item in enumerate(metadata):
                    holder = f"dependency-wave:{manifest.plan_id}:{wave.wave_id}:{index + 1}"
                    for resource in item.effective_lock_resources():
                        entry = self.registry.acquire(
                            resource_path=resource,
                            lock_type=LockType.EXCLUSIVE,
                            holder=holder,
                            context_id=manifest.plan_id,
                            ttl_seconds=lock_ttl_seconds,
                            metadata={"plan_id": manifest.plan_id, "wave_id": wave.wave_id, "playbook": item.path},
                        )
                        acquired_lock_ids.append(entry.lock_id)
                    acquired_holders.append(holder)
            except ResourceLocked as exc:
                self._release_holders(acquired_holders)
                wave_results.append(
                    WaveExecutionResult(
                        wave_id=wave.wave_id,
                        status="blocked",
                        partial_safe=wave.partial_safe,
                        depends_on=wave.depends_on,
                        results=tuple(),
                        error=str(exc),
                    )
                )
                blocked = True
                continue

            stop_heartbeat = threading.Event()
            heartbeat = threading.Thread(
                target=self._heartbeat_locks,
                args=(acquired_lock_ids, stop_heartbeat, heartbeat_interval, lock_ttl_seconds),
                daemon=True,
            )
            heartbeat.start()
            try:
                results = self._run_wave_commands(wave_id=wave.wave_id, metadata=metadata, env=env, extra_args=extra_args)
            finally:
                stop_heartbeat.set()
                heartbeat.join(timeout=max(heartbeat_interval, 1))
                self._release_holders(acquired_holders)

            failed = any(result.returncode not in (None, 0) for result in results)
            status = "partial_failed" if failed and wave.partial_safe else "failed" if failed else "completed"
            wave_results.append(
                WaveExecutionResult(
                    wave_id=wave.wave_id,
                    status=status,
                    partial_safe=wave.partial_safe,
                    depends_on=wave.depends_on,
                    results=results,
                )
            )
            if failed and not wave.partial_safe:
                blocked = True

        statuses = {wave.status for wave in wave_results}
        if "failed" in statuses or "blocked" in statuses or "invalid" in statuses:
            overall = "failed"
        elif "partial_failed" in statuses:
            overall = "partial_failed"
        elif statuses == {"planned"}:
            overall = "planned"
        else:
            overall = "completed"
        return DependencyWaveApplyResult(plan_id=manifest.plan_id, status=overall, waves=tuple(wave_results))

    @staticmethod
    def _default_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)

    def _check_wave_shards(self, metadata: list[PlaybookApplyMetadata]) -> str | None:
        for index, first in enumerate(metadata):
            for second in metadata[index + 1 :]:
                overlap = sorted(first.shard_keys() & second.shard_keys())
                if overlap:
                    joined = ", ".join(overlap)
                    return (
                        f"wave shard conflict: {first.normalized_path} and {second.normalized_path} "
                        f"both claim {joined}"
                    )
        return None

    def _run_wave_commands(
        self,
        *,
        wave_id: str,
        metadata: list[PlaybookApplyMetadata],
        env: str,
        extra_args: str,
    ) -> tuple[WaveCommandResult, ...]:
        ordered_results: dict[str, WaveCommandResult] = {}

        def run_one(item: PlaybookApplyMetadata) -> WaveCommandResult:
            command = item.make_command(env=env, extra_args=extra_args)
            started = self.now_fn()
            started_monotonic = time.monotonic()
            completed = self.command_runner(command, self.repo_root)
            finished = self.now_fn()
            return WaveCommandResult(
                playbook=item.normalized_path,
                wave_id=wave_id,
                metadata=item,
                command=tuple(command),
                status="completed" if completed.returncode == 0 else "failed",
                returncode=completed.returncode,
                started_at=_isoformat(started),
                finished_at=_isoformat(finished),
                elapsed_ms=int((time.monotonic() - started_monotonic) * 1000),
                stdout=completed.stdout or "",
                stderr=completed.stderr or "",
                lock_resources=item.effective_lock_resources(),
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(metadata))) as executor:
            future_map = {executor.submit(run_one, item): item.normalized_path for item in metadata}
            for future in concurrent.futures.as_completed(future_map):
                result = future.result()
                ordered_results[future_map[future]] = result

        return tuple(ordered_results[item.normalized_path] for item in metadata)

    def _heartbeat_locks(
        self,
        lock_ids: list[str],
        stop_event: threading.Event,
        heartbeat_seconds: int,
        ttl_seconds: int,
    ) -> None:
        while not stop_event.wait(timeout=heartbeat_seconds):
            for lock_id in lock_ids:
                self.registry.heartbeat(lock_id, ttl_seconds=ttl_seconds)

    def _release_holders(self, holders: list[str]) -> None:
        for holder in holders:
            self.registry.release_all(holder)


def execute_dependency_wave_manifest(
    *,
    repo_root: Path,
    manifest_path: Path,
    catalog_path: Path,
    env: str,
    extra_args: str = "",
    lock_ttl_seconds: int = 1800,
    heartbeat_seconds: int | None = None,
    dry_run: bool = False,
    registry: ResourceLockRegistry | None = None,
    command_runner: CommandRunner | None = None,
) -> DependencyWaveApplyResult:
    manifest = load_dependency_wave_manifest(manifest_path)
    catalog = load_playbook_apply_catalog(catalog_path, repo_root=repo_root)
    executor = DependencyWaveExecutor(
        repo_root=repo_root,
        catalog=catalog,
        registry=registry,
        command_runner=command_runner,
    )
    return executor.execute(
        manifest,
        env=env,
        extra_args=extra_args,
        lock_ttl_seconds=lock_ttl_seconds,
        heartbeat_seconds=heartbeat_seconds,
        dry_run=dry_run,
    )
