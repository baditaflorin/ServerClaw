#!/usr/bin/env python3
"""Run ADR 0302 restic backups for platform configuration artifacts."""

from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import ipaddress
import json
import os
import shlex
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from script_bootstrap import ensure_repo_root_on_path

REPO_ROOT = ensure_repo_root_on_path(__file__)

from controller_automation_toolkit import emit_cli_error, load_json, repo_path
from platform.events import build_envelope


DEFAULT_REPO_ROOT = Path("/srv/proxmox_florin_server")
DEFAULT_CATALOG_PATH = repo_path("config", "restic-file-backup-catalog.json")
DEFAULT_BACKUP_RECEIPT_DIR = repo_path("receipts", "restic-backups")
DEFAULT_LATEST_RECEIPT_PATH = repo_path("receipts", "restic-snapshots-latest.json")
DEFAULT_RESTORE_VERIFY_DIR = repo_path("receipts", "restic-restore-verifications")
DEFAULT_CACHE_DIR = Path("/var/lib/lv3/restic-config-backup/cache")
DEFAULT_RUNTIME_STATE_DIR = Path("/var/lib/lv3/restic-config-backup")
DEFAULT_RUNTIME_CONFIG_NAME = "runtime-config.json"
DEFAULT_LOCK_FILENAME = "restic-config-backup.lock"
DEFAULT_LOCK_TIMEOUT_SECONDS = 300
DEFAULT_LOCK_POLL_SECONDS = 1.0
DEFAULT_TRIGGER = "manual"
DEFAULT_GRACE_MINUTES = 30
NTFY_CRITICAL_TITLE = "Restic backup critical"
NTFY_STALE_MESSAGE_PREFIX = "Restic backup source is stale"
FALLBACK_MINIO_CONTAINER_NAMES = ("outline-minio",)


@dataclass(frozen=True)
class Source:
    source_id: str
    label: str
    paths: tuple[Path, ...]
    freshness_minutes: int
    freshness_policy: str
    expected_schedule: str
    retention: dict[str, int]
    trigger_on_live_apply: bool
    optional: bool
    restore_verification: dict[str, Any] | None


def utc_now() -> datetime:
    return datetime.now(UTC)


def isoformat(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def display_path(path: Path, *, repo_root: Path = REPO_ROOT) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def run_command(
    argv: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        text=True,
        capture_output=True,
        check=False,
        env=env,
        cwd=str(cwd) if cwd else None,
    )


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_runtime_credentials(path: Path | None = None) -> dict[str, str]:
    candidate = path
    if candidate is None:
        credential_dir = os.environ.get("CREDENTIALS_DIRECTORY", "").strip()
        if credential_dir:
            candidate = Path(credential_dir) / DEFAULT_RUNTIME_CONFIG_NAME
    if candidate is None:
        raise ValueError("systemd runtime credentials are unavailable")
    payload = json.loads(Path(candidate).read_text(encoding="utf-8"))
    required = ("restic_password", "minio_secret_key", "nats_password", "ntfy_password")
    missing = [field for field in required if not str(payload.get(field) or "").strip()]
    if missing:
        raise ValueError("runtime credential payload is missing " + ", ".join(missing))
    return {str(key): str(value).strip() for key, value in payload.items() if isinstance(value, (str, int, float))}


def snapshot_id_from_backup_stdout(stdout: str) -> str | None:
    text = stdout.strip()
    if not text:
        return None
    for line in reversed(text.splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        record = json.loads(candidate)
        if isinstance(record, dict) and str(record.get("snapshot_id") or "").strip():
            return str(record["snapshot_id"]).strip()
    return None


def inspect_container_state(container_name: str) -> dict[str, Any]:
    inspect = run_command(
        [
            "docker",
            "inspect",
            container_name,
        ]
    )
    if inspect.returncode != 0:
        detail = inspect.stderr.strip() or inspect.stdout.strip() or f"failed to inspect {container_name}"
        raise RuntimeError(detail)
    try:
        payload = json.loads(inspect.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"unable to parse Docker inspect payload for {container_name}") from exc
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise RuntimeError(f"Docker inspect payload for {container_name} must contain one object")
    return payload[0]


def resolve_minio_container(container_name: str) -> tuple[str, dict[str, Any]]:
    candidates: list[str] = []
    for candidate in (container_name, *FALLBACK_MINIO_CONTAINER_NAMES):
        normalized = str(candidate or "").strip()
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    errors: list[str] = []
    for candidate in candidates:
        try:
            return candidate, inspect_container_state(candidate)
        except RuntimeError as exc:
            detail = str(exc)
            if "no such object" not in detail.lower():
                raise
            errors.append(f"{candidate}: {detail}")

    fallback_list = ", ".join(candidates)
    error_detail = "; ".join(errors) or "no candidate container was inspectable"
    raise RuntimeError(f"unable to inspect any configured MinIO container ({fallback_list}): {error_detail}")


def ensure_container_running(container_name: str, *, container: dict[str, Any] | None = None) -> dict[str, Any]:
    current = container or inspect_container_state(container_name)
    state = current.get("State", {})
    if state.get("Running"):
        return current

    status = str(state.get("Status") or "unknown").strip() or "unknown"
    start = run_command(["docker", "start", container_name])
    if start.returncode != 0:
        detail = start.stderr.strip() or start.stdout.strip() or "docker start failed"
        raise RuntimeError(f"{container_name} is {status} and docker start failed: {detail}")

    recovered = inspect_container_state(container_name)
    recovered_state = recovered.get("State", {})
    if recovered_state.get("Running"):
        return recovered

    recovered_status = str(recovered_state.get("Status") or "unknown").strip() or "unknown"
    raise RuntimeError(
        f"{container_name} is {recovered_status} after docker start; "
        "converge the Outline MinIO runtime before rerunning restic config backup"
    )


def resolve_minio_endpoint(catalog: dict[str, Any]) -> tuple[str, str]:
    controller_host = catalog.get("controller_host", {})
    minio = controller_host.get("minio", {})
    container_name = str(minio.get("container_name") or "").strip()
    if not container_name:
        raise ValueError("restic catalog is missing controller_host.minio.container_name")
    live_container_name, container = resolve_minio_container(container_name)
    container = ensure_container_running(live_container_name, container=container)

    networks = container.get("NetworkSettings", {}).get("Networks", {}) or {}
    first_valid_ip: str | None = None
    first_valid_version: int | None = None
    first_invalid_ip: str | None = None
    for network in networks.values():
        for candidate in (
            str(network.get("IPAddress") or "").strip(),
            str(network.get("GlobalIPv6Address") or "").strip(),
        ):
            if not candidate:
                continue
            try:
                parsed = ipaddress.ip_address(candidate)
            except ValueError:
                first_invalid_ip = first_invalid_ip or candidate
                continue
            if first_valid_ip is None or (first_valid_version != 4 and parsed.version == 4):
                first_valid_ip = candidate
                first_valid_version = parsed.version

    if first_valid_ip is None:
        if first_invalid_ip:
            raise RuntimeError(f"{live_container_name} reported an invalid container IP: {first_invalid_ip!r}")
        raise RuntimeError(f"{live_container_name} has no reachable container IP")

    host = first_valid_ip if first_valid_version == 4 else f"[{first_valid_ip}]"
    return first_valid_ip, f"http://{host}:9000"


def restic_repository(catalog: dict[str, Any], endpoint: str) -> str:
    minio = catalog["controller_host"]["minio"]
    bucket = str(minio.get("bucket") or "").strip()
    if not bucket:
        raise ValueError("restic catalog is missing controller_host.minio.bucket")
    return f"s3:{endpoint.rstrip('/')}/{bucket}"


def build_restic_env(
    *,
    catalog: dict[str, Any],
    credentials: dict[str, str],
    endpoint: str,
    cache_dir: Path,
) -> dict[str, str]:
    minio = catalog["controller_host"]["minio"]
    env = os.environ.copy()
    env["RESTIC_REPOSITORY"] = restic_repository(catalog, endpoint)
    env["RESTIC_PASSWORD"] = credentials["restic_password"]
    env["AWS_ACCESS_KEY_ID"] = str(
        minio.get("access_key")
        or credentials.get("minio_access_key")
        or credentials.get("minio")
        or "minio"
    ).strip()
    env["AWS_SECRET_ACCESS_KEY"] = credentials["minio_secret_key"]
    env["RESTIC_CACHE_DIR"] = str(cache_dir)
    return env


def restic_common_args(catalog: dict[str, Any]) -> list[str]:
    minio = catalog["controller_host"]["minio"]
    return [
        "--option",
        f"s3.region={minio.get('region', 'eu-central-1')}",
        "--option",
        f"s3.bucket-lookup={minio.get('bucket_lookup', 'path')}",
    ]


def restic_call(
    args: list[str],
    *,
    catalog: dict[str, Any],
    credentials: dict[str, str],
    endpoint: str,
    cache_dir: Path,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = ["restic", *restic_common_args(catalog), *args]
    outcome = run_command(
        command,
        env=build_restic_env(catalog=catalog, credentials=credentials, endpoint=endpoint, cache_dir=cache_dir),
        cwd=cwd,
    )
    if outcome.returncode != 0:
        detail = outcome.stderr.strip() or outcome.stdout.strip() or "restic command failed"
        raise RuntimeError(" ".join(shlex.quote(item) for item in command) + f": {detail}")
    return outcome


def ensure_restic_repository(
    *,
    catalog: dict[str, Any],
    credentials: dict[str, str],
    endpoint: str,
    cache_dir: Path,
) -> None:
    snapshots = run_command(
        ["restic", *restic_common_args(catalog), "snapshots", "--json"],
        env=build_restic_env(catalog=catalog, credentials=credentials, endpoint=endpoint, cache_dir=cache_dir),
    )
    if snapshots.returncode == 0:
        return
    stderr = snapshots.stderr.lower()
    stdout = snapshots.stdout.lower()
    if "wrong password" in stderr:
        detail = snapshots.stderr.strip() or snapshots.stdout.strip() or "unable to inspect restic repository"
        raise RuntimeError(detail)
    if (
        "is there a repository at the following location?" in stderr
        or "config file does not exist" in stdout
        or "unable to open config file" in stderr
    ):
        restic_call(
            ["init"],
            catalog=catalog,
            credentials=credentials,
            endpoint=endpoint,
            cache_dir=cache_dir,
        )
        return
    detail = snapshots.stderr.strip() or snapshots.stdout.strip() or "unable to inspect restic repository"
    raise RuntimeError(detail)


def load_catalog(path: Path) -> tuple[dict[str, Any], list[Source]]:
    payload = load_json(path)
    if str(payload.get("schema_version") or "") != "1.0.0":
        raise ValueError(f"{path} must declare schema_version 1.0.0")

    sources: list[Source] = []
    for raw in payload.get("sources", []):
        if not isinstance(raw, dict):
            raise ValueError("restic source entries must be objects")
        source_id = str(raw.get("id") or "").strip()
        if not source_id:
            raise ValueError("restic source id is required")
        raw_paths = raw.get("paths") or []
        if not isinstance(raw_paths, list) or not raw_paths:
            raise ValueError(f"restic source {source_id} must define non-empty paths")
        retention = raw.get("retention") or {}
        if not isinstance(retention, dict):
            raise ValueError(f"restic source {source_id} retention must be an object")
        freshness_policy = str(raw.get("freshness_policy") or "interval").strip().lower()
        if freshness_policy not in {"interval", "event_driven"}:
            raise ValueError(
                f"restic source {source_id} freshness_policy must be 'interval' or 'event_driven'"
            )
        restore_verification = raw.get("restore_verification")
        if restore_verification is not None and not isinstance(restore_verification, dict):
            raise ValueError(f"restic source {source_id} restore_verification must be an object")
        sources.append(
            Source(
                source_id=source_id,
                label=str(raw.get("label") or source_id),
                paths=tuple(Path(str(item)) for item in raw_paths),
                freshness_minutes=int(raw.get("freshness_minutes") or 0),
                freshness_policy=freshness_policy,
                expected_schedule=str(raw.get("expected_schedule") or "unspecified").strip() or "unspecified",
                retention={str(key): int(value) for key, value in retention.items()},
                trigger_on_live_apply=bool(raw.get("trigger_on_live_apply", False)),
                optional=bool(raw.get("optional", False)),
                restore_verification=restore_verification,
            )
        )
    return payload, sources


def resolve_source_paths(sources: list[Source], repo_root: Path) -> list[Source]:
    resolved: list[Source] = []
    for source in sources:
        resolved.append(
            replace(
                source,
                paths=tuple(path if path.is_absolute() else repo_root / path for path in source.paths),
            )
        )
    return resolved


def filter_sources(sources: list[Source], *, only_live_apply: bool) -> list[Source]:
    if only_live_apply:
        return [source for source in sources if source.trigger_on_live_apply]
    return [source for source in sources if not source.trigger_on_live_apply]


def count_files(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return 1
    return sum(1 for candidate in path.rglob("*") if candidate.is_file())


def latest_restore_verification(receipt_dir: Path, repo_root: Path = REPO_ROOT) -> dict[str, Any] | None:
    if not receipt_dir.is_dir():
        return None
    latest: tuple[datetime, dict[str, Any]] | None = None
    for path in sorted(receipt_dir.glob("*.json")):
        payload = load_json(path)
        recorded_at = parse_datetime(str(payload.get("recorded_at") or "")) or parse_datetime(
            str(payload.get("restored_at") or "")
        )
        if recorded_at is None:
            continue
        candidate = {
            "recorded_at": isoformat(recorded_at),
            "path": display_path(path, repo_root=repo_root),
            "result": str(payload.get("result") or "unknown"),
        }
        if latest is None or recorded_at > latest[0]:
            latest = (recorded_at, candidate)
    return latest[1] if latest else None


def snapshot_for_source(source: Source, snapshots: list[dict[str, Any]]) -> dict[str, Any] | None:
    expected_tag = f"source:{source.source_id}"
    candidates: list[dict[str, Any]] = []
    for snapshot in snapshots:
        tags = snapshot.get("tags") or []
        if expected_tag not in tags:
            continue
        timestamp = parse_datetime(str(snapshot.get("time") or ""))
        if timestamp is None:
            continue
        candidates.append({**snapshot, "_parsed_time": timestamp})
    if not candidates:
        return None
    return max(candidates, key=lambda item: item["_parsed_time"])


def summarize_latest_snapshots(
    *,
    catalog: dict[str, Any],
    sources: list[Source],
    repo_root: Path,
    credentials: dict[str, str],
    endpoint: str,
    cache_dir: Path,
    restore_verify_dir: Path,
    generated_at: datetime,
) -> dict[str, Any]:
    snapshots_result = restic_call(
        ["snapshots", "--json"],
        catalog=catalog,
        credentials=credentials,
        endpoint=endpoint,
        cache_dir=cache_dir,
    )
    snapshots = json.loads(snapshots_result.stdout or "[]")
    if not isinstance(snapshots, list):
        raise ValueError("restic snapshots output must be a list")

    source_entries: list[dict[str, Any]] = []
    summary = {
        "governed_sources": len(sources),
        "protected": 0,
        "uncovered": 0,
        "inactive": 0,
        "uncovered_sources": [],
        "inactive_sources": [],
    }

    for source in sources:
        existing_paths = [path for path in source.paths if path.exists()]
        reasons: list[str] = []
        latest_snapshot = snapshot_for_source(source, snapshots)
        last_restore = (
            latest_restore_verification(restore_verify_dir, repo_root=repo_root)
            if source.restore_verification
            else None
        )

        state = "protected"
        rendered_snapshot: dict[str, Any] | None = None

        if not existing_paths and source.optional:
            state = "inactive"
            reasons.append(f"No live path currently exists for optional source {source.source_id} backup path.")
        elif latest_snapshot is None:
            state = "uncovered"
            reasons.append(f"No restic snapshot exists yet for source {source.source_id}.")
        else:
            snapshot_time = latest_snapshot["_parsed_time"]
            rendered_snapshot = {
                "snapshot_id": str(latest_snapshot.get("id") or ""),
                "recorded_at": isoformat(snapshot_time),
                "host": str(latest_snapshot.get("hostname") or ""),
                "paths": [display_path(Path(path), repo_root=repo_root) for path in latest_snapshot.get("paths", [])],
                "files": int(
                    ((latest_snapshot.get("summary") or {}) if isinstance(latest_snapshot.get("summary"), dict) else {}).get(
                        "total_files_processed",
                        0,
                    )
                    or 0
                ),
            }
            if source.freshness_policy == "event_driven":
                reasons.append(
                    "Latest snapshot exists and this source is governed by the event-driven "
                    f"'{source.expected_schedule}' policy."
                )
            else:
                age = max(generated_at - snapshot_time, timedelta())
                threshold = source.freshness_minutes + DEFAULT_GRACE_MINUTES
                if age > timedelta(minutes=threshold):
                    state = "uncovered"
                    reasons.append(
                        f"Latest snapshot is {int(age.total_seconds() // 60)} minutes old and exceeds the "
                        f"{threshold} minute freshness window."
                    )
                else:
                    reasons.append(
                        f"Latest snapshot is {int(age.total_seconds() // 60)} minutes old and within the "
                        f"{threshold} minute freshness window."
                    )

        entry = {
            "source_id": source.source_id,
            "label": source.label,
            "paths": [display_path(path, repo_root=repo_root) for path in source.paths],
            "state": state,
            "expected_schedule": source.expected_schedule,
            "freshness_minutes": source.freshness_minutes,
            "freshness_policy": source.freshness_policy,
            "retention": source.retention,
            "latest_snapshot": rendered_snapshot,
            "last_restore_verification": last_restore,
            "reasons": reasons,
        }
        source_entries.append(entry)
        summary[state] += 1
        if state == "uncovered":
            summary["uncovered_sources"].append(source.source_id)
        elif state == "inactive":
            summary["inactive_sources"].append(source.source_id)

    return {
        "schema_version": "1.0.0",
        "recorded_at": isoformat(generated_at),
        "recorded_on": generated_at.date().isoformat(),
        "recorded_by": "codex",
        "repository": {
            "bucket": catalog["controller_host"]["minio"]["bucket"],
            "endpoint": endpoint,
        },
        "summary": summary,
        "sources": source_entries,
    }


def load_existing_latest_snapshot_receipt(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = load_json(path)
    return payload if isinstance(payload, dict) else None


def _render_live_apply_source_entry(
    *,
    source: Source,
    result: dict[str, Any],
    repo_root: Path,
    host_name: str,
    generated_at: datetime,
    previous_entry: dict[str, Any] | None,
) -> dict[str, Any]:
    previous = previous_entry or {}
    display_paths = [display_path(path, repo_root=repo_root) for path in source.paths]
    last_restore = previous.get("last_restore_verification")
    latest_snapshot: dict[str, Any] | None = None
    reasons: list[str]

    if result.get("result") == "backed_up":
        latest_snapshot = {
            "snapshot_id": str(result.get("snapshot_id") or ""),
            "recorded_at": isoformat(generated_at),
            "host": host_name,
            "paths": display_paths,
            "files": int(result.get("files") or 0),
        }
        if source.freshness_policy == "event_driven":
            reasons = [
                "Latest snapshot exists and this source is governed by the event-driven "
                f"'{source.expected_schedule}' policy."
            ]
        else:
            threshold = source.freshness_minutes + DEFAULT_GRACE_MINUTES
            reasons = [f"Latest snapshot is 0 minutes old and within the {threshold} minute freshness window."]
        state = "protected"
    elif result.get("result") == "skipped_optional_missing":
        state = "inactive"
        reasons = [f"No live path currently exists for optional source {source.source_id} backup path."]
    else:
        state = str(previous.get("state") or ("inactive" if source.optional else "uncovered"))
        latest_snapshot = previous.get("latest_snapshot")
        reasons = list(previous.get("reasons") or [f"No new live-apply result was recorded for {source.source_id}."])

    return {
        "source_id": source.source_id,
        "label": source.label,
        "paths": display_paths,
        "state": state,
        "expected_schedule": source.expected_schedule,
        "freshness_minutes": source.freshness_minutes,
        "freshness_policy": source.freshness_policy,
        "retention": source.retention,
        "latest_snapshot": latest_snapshot,
        "last_restore_verification": last_restore,
        "reasons": reasons,
    }


def refresh_latest_snapshot_receipt_for_live_apply(
    *,
    existing_receipt: dict[str, Any],
    sources: list[Source],
    source_results: list[dict[str, Any]],
    repo_root: Path,
    endpoint: str,
    host_name: str,
    generated_at: datetime,
    bucket: str,
) -> dict[str, Any]:
    existing_entries = {
        str(entry.get("source_id") or ""): entry
        for entry in existing_receipt.get("sources", [])
        if isinstance(entry, dict) and str(entry.get("source_id") or "").strip()
    }
    results_by_source = {
        str(result.get("source_id") or ""): result
        for result in source_results
        if isinstance(result, dict) and str(result.get("source_id") or "").strip()
    }

    source_entries: list[dict[str, Any]] = []
    summary = {
        "governed_sources": len(sources),
        "protected": 0,
        "uncovered": 0,
        "inactive": 0,
        "uncovered_sources": [],
        "inactive_sources": [],
    }

    for source in sources:
        entry = _render_live_apply_source_entry(
            source=source,
            result=results_by_source.get(source.source_id, {}),
            repo_root=repo_root,
            host_name=host_name,
            generated_at=generated_at,
            previous_entry=existing_entries.get(source.source_id),
        )
        source_entries.append(entry)
        state = entry["state"]
        if state in {"protected", "uncovered", "inactive"}:
            summary[state] += 1
        if state == "uncovered":
            summary["uncovered_sources"].append(source.source_id)
        elif state == "inactive":
            summary["inactive_sources"].append(source.source_id)

    return {
        "schema_version": "1.0.0",
        "recorded_at": isoformat(generated_at),
        "recorded_on": generated_at.date().isoformat(),
        "recorded_by": "codex",
        "repository": {
            "bucket": bucket,
            "endpoint": endpoint,
        },
        "summary": summary,
        "sources": source_entries,
    }


def build_live_apply_latest_snapshot_receipt(
    *,
    existing_receipt: dict[str, Any] | None,
    resolved_sources: list[Source],
    live_apply_sources: list[Source],
    source_results: list[dict[str, Any]],
    repo_root: Path,
    endpoint: str,
    host_name: str,
    generated_at: datetime,
    bucket: str,
) -> dict[str, Any]:
    # Live-apply hooks should never force a repository-wide snapshot scan. If the
    # cached latest receipt is unavailable, synthesize a narrowed receipt from the
    # live-apply sources we just backed up and let the scheduled backup refresh the
    # full repository-wide snapshot view later.
    return refresh_latest_snapshot_receipt_for_live_apply(
        existing_receipt=existing_receipt or {},
        sources=resolved_sources if existing_receipt is not None else live_apply_sources,
        source_results=source_results,
        repo_root=repo_root,
        endpoint=endpoint,
        host_name=host_name,
        generated_at=generated_at,
        bucket=bucket,
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_directory(path.parent)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def post_ntfy_notification(
    catalog: dict[str, Any],
    credentials: dict[str, str],
    message: str,
) -> dict[str, Any]:
    ntfy = (catalog.get("controller_host") or {}).get("ntfy") or {}
    base_url = str(ntfy.get("url") or "http://127.0.0.1:2586").rstrip("/")
    topic = str(ntfy.get("topic") or "platform-alerts").strip() or "platform-alerts"
    username = str(ntfy.get("username") or "alertmanager").strip() or "alertmanager"
    password = credentials["ntfy_password"]
    publish_url = base_url if base_url.endswith(f"/{topic}") else f"{base_url}/{topic}"
    request = urllib.request.Request(
        publish_url,
        data=message.encode("utf-8"),
        method="POST",
        headers={
            "Authorization": "Basic " + base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii"),
            "Title": NTFY_CRITICAL_TITLE,
            "Priority": "4",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return {
                "channel": "ntfy",
                "topic": topic,
                "status": "sent",
                "http_status": response.status,
            }
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        return {
            "channel": "ntfy",
            "topic": topic,
            "status": "error",
            "error": str(exc),
        }


def publish_stale_event(
    catalog: dict[str, Any],
    credentials: dict[str, str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    nats = (catalog.get("controller_host") or {}).get("nats") or {}
    subject = str(nats.get("subject") or "platform.backup.stale").strip() or "platform.backup.stale"
    username = str(nats.get("username") or "jetstream-admin").strip() or "jetstream-admin"
    host = str(nats.get("host") or "127.0.0.1").strip() or "127.0.0.1"
    port = int(nats.get("port") or 4222)
    envelope = build_envelope(subject, payload, actor_id="service/restic-config-backup", ts=payload["recorded_at"])
    encoded = json.dumps(envelope, separators=(",", ":")).encode("utf-8")

    try:
        with socket.create_connection((host, port), timeout=5) as sock:
            reader = sock.makefile("rb")
            info = reader.readline().decode("utf-8", errors="replace").strip()
            if not info.startswith("INFO "):
                raise RuntimeError("NATS server did not return INFO banner")
            connect_payload = json.dumps(
                {
                    "protocol": 1,
                    "verbose": False,
                    "pedantic": False,
                    "user": username,
                    "pass": credentials["nats_password"],
                },
                separators=(",", ":"),
            )
            sock.sendall(f"CONNECT {connect_payload}\r\n".encode("utf-8"))
            sock.sendall(f"PUB {subject} {len(encoded)}\r\n".encode("utf-8"))
            sock.sendall(encoded + b"\r\nPING\r\n")
            for _ in range(5):
                response = reader.readline().decode("utf-8", errors="replace").strip()
                if not response:
                    continue
                if response.startswith("-ERR"):
                    raise RuntimeError(response)
                if response == "PONG" or response.startswith("+OK"):
                    return {
                        "channel": "nats",
                        "subject": subject,
                        "status": "sent",
                        "event_id": envelope["event_id"],
                    }
            raise RuntimeError("NATS server did not acknowledge publish")
    except (OSError, RuntimeError) as exc:
        return {
            "channel": "nats",
            "subject": subject,
            "status": "error",
            "error": str(exc),
        }


def emit_stale_signals(
    *,
    catalog: dict[str, Any],
    credentials: dict[str, str],
    latest_receipt: dict[str, Any],
    latest_receipt_path: Path,
) -> list[dict[str, Any]]:
    notifications: list[dict[str, Any]] = []
    for source in latest_receipt.get("sources", []):
        if source.get("freshness_policy") != "interval":
            continue
        if source.get("state") != "uncovered":
            continue
        summary = "; ".join(source.get("reasons") or []) or f"Source {source.get('source_id')} is stale."
        payload = {
            "event": "restic_snapshot_stale",
            "recorded_at": latest_receipt["recorded_at"],
            "source_id": source["source_id"],
            "summary": summary,
            "expected_max_age_minutes": int(source.get("freshness_minutes", 0)) + DEFAULT_GRACE_MINUTES,
        }
        notifications.append(publish_stale_event(catalog, credentials, payload))
        message = (
            f"{NTFY_STALE_MESSAGE_PREFIX}\nSource: {source['source_id']}\n"
            f"Latest snapshot receipt: {display_path(latest_receipt_path)}\n{summary}"
        )
        notifications.append(post_ntfy_notification(catalog, credentials, message))
    return notifications


def backup_source(
    source: Source,
    *,
    catalog: dict[str, Any],
    credentials: dict[str, str],
    endpoint: str,
    cache_dir: Path,
    host_name: str,
) -> dict[str, Any]:
    existing_paths = [path for path in source.paths if path.exists()]
    if not existing_paths and source.optional:
        return {
            "source_id": source.source_id,
            "result": "skipped_optional_missing",
            "paths": [str(path) for path in source.paths],
            "reason": "optional source path is not present on the runtime host",
        }
    missing_required = [path for path in source.paths if not path.exists()]
    if missing_required:
        raise RuntimeError(f"required source {source.source_id} backup path is missing: {missing_required[0]}")

    tags = [f"source:{source.source_id}", f"source-label:{source.label.lower()}"]
    outcome = restic_call(
        [
            "backup",
            "--json",
            "--host",
            host_name,
            "--tag",
            tags[0],
            "--tag",
            tags[1],
            *[str(path) for path in source.paths],
        ],
        catalog=catalog,
        credentials=credentials,
        endpoint=endpoint,
        cache_dir=cache_dir,
    )
    retention_args: list[str] = []
    for key, value in sorted(source.retention.items()):
        retention_args.extend([f"--{key.replace('_', '-')}", str(value)])
    if retention_args:
        restic_call(
            [
                "forget",
                "--prune",
                "--group-by",
                "host,tags,paths",
                "--tag",
                f"source:{source.source_id}",
                *retention_args,
            ],
            catalog=catalog,
            credentials=credentials,
            endpoint=endpoint,
            cache_dir=cache_dir,
        )
    return {
        "source_id": source.source_id,
        "result": "backed_up",
        "host": host_name,
        "files": sum(count_files(path) for path in source.paths),
        "paths": [str(path) for path in source.paths],
        "retention": source.retention,
        "restic_stdout": outcome.stdout.strip(),
        "snapshot_id": snapshot_id_from_backup_stdout(outcome.stdout),
    }


def run_restore_verification(
    *,
    sources: list[Source],
    credentials: dict[str, str],
    endpoint: str,
    cache_dir: Path,
    repo_root: Path,
    restore_dir: Path,
    runtime_state_dir: Path,
    catalog: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    receipts_source = next((source for source in sources if source.source_id == "receipts"), None)
    if receipts_source is None or not receipts_source.restore_verification:
        raise ValueError("restic catalog does not define the receipts source required for restore verification")

    snapshots_result = restic_call(
        ["snapshots", "--json"],
        catalog=catalog,
        credentials=credentials,
        endpoint=endpoint,
        cache_dir=cache_dir,
    )
    snapshots = json.loads(snapshots_result.stdout or "[]")
    if not isinstance(snapshots, list):
        raise ValueError("restic snapshots output must be a list")
    snapshot = snapshot_for_source(receipts_source, snapshots)
    if snapshot is None:
        raise RuntimeError("No restic snapshot exists yet for source receipts.")

    restored_at = utc_now()
    staging_root = runtime_state_dir / "restore-verification" / restored_at.strftime("%Y%m%dT%H%M%SZ")
    ensure_directory(staging_root)
    restore_target = staging_root / "restore"
    ensure_directory(restore_target)

    restic_call(
        ["restore", str(snapshot["id"]), "--target", str(restore_target)],
        catalog=catalog,
        credentials=credentials,
        endpoint=endpoint,
        cache_dir=cache_dir,
    )

    expected_path = restore_target / repo_root.relative_to(repo_root.anchor) / str(
        receipts_source.restore_verification.get("path", "receipts")
    )
    if not expected_path.exists():
        expected_path = restore_target / str(receipts_source.restore_verification.get("path", "receipts"))
    restored_file_count = count_files(expected_path)
    expected_minimum_files = int(receipts_source.restore_verification.get("expected_minimum_files") or 1)
    result = "pass" if restored_file_count >= expected_minimum_files else "fail"

    receipt = {
        "schema_version": "1.0.0",
        "receipt_id": f"restic-restore-verify-{restored_at.strftime('%Y%m%dT%H%M%SZ')}",
        "recorded_at": isoformat(restored_at),
        "recorded_on": restored_at.date().isoformat(),
        "recorded_by": "codex",
        "restored_at": isoformat(restored_at),
        "result": result,
        "source_id": receipts_source.source_id,
        "snapshot_id": str(snapshot.get("id") or ""),
        "snapshot_recorded_at": isoformat(snapshot["_parsed_time"]),
        "restore_path": display_path(expected_path, repo_root=repo_root),
        "restored_file_count": restored_file_count,
        "expected_minimum_files": expected_minimum_files,
    }
    receipt_path = restore_dir / f"{restored_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    write_json(receipt_path, receipt)
    return receipt, receipt_path


def build_backup_receipt(
    *,
    catalog: dict[str, Any],
    source_results: list[dict[str, Any]],
    latest_snapshot_receipt: dict[str, Any],
    latest_snapshot_receipt_path: Path,
    repository_endpoint: str,
    triggered_by: str,
    repo_root: Path,
    source_commit: str,
    notifications: list[dict[str, Any]],
    generated_at: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "receipt_id": f"restic-config-backup-{generated_at.strftime('%Y%m%dT%H%M%SZ')}",
        "recorded_at": isoformat(generated_at),
        "recorded_on": generated_at.date().isoformat(),
        "recorded_by": "codex",
        "triggered_by": triggered_by,
        "source_commit": source_commit,
        "repository": {
            "bucket": catalog["controller_host"]["minio"]["bucket"],
            "endpoint": repository_endpoint,
            "repository_url": restic_repository(catalog, repository_endpoint),
        },
        "summary": latest_snapshot_receipt["summary"],
        "source_results": source_results,
        "latest_snapshot_receipt": display_path(latest_snapshot_receipt_path, repo_root=repo_root),
        "notifications": notifications,
    }


def repo_source_commit(repo_root: Path) -> str:
    if not repo_root.exists():
        return "unknown"
    outcome = run_command(["git", "-C", str(repo_root), "rev-parse", "HEAD"])
    if outcome.returncode != 0:
        return "unknown"
    return outcome.stdout.strip() or "unknown"


def ensure_latest_receipt_dir(path: Path) -> None:
    ensure_directory(path.parent)


@contextlib.contextmanager
def runtime_lock(
    *,
    lock_path: Path,
    mode: str,
    triggered_by: str,
    live_apply_trigger: bool,
    timeout_seconds: int,
    poll_seconds: float = DEFAULT_LOCK_POLL_SECONDS,
) -> Iterator[None]:
    ensure_directory(lock_path.parent)
    lock_file = lock_path.open("a+", encoding="utf-8")
    deadline = time.monotonic() + max(timeout_seconds, 0)
    holder_payload = {
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "mode": mode,
        "triggered_by": triggered_by,
        "live_apply_trigger": live_apply_trigger,
        "started_at": isoformat(utc_now()),
    }
    try:
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                lock_file.seek(0)
                lock_file.truncate()
                lock_file.write(json.dumps(holder_payload, indent=2) + "\n")
                lock_file.flush()
                os.fsync(lock_file.fileno())
                break
            except BlockingIOError:
                lock_file.seek(0)
                active_holder = lock_file.read().strip() or "unknown"
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(
                        "another restic config backup is still running; "
                        f"waited {timeout_seconds} seconds for {lock_path} (holder={active_holder})"
                    )
                time.sleep(min(poll_seconds, remaining))
        yield
    finally:
        try:
            lock_file.seek(0)
            lock_file.truncate()
            lock_file.flush()
        except OSError:
            pass
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            lock_file.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ADR 0302 restic backups for platform configuration artifacts.")
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--backup-receipts-dir", type=Path, default=DEFAULT_BACKUP_RECEIPT_DIR)
    parser.add_argument("--latest-snapshot-receipt", type=Path, default=DEFAULT_LATEST_RECEIPT_PATH)
    parser.add_argument("--restore-verification-dir", type=Path, default=DEFAULT_RESTORE_VERIFY_DIR)
    parser.add_argument("--runtime-state-dir", type=Path, default=DEFAULT_RUNTIME_STATE_DIR)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--credential-file", type=Path)
    parser.add_argument("--mode", choices=["backup", "restore-verify"], default="backup")
    parser.add_argument("--triggered-by", default=DEFAULT_TRIGGER)
    parser.add_argument("--lock-timeout-seconds", type=int, default=DEFAULT_LOCK_TIMEOUT_SECONDS)
    parser.add_argument(
        "--live-apply-trigger",
        action="store_true",
        help="Only back up sources marked trigger_on_live_apply.",
    )
    parser.add_argument(
        "--print-report-json",
        action="store_true",
        help="Emit REPORT_JSON=<json> for wrappers.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        repo_root = args.repo_root
        catalog, raw_sources = load_catalog(args.catalog)
        credentials = load_runtime_credentials(args.credential_file)
        ensure_directory(args.cache_dir)
        ensure_directory(args.runtime_state_dir)
        lock_path = args.runtime_state_dir / DEFAULT_LOCK_FILENAME
        with runtime_lock(
            lock_path=lock_path,
            mode=args.mode,
            triggered_by=args.triggered_by,
            live_apply_trigger=args.live_apply_trigger,
            timeout_seconds=args.lock_timeout_seconds,
        ):
            host_name = str(catalog.get("controller_host", {}).get("inventory_hostname") or "docker-runtime-lv3")
            _, endpoint = resolve_minio_endpoint(catalog)
            ensure_restic_repository(
                catalog=catalog,
                credentials=credentials,
                endpoint=endpoint,
                cache_dir=args.cache_dir,
            )
            resolved_sources = resolve_source_paths(raw_sources, repo_root)

            if args.mode == "restore-verify":
                restore_receipt, restore_receipt_path = run_restore_verification(
                    sources=resolved_sources,
                    credentials=credentials,
                    endpoint=endpoint,
                    cache_dir=args.cache_dir,
                    repo_root=repo_root,
                    restore_dir=args.restore_verification_dir,
                    runtime_state_dir=args.runtime_state_dir,
                    catalog=catalog,
                )
                payload = {
                    "status": "ok" if restore_receipt["result"] == "pass" else "error",
                    "mode": "restore-verify",
                    "result": restore_receipt["result"],
                    "receipt_path": display_path(restore_receipt_path, repo_root=repo_root),
                    "report": restore_receipt,
                }
                print(json.dumps(payload, indent=2))
                if args.print_report_json:
                    print("REPORT_JSON=" + json.dumps(payload, separators=(",", ":")))
                return 0 if restore_receipt["result"] == "pass" else 1

            selected_sources = filter_sources(resolved_sources, only_live_apply=args.live_apply_trigger)
            generated_at = utc_now()
            source_results = [
                backup_source(
                    source,
                    catalog=catalog,
                    credentials=credentials,
                    endpoint=endpoint,
                    cache_dir=args.cache_dir,
                    host_name=host_name,
                )
                for source in selected_sources
            ]
            restic_call(
                ["check", "--read-data-subset=5%"],
                catalog=catalog,
                credentials=credentials,
                endpoint=endpoint,
                cache_dir=args.cache_dir,
            )
            existing_latest_receipt = load_existing_latest_snapshot_receipt(args.latest_snapshot_receipt)
            if args.live_apply_trigger:
                latest_receipt = build_live_apply_latest_snapshot_receipt(
                    existing_receipt=existing_latest_receipt,
                    resolved_sources=resolved_sources,
                    live_apply_sources=selected_sources,
                    source_results=source_results,
                    repo_root=repo_root,
                    endpoint=endpoint,
                    host_name=host_name,
                    generated_at=generated_at,
                    bucket=catalog["controller_host"]["minio"]["bucket"],
                )
                notifications = []
            else:
                latest_receipt = summarize_latest_snapshots(
                    catalog=catalog,
                    sources=resolved_sources,
                    repo_root=repo_root,
                    credentials=credentials,
                    endpoint=endpoint,
                    cache_dir=args.cache_dir,
                    restore_verify_dir=args.restore_verification_dir,
                    generated_at=generated_at,
                )
                notifications = emit_stale_signals(
                    catalog=catalog,
                    credentials=credentials,
                    latest_receipt=latest_receipt,
                    latest_receipt_path=args.latest_snapshot_receipt,
                )
            ensure_latest_receipt_dir(args.latest_snapshot_receipt)
            write_json(args.latest_snapshot_receipt, latest_receipt)
            backup_receipt = build_backup_receipt(
                catalog=catalog,
                source_results=source_results,
                latest_snapshot_receipt=latest_receipt,
                latest_snapshot_receipt_path=args.latest_snapshot_receipt,
                repository_endpoint=endpoint,
                triggered_by=args.triggered_by,
                repo_root=repo_root,
                source_commit=repo_source_commit(repo_root),
                notifications=notifications,
                generated_at=generated_at,
            )
            backup_receipt_path = args.backup_receipts_dir / f"{generated_at.strftime('%Y%m%dT%H%M%SZ')}.json"
            write_json(backup_receipt_path, backup_receipt)
            payload = {
                "status": "ok",
                "mode": "backup",
                "summary": latest_receipt["summary"],
                "receipt_path": display_path(backup_receipt_path, repo_root=repo_root),
                "latest_snapshot_receipt": display_path(args.latest_snapshot_receipt, repo_root=repo_root),
                "report": backup_receipt,
            }
            print(json.dumps(payload, indent=2))
            if args.print_report_json:
                print("REPORT_JSON=" + json.dumps(payload, separators=(",", ":")))
            return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        return emit_cli_error("Restic config backup", exc)


if __name__ == "__main__":
    raise SystemExit(main())
