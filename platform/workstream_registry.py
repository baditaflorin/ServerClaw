from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Any

from platform.datetime_compat import UTC, datetime
from platform.repo import load_yaml, repo_path


WORKSTREAMS_PATH = repo_path("workstreams.yaml")
WORKSTREAMS_DIR = repo_path("workstreams")
POLICY_PATH = repo_path("workstreams", "policy.yaml")
ACTIVE_DIR = repo_path("workstreams", "active")
ARCHIVE_DIR = repo_path("workstreams", "archive")
ACTIVE_STATUSES = {"blocked", "in_progress", "planned", "ready", "ready_for_merge"}
TERMINAL_STATUSES = {"implemented", "live_applied", "merged"}
GENERATED_HEADER = """# GENERATED FILE — do not edit by hand
# Source shards: workstreams/policy.yaml + workstreams/active/*.yaml + workstreams/archive/**/*.yaml
# Regenerate: python3 scripts/workstream_registry.py --write
"""


@dataclass(frozen=True)
class RegistryPaths:
    repo_root: Path
    compatibility_path: Path
    policy_path: Path
    active_dir: Path
    archive_dir: Path


@dataclass(frozen=True)
class LoadedWorkstream:
    payload: dict[str, Any]
    path: Path
    location: str
    archive_year: str | None = None


def resolve_paths(
    *,
    repo_root: Path | None = None,
    compatibility_path: Path | None = None,
) -> RegistryPaths:
    resolved_repo_root = repo_root or (
        compatibility_path.parent if compatibility_path is not None else repo_path()
    )
    resolved_compatibility_path = compatibility_path or (resolved_repo_root / "workstreams.yaml")
    workstreams_dir = resolved_repo_root / "workstreams"
    return RegistryPaths(
        repo_root=resolved_repo_root,
        compatibility_path=resolved_compatibility_path,
        policy_path=workstreams_dir / "policy.yaml",
        active_dir=workstreams_dir / "active",
        archive_dir=workstreams_dir / "archive",
    )


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a mapping")
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def _adr_sort_value(value: Any) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return -1


def _sort_workstreams(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: (_adr_sort_value(item.get("adr")), str(item.get("id", ""))), reverse=True)


def _yaml_module():
    try:
        import yaml  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
        raise RuntimeError(
            "Missing dependency: PyYAML. Run via 'uvx --from pyyaml python ...' or 'uv run --with pyyaml ...'."
        ) from exc
    return yaml


def _dump_yaml(payload: dict[str, Any]) -> str:
    yaml = _yaml_module()
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=False)


def _clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if not str(key).startswith("__")}


def has_sharded_sources(
    *,
    repo_root: Path | None = None,
    compatibility_path: Path | None = None,
) -> bool:
    paths = resolve_paths(repo_root=repo_root, compatibility_path=compatibility_path)
    return paths.policy_path.exists() and paths.active_dir.is_dir() and paths.archive_dir.is_dir()


def _release_bookkeeping_pending(workstream: dict[str, Any]) -> bool:
    canonical_truth = workstream.get("canonical_truth")
    if not isinstance(canonical_truth, dict):
        return False
    changelog_entry = canonical_truth.get("changelog_entry")
    release_bump = canonical_truth.get("release_bump")
    included_in_repo_version = canonical_truth.get("included_in_repo_version")
    return (
        isinstance(changelog_entry, str)
        and bool(changelog_entry.strip())
        and isinstance(release_bump, str)
        and bool(release_bump.strip())
        and included_in_repo_version is None
    )


def is_active_workstream(workstream: dict[str, Any]) -> bool:
    status = str(workstream.get("status", "")).strip()
    if status in ACTIVE_STATUSES:
        return True
    if status in TERMINAL_STATUSES and _release_bookkeeping_pending(workstream):
        return True
    return False


def _iter_shard_paths(
    paths: RegistryPaths,
    *,
    include_active: bool = True,
    include_archive: bool = True,
) -> list[Path]:
    shard_paths: list[Path] = []
    if include_active and paths.active_dir.exists():
        shard_paths.extend(sorted(paths.active_dir.glob("*.yaml")))
    if include_archive and paths.archive_dir.exists():
        for year_dir in sorted(path for path in paths.archive_dir.iterdir() if path.is_dir()):
            shard_paths.extend(sorted(year_dir.glob("*.yaml")))
    return shard_paths


def load_policy(
    *,
    repo_root: Path | None = None,
    compatibility_path: Path | None = None,
) -> dict[str, Any]:
    paths = resolve_paths(repo_root=repo_root, compatibility_path=compatibility_path)
    if paths.policy_path.exists():
        payload = _require_mapping(load_yaml(paths.policy_path), str(paths.policy_path))
        return {
            "schema_version": payload.get("schema_version", "1.0.0"),
            "delivery_model": _require_mapping(payload.get("delivery_model"), "workstreams/policy.yaml.delivery_model"),
            "release_policy": _require_mapping(payload.get("release_policy"), "workstreams/policy.yaml.release_policy"),
        }

    payload = _require_mapping(load_yaml(paths.compatibility_path), str(paths.compatibility_path))
    return {
        "schema_version": payload.get("schema_version", "1.0.0"),
        "delivery_model": _require_mapping(payload.get("delivery_model"), "workstreams.yaml.delivery_model"),
        "release_policy": _require_mapping(payload.get("release_policy"), "workstreams.yaml.release_policy"),
    }


def load_shard_workstreams(
    *,
    repo_root: Path | None = None,
    compatibility_path: Path | None = None,
    include_active: bool = True,
    include_archive: bool = True,
) -> list[LoadedWorkstream]:
    paths = resolve_paths(repo_root=repo_root, compatibility_path=compatibility_path)
    result: list[LoadedWorkstream] = []
    for shard_path in _iter_shard_paths(paths, include_active=include_active, include_archive=include_archive):
        payload = _require_mapping(load_yaml(shard_path), str(shard_path))
        workstream_id = _require_str(payload.get("id"), f"{shard_path}.id")
        if shard_path.stem != workstream_id:
            raise ValueError(f"{shard_path} must match workstream id '{workstream_id}'")

        if shard_path.parent == paths.active_dir:
            if not is_active_workstream(payload):
                raise ValueError(f"{shard_path} is under workstreams/active but is not currently active")
            result.append(LoadedWorkstream(payload=_clean_payload(payload), path=shard_path, location="active"))
            continue

        if paths.archive_dir not in shard_path.parents:
            raise ValueError(f"{shard_path} must live under {paths.active_dir} or {paths.archive_dir}")
        archive_year = shard_path.parent.name
        if len(archive_year) != 4 or not archive_year.isdigit():
            raise ValueError(f"{shard_path} must live under workstreams/archive/<year>/")
        if is_active_workstream(payload):
            raise ValueError(f"{shard_path} is under workstreams/archive but still requires active tracking")
        result.append(
            LoadedWorkstream(
                payload=_clean_payload(payload),
                path=shard_path,
                location="archive",
                archive_year=archive_year,
            )
        )
    return sorted(result, key=lambda item: (_adr_sort_value(item.payload.get("adr")), str(item.payload.get("id", ""))), reverse=True)


def load_assembled_registry(
    *,
    repo_root: Path | None = None,
    compatibility_path: Path | None = None,
) -> dict[str, Any]:
    paths = resolve_paths(repo_root=repo_root, compatibility_path=compatibility_path)
    if paths.compatibility_path.exists():
        return _require_mapping(load_yaml(paths.compatibility_path), str(paths.compatibility_path))
    return assemble_registry(repo_root=paths.repo_root)


def load_registry(
    *,
    repo_root: Path | None = None,
    compatibility_path: Path | None = None,
    include_archive: bool = True,
) -> dict[str, Any]:
    if has_sharded_sources(repo_root=repo_root, compatibility_path=compatibility_path):
        return assemble_registry(
            repo_root=repo_root,
            compatibility_path=compatibility_path,
            include_archive=include_archive,
        )
    return load_assembled_registry(repo_root=repo_root, compatibility_path=compatibility_path)


def load_workstreams(
    *,
    repo_root: Path | None = None,
    compatibility_path: Path | None = None,
    include_archive: bool = True,
) -> list[dict[str, Any]]:
    registry = load_registry(
        repo_root=repo_root,
        compatibility_path=compatibility_path,
        include_archive=include_archive,
    )
    workstreams = _require_list(registry.get("workstreams"), "workstreams.workstreams")
    return [_clean_payload(_require_mapping(item, "workstreams.workstreams[]")) for item in workstreams]


def load_active_workstreams(
    *,
    repo_root: Path | None = None,
    compatibility_path: Path | None = None,
) -> list[dict[str, Any]]:
    if has_sharded_sources(repo_root=repo_root, compatibility_path=compatibility_path):
        records = load_shard_workstreams(
            repo_root=repo_root,
            compatibility_path=compatibility_path,
            include_active=True,
            include_archive=False,
        )
        return [_clean_payload(record.payload) for record in records]
    return load_workstreams(repo_root=repo_root, compatibility_path=compatibility_path, include_archive=False)


def find_workstream(
    workstream_id: str,
    *,
    repo_root: Path | None = None,
    compatibility_path: Path | None = None,
    include_archive: bool = True,
) -> LoadedWorkstream | None:
    if has_sharded_sources(repo_root=repo_root, compatibility_path=compatibility_path):
        records = load_shard_workstreams(
            repo_root=repo_root,
            compatibility_path=compatibility_path,
            include_active=True,
            include_archive=include_archive,
        )
        return next((record for record in records if record.payload.get("id") == workstream_id), None)

    registry = load_assembled_registry(repo_root=repo_root, compatibility_path=compatibility_path)
    workstreams = _require_list(registry.get("workstreams"), "workstreams.yaml.workstreams")
    for item in workstreams:
        workstream = _require_mapping(item, "workstreams.yaml.workstreams[]")
        if str(workstream.get("id", "")).strip() == workstream_id:
            return LoadedWorkstream(
                payload=_clean_payload(workstream),
                path=resolve_paths(repo_root=repo_root, compatibility_path=compatibility_path).compatibility_path,
                location="compatibility",
            )
    return None


def build_archive_summary(records: list[LoadedWorkstream]) -> dict[str, Any]:
    by_year: dict[str, int] = {}
    for record in records:
        if record.archive_year is None:
            continue
        by_year[record.archive_year] = by_year.get(record.archive_year, 0) + 1
    return {
        "root": "workstreams/archive",
        "total_workstreams": sum(by_year.values()),
        "by_year": dict(sorted(by_year.items())),
    }


def assemble_registry(
    *,
    repo_root: Path | None = None,
    compatibility_path: Path | None = None,
    include_archive: bool = False,
) -> dict[str, Any]:
    policy = load_policy(repo_root=repo_root, compatibility_path=compatibility_path)
    if not has_sharded_sources(repo_root=repo_root, compatibility_path=compatibility_path):
        registry = load_assembled_registry(repo_root=repo_root, compatibility_path=compatibility_path)
        if include_archive:
            return registry
        return {
            "schema_version": registry.get("schema_version", policy.get("schema_version", "1.0.0")),
            "delivery_model": registry.get("delivery_model", policy["delivery_model"]),
            "release_policy": registry.get("release_policy", policy["release_policy"]),
            "workstreams": _require_list(registry.get("workstreams"), "workstreams.yaml.workstreams"),
        }

    active_records = load_shard_workstreams(
        repo_root=repo_root,
        compatibility_path=compatibility_path,
        include_active=True,
        include_archive=False,
    )
    archive_records = load_shard_workstreams(
        repo_root=repo_root,
        compatibility_path=compatibility_path,
        include_active=False,
        include_archive=True,
    )
    payload: dict[str, Any] = {
        "schema_version": policy["schema_version"],
        "delivery_model": policy["delivery_model"],
        "release_policy": policy["release_policy"],
        "archive_summary": build_archive_summary(archive_records),
        "workstreams": _sort_workstreams([_clean_payload(record.payload) for record in active_records]),
    }
    if include_archive:
        payload["workstreams"] = _sort_workstreams(
            [_clean_payload(record.payload) for record in active_records]
            + [_clean_payload(record.payload) for record in archive_records]
        )
    return payload


def compatibility_matches_source(
    *,
    repo_root: Path | None = None,
    compatibility_path: Path | None = None,
) -> bool:
    if not has_sharded_sources(repo_root=repo_root, compatibility_path=compatibility_path):
        return True
    expected = assemble_registry(repo_root=repo_root, compatibility_path=compatibility_path, include_archive=False)
    actual = load_assembled_registry(repo_root=repo_root, compatibility_path=compatibility_path)
    return actual == expected


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_policy(policy: dict[str, Any], *, paths: RegistryPaths) -> Path:
    payload = {
        "schema_version": policy.get("schema_version", "1.0.0"),
        "delivery_model": policy["delivery_model"],
        "release_policy": policy["release_policy"],
    }
    _write_text(paths.policy_path, _dump_yaml(payload))
    return paths.policy_path


def determine_target_path(
    workstream: dict[str, Any],
    *,
    paths: RegistryPaths,
    archive_year: str | None = None,
) -> Path:
    workstream_id = _require_str(workstream.get("id"), "workstream.id")
    if is_active_workstream(workstream):
        return paths.active_dir / f"{workstream_id}.yaml"
    resolved_archive_year = archive_year or str(datetime.now(UTC).year)
    return paths.archive_dir / resolved_archive_year / f"{workstream_id}.yaml"


def write_workstream(
    workstream: dict[str, Any],
    *,
    repo_root: Path | None = None,
    compatibility_path: Path | None = None,
    current_path: Path | None = None,
    archive_year: str | None = None,
) -> Path:
    paths = resolve_paths(repo_root=repo_root, compatibility_path=compatibility_path)
    payload = _clean_payload(_require_mapping(workstream, "workstream"))
    target_path = determine_target_path(payload, paths=paths, archive_year=archive_year)
    if current_path is not None and current_path != target_path and current_path.exists():
        current_path.unlink()
    _write_text(target_path, _dump_yaml(payload))
    return target_path


def write_assembled_registry(
    *,
    repo_root: Path | None = None,
    compatibility_path: Path | None = None,
) -> Path:
    paths = resolve_paths(repo_root=repo_root, compatibility_path=compatibility_path)
    payload = assemble_registry(repo_root=paths.repo_root, compatibility_path=paths.compatibility_path, include_archive=False)
    _write_text(paths.compatibility_path, GENERATED_HEADER + _dump_yaml(payload))
    return paths.compatibility_path


def migrate_from_compatibility(
    *,
    repo_root: Path | None = None,
    compatibility_path: Path | None = None,
    source_registry_path: Path | None = None,
    archive_year: str | None = None,
) -> dict[str, Any]:
    paths = resolve_paths(repo_root=repo_root, compatibility_path=compatibility_path)
    source_path = source_registry_path or paths.compatibility_path
    registry = _require_mapping(load_yaml(source_path), str(source_path))
    workstreams = [
        _clean_payload(_require_mapping(item, f"{source_path}.workstreams[]"))
        for item in _require_list(registry.get("workstreams"), f"{source_path}.workstreams")
    ]

    if paths.active_dir.exists():
        shutil.rmtree(paths.active_dir)
    if paths.archive_dir.exists():
        shutil.rmtree(paths.archive_dir)

    policy = {
        "schema_version": registry.get("schema_version", "1.0.0"),
        "delivery_model": _require_mapping(registry.get("delivery_model"), f"{source_path}.delivery_model"),
        "release_policy": _require_mapping(registry.get("release_policy"), f"{source_path}.release_policy"),
    }
    _write_policy(policy, paths=paths)

    written: list[str] = []
    for workstream in workstreams:
        target_path = write_workstream(
            workstream,
            repo_root=paths.repo_root,
            compatibility_path=paths.compatibility_path,
            archive_year=archive_year,
        )
        written.append(str(target_path.relative_to(paths.repo_root)))

    write_assembled_registry(repo_root=paths.repo_root, compatibility_path=paths.compatibility_path)
    return {
        "written": sorted(written),
        "active_count": len(load_active_workstreams(repo_root=paths.repo_root, compatibility_path=paths.compatibility_path)),
        "archive_count": len(load_workstreams(repo_root=paths.repo_root, compatibility_path=paths.compatibility_path, include_archive=True))
        - len(load_active_workstreams(repo_root=paths.repo_root, compatibility_path=paths.compatibility_path)),
    }
