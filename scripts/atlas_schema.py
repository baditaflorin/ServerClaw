#!/usr/bin/env python3
"""Repo-managed Atlas linting, snapshot, and drift automation."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import shlex
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from scripts.drift_lib import (
        build_guest_ssh_tunnel_command,
        load_controller_context,
        reserve_local_port,
        resolve_nats_credentials,
        resolve_repo_local_path,
        wait_for_tunnel,
    )
except ModuleNotFoundError as exc:
    if exc.name != "yaml" or os.environ.get("LV3_ATLAS_PYYAML_BOOTSTRAPPED") == "1":
        raise
    helper_path = Path(__file__).resolve().with_name("run_python_with_packages.sh")
    if not helper_path.is_file():
        raise
    os.environ["LV3_ATLAS_PYYAML_BOOTSTRAPPED"] = "1"
    os.execv(
        str(helper_path),
        [str(helper_path), "pyyaml", "--", str(Path(__file__).resolve()), *sys.argv[1:]],
    )

from controller_automation_toolkit import emit_cli_error, load_json, repo_path, write_json
from platform.events.publisher import publish_nats_events


REPO_ROOT = repo_path()
DEFAULT_CATALOG = repo_path("config", "atlas", "catalog.json")
SUPPORTED_SCHEMA_VERSION = "1.0.0"
DEFAULT_DRIFT_EXIT_CODE = 2
DEFAULT_OPERATION_TIMEOUT_SECONDS = 120
DEFAULT_DEV_POSTGRES_WAIT_SECONDS = 30


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def require_int(value: Any, path: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    if value < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    return value


def ensure_repo_root_on_host(repo_root: Path) -> Path:
    override = os.environ.get("LV3_HOST_WORKSPACE", "").strip()
    return Path(override).resolve() if override else repo_root.resolve()


def load_catalog(catalog_path: Path) -> dict[str, Any]:
    catalog = load_json(catalog_path)
    return require_mapping(catalog, str(catalog_path))


def validate_catalog(catalog: dict[str, Any], *, repo_root: Path) -> None:
    if catalog.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"config/atlas/catalog.json.schema_version must be '{SUPPORTED_SCHEMA_VERSION}'"
        )

    require_str(catalog.get("atlas_image_ref"), "config/atlas/catalog.json.atlas_image_ref")
    require_str(catalog.get("dev_postgres_image"), "config/atlas/catalog.json.dev_postgres_image")

    runtime = require_mapping(catalog.get("runtime"), "config/atlas/catalog.json.runtime")
    require_str(runtime.get("openbao_guest"), "config/atlas/catalog.json.runtime.openbao_guest")
    require_str(runtime.get("openbao_url"), "config/atlas/catalog.json.runtime.openbao_url")
    require_str(runtime.get("postgres_guest"), "config/atlas/catalog.json.runtime.postgres_guest")
    require_int(runtime.get("postgres_port"), "config/atlas/catalog.json.runtime.postgres_port")

    openbao = require_mapping(catalog.get("openbao"), "config/atlas/catalog.json.openbao")
    require_str(
        openbao.get("approle_secret_id"),
        "config/atlas/catalog.json.openbao.approle_secret_id",
    )
    require_str(
        openbao.get("database_role"),
        "config/atlas/catalog.json.openbao.database_role",
    )

    receipts = require_mapping(catalog.get("receipts"), "config/atlas/catalog.json.receipts")
    drift_dir = require_str(
        receipts.get("drift_dir"),
        "config/atlas/catalog.json.receipts.drift_dir",
    )
    if not drift_dir.startswith("receipts/"):
        raise ValueError("config/atlas/catalog.json.receipts.drift_dir must live under receipts/")

    notifications = require_mapping(
        catalog.get("notifications"),
        "config/atlas/catalog.json.notifications",
    )
    require_str(
        notifications.get("nats_subject"),
        "config/atlas/catalog.json.notifications.nats_subject",
    )
    ntfy = require_mapping(
        notifications.get("ntfy"),
        "config/atlas/catalog.json.notifications.ntfy",
    )
    require_str(ntfy.get("url"), "config/atlas/catalog.json.notifications.ntfy.url")
    require_str(
        ntfy.get("username"),
        "config/atlas/catalog.json.notifications.ntfy.username",
    )
    require_str(
        ntfy.get("password_secret_id"),
        "config/atlas/catalog.json.notifications.ntfy.password_secret_id",
    )

    lint_targets = require_list(
        catalog.get("lint_targets"),
        "config/atlas/catalog.json.lint_targets",
    )
    if not lint_targets:
        raise ValueError("config/atlas/catalog.json.lint_targets must not be empty")
    lint_ids: set[str] = set()
    for index, target in enumerate(lint_targets):
        target_path = f"config/atlas/catalog.json.lint_targets[{index}]"
        target = require_mapping(target, target_path)
        lint_id = require_str(target.get("id"), f"{target_path}.id")
        if lint_id in lint_ids:
            raise ValueError(f"duplicate Atlas lint target id '{lint_id}'")
        lint_ids.add(lint_id)
        directory = require_str(target.get("path"), f"{target_path}.path")
        if not repo_root.joinpath(directory).is_dir():
            raise ValueError(f"{target_path}.path references missing directory '{directory}'")
        require_str(target.get("dev_database"), f"{target_path}.dev_database")
        triggers = require_list(target.get("triggers"), f"{target_path}.triggers")
        if not triggers:
            raise ValueError(f"{target_path}.triggers must not be empty")
        for trigger_index, trigger in enumerate(triggers):
            require_str(trigger, f"{target_path}.triggers[{trigger_index}]")

    databases = require_list(catalog.get("databases"), "config/atlas/catalog.json.databases")
    if not databases:
        raise ValueError("config/atlas/catalog.json.databases must not be empty")
    database_ids: set[str] = set()
    snapshot_paths: set[str] = set()
    for index, entry in enumerate(databases):
        entry_path = f"config/atlas/catalog.json.databases[{index}]"
        entry = require_mapping(entry, entry_path)
        database_id = require_str(entry.get("id"), f"{entry_path}.id")
        if database_id in database_ids:
            raise ValueError(f"duplicate Atlas database id '{database_id}'")
        database_ids.add(database_id)
        require_str(entry.get("database"), f"{entry_path}.database")
        snapshot_path = require_str(entry.get("snapshot_path"), f"{entry_path}.snapshot_path")
        if snapshot_path in snapshot_paths:
            raise ValueError(f"duplicate Atlas snapshot path '{snapshot_path}'")
        snapshot_paths.add(snapshot_path)
        snapshot_file = repo_root / snapshot_path
        if not snapshot_file.is_file():
            raise ValueError(f"{entry_path}.snapshot_path references missing file '{snapshot_path}'")
        if not snapshot_file.read_text(encoding="utf-8").strip():
            raise ValueError(f"{entry_path}.snapshot_path must not be empty")


def parse_changed_files() -> tuple[str, ...] | None:
    raw_payload = os.environ.get("LV3_VALIDATION_CHANGED_FILES_JSON", "").strip()
    if not raw_payload:
        return None
    payload = json.loads(raw_payload)
    if not isinstance(payload, list):
        raise ValueError("LV3_VALIDATION_CHANGED_FILES_JSON must be a JSON array")
    changed_files: list[str] = []
    for index, item in enumerate(payload):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                f"LV3_VALIDATION_CHANGED_FILES_JSON[{index}] must be a non-empty string"
            )
        changed_files.append(item.strip())
    return tuple(changed_files)


def select_lint_targets(
    catalog: dict[str, Any],
    *,
    changed_files: tuple[str, ...] | None,
    explicit_target_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    targets = require_list(catalog.get("lint_targets"), "config/atlas/catalog.json.lint_targets")
    if explicit_target_ids:
        target_map = {
            require_str(target.get("id"), "config/atlas/catalog.json.lint_targets[].id"): require_mapping(
                target,
                "config/atlas/catalog.json.lint_targets[]",
            )
            for target in targets
        }
        missing = [target_id for target_id in explicit_target_ids if target_id not in target_map]
        if missing:
            raise ValueError(f"unknown Atlas lint target(s): {', '.join(missing)}")
        return [target_map[target_id] for target_id in explicit_target_ids]

    if not changed_files:
        return [require_mapping(target, "config/atlas/catalog.json.lint_targets[]") for target in targets]

    selected: list[dict[str, Any]] = []
    for target in targets:
        target = require_mapping(target, "config/atlas/catalog.json.lint_targets[]")
        triggers = [
            require_str(trigger, "config/atlas/catalog.json.lint_targets[].triggers[]")
            for trigger in require_list(target.get("triggers"), "config/atlas/catalog.json.lint_targets[].triggers")
        ]
        if any(any(path == trigger or path.startswith(trigger) for trigger in triggers) for path in changed_files):
            selected.append(target)
    return selected


def normalize_snapshot(content: str) -> str:
    return content.strip() + "\n"


def hash_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def decode_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return value.strip()


def load_docker_sdk():
    repo_root = REPO_ROOT.resolve()
    original = list(sys.path)
    filtered: list[str] = []
    for entry in original:
        resolved = repo_root if entry == "" else Path(entry).resolve()
        if resolved == repo_root:
            continue
        filtered.append(entry)
    sys.path[:] = filtered
    try:
        import docker as docker_sdk  # type: ignore[import-not-found]
    finally:
        sys.path[:] = original
    return docker_sdk


def ensure_image(client: Any, image_ref: str) -> None:
    try:
        client.images.get(image_ref)
        return
    except Exception:  # noqa: BLE001
        client.images.pull(image_ref)


def run_atlas(
    client: Any,
    *,
    image_ref: str,
    command: list[str],
    host_repo_root: Path | None = None,
) -> str:
    docker_sdk = load_docker_sdk()
    ensure_image(client, image_ref)
    volumes: dict[str, dict[str, str]] = {}
    working_dir = None
    if host_repo_root is not None:
        volumes[str(host_repo_root)] = {"bind": "/workspace", "mode": "ro"}
        working_dir = "/workspace"
    try:
        output = client.containers.run(
            image_ref,
            command=command,
            remove=True,
            detach=False,
            stderr=True,
            stdout=True,
            working_dir=working_dir,
            volumes=volumes or None,
            extra_hosts={"host.docker.internal": "host-gateway"},
        )
    except docker_sdk.errors.ContainerError as exc:  # type: ignore[attr-defined]
        stderr = decode_output(getattr(exc, "stderr", None))
        raise RuntimeError(
            f"Atlas command failed ({' '.join(command)}): {stderr or str(exc)}"
        ) from exc
    except docker_sdk.errors.APIError as exc:  # type: ignore[attr-defined]
        raise RuntimeError(f"Atlas container API error: {exc}") from exc
    return decode_output(output)


@contextmanager
def guest_tunnel(context: dict[str, Any], guest_name: str, *, remote_bind: str):
    local_port = reserve_local_port()
    command = build_guest_ssh_tunnel_command(
        context,
        guest_name,
        local_bind=f"127.0.0.1:{local_port}",
        remote_bind=remote_bind,
    )
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        wait_for_tunnel(process, local_port)
        yield local_port
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


def host_reachable(host: str, port: int, *, timeout_seconds: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def http_reachable(url: str, *, timeout_seconds: float = 2.0) -> bool:
    request = urllib.request.Request(url.rstrip("/") + "/v1/sys/health", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds):
            return True
    except urllib.error.HTTPError:
        return True
    except urllib.error.URLError:
        return False


@contextmanager
def resolve_openbao_url(catalog: dict[str, Any], context: dict[str, Any]):
    runtime = require_mapping(catalog.get("runtime"), "config/atlas/catalog.json.runtime")
    openbao_url = require_str(runtime.get("openbao_url"), "config/atlas/catalog.json.runtime.openbao_url")
    if http_reachable(openbao_url):
        yield openbao_url
        return

    guest_name = require_str(runtime.get("openbao_guest"), "config/atlas/catalog.json.runtime.openbao_guest")
    with guest_tunnel(context, guest_name, remote_bind="127.0.0.1:8201") as local_port:
        yield f"http://127.0.0.1:{local_port}"


@contextmanager
def resolve_postgres_endpoint(catalog: dict[str, Any], context: dict[str, Any]):
    runtime = require_mapping(catalog.get("runtime"), "config/atlas/catalog.json.runtime")
    guest_name = require_str(runtime.get("postgres_guest"), "config/atlas/catalog.json.runtime.postgres_guest")
    postgres_port = require_int(
        runtime.get("postgres_port"),
        "config/atlas/catalog.json.runtime.postgres_port",
    )
    guest_host = context["guests"][guest_name]
    if host_reachable(guest_host, postgres_port):
        yield guest_host, postgres_port
        return

    with guest_tunnel(context, guest_name, remote_bind=f"127.0.0.1:{postgres_port}") as local_port:
        yield "host.docker.internal", local_port


def controller_secret_path(context: dict[str, Any], secret_id: str) -> Path:
    manifest = require_mapping(
        context.get("secret_manifest"),
        "controller-local secret manifest",
    )
    secrets = require_mapping(manifest.get("secrets"), "controller-local secret manifest.secrets")
    secret = require_mapping(secrets.get(secret_id), f"controller-local secret manifest.secrets.{secret_id}")
    if secret.get("kind") != "file":
        raise ValueError(f"secret '{secret_id}' must use the file storage contract")
    return resolve_repo_local_path(require_str(secret.get("path"), f"secret {secret_id}.path"))


def openbao_login(context: dict[str, Any], base_url: str, catalog: dict[str, Any]) -> str:
    openbao = require_mapping(catalog.get("openbao"), "config/atlas/catalog.json.openbao")
    approle_secret_id = require_str(
        openbao.get("approle_secret_id"),
        "config/atlas/catalog.json.openbao.approle_secret_id",
    )
    approle_file = controller_secret_path(context, approle_secret_id)
    if not approle_file.exists():
        raise ValueError(
            f"OpenBao Atlas AppRole artifact is missing at {approle_file}. "
            "Converge OpenBao first so the repo-managed AppRole file exists."
        )
    approle = require_mapping(load_json(approle_file), str(approle_file))
    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/auth/approle/login",
        data=json.dumps(
            {
                "role_id": require_str(approle.get("role_id"), f"{approle_file}.role_id"),
                "secret_id": require_str(approle.get("secret_id"), f"{approle_file}.secret_id"),
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    auth = require_mapping(payload.get("auth"), "OpenBao AppRole login response.auth")
    return require_str(auth.get("client_token"), "OpenBao AppRole login response.auth.client_token")


def request_dynamic_credentials(
    base_url: str,
    *,
    token: str,
    role_name: str,
) -> dict[str, str]:
    request = urllib.request.Request(
        base_url.rstrip("/") + f"/v1/database/creds/{role_name}",
        headers={"X-Vault-Token": token},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = require_mapping(payload.get("data"), "OpenBao dynamic credential response.data")
    return {
        "username": require_str(data.get("username"), "OpenBao dynamic credential username"),
        "password": require_str(data.get("password"), "OpenBao dynamic credential password"),
    }


def postgres_url(*, host: str, port: int, database: str, username: str, password: str) -> str:
    return (
        "postgres://"
        f"{urllib.parse.quote(username, safe='')}:"
        f"{urllib.parse.quote(password, safe='')}"
        f"@{host}:{port}/{database}?sslmode=disable"
    )


@contextmanager
def dev_postgres(client: Any, image_ref: str, database_name: str):
    ensure_image(client, image_ref)
    container_name = f"atlas-lint-{os.getpid()}-{reserve_local_port()}"
    local_port = reserve_local_port()
    container = client.containers.run(
        image_ref,
        detach=True,
        remove=True,
        name=container_name,
        environment={
            "POSTGRES_PASSWORD": "postgres",
            "POSTGRES_DB": database_name,
        },
        ports={"5432/tcp": ("127.0.0.1", local_port)},
    )
    try:
        deadline = time.time() + DEFAULT_DEV_POSTGRES_WAIT_SECONDS
        last_output = ""
        while time.time() < deadline:
            result = container.exec_run(["pg_isready", "-U", "postgres", "-d", database_name])
            if result.exit_code == 0:
                yield {
                    "host": "host.docker.internal",
                    "port": local_port,
                    "database": database_name,
                    "username": "postgres",
                    "password": "postgres",
                }
                return
            last_output = decode_output(result.output)
            time.sleep(1)
        raise RuntimeError(
            f"ephemeral PostgreSQL dev database did not become ready: {last_output or 'timeout'}"
        )
    finally:
        try:
            container.stop(timeout=3)
        except Exception:  # noqa: BLE001
            pass


def inspect_live_schema(
    client: Any,
    *,
    atlas_image_ref: str,
    database_url: str,
) -> str:
    output = run_atlas(
        client,
        image_ref=atlas_image_ref,
        command=[
            "schema",
            "inspect",
            "--url",
            database_url,
            "--format",
            "{{ hcl . }}",
        ],
    )
    return normalize_snapshot(output)


def lint_target(
    client: Any,
    *,
    atlas_image_ref: str,
    dev_postgres_image: str,
    host_repo_root: Path,
    target: dict[str, Any],
) -> dict[str, Any]:
    target_id = require_str(target.get("id"), "Atlas lint target id")
    migrations_path = require_str(target.get("path"), "Atlas lint target path")
    dev_database = require_str(target.get("dev_database"), "Atlas lint target dev_database")
    with dev_postgres(client, dev_postgres_image, dev_database) as dev_db:
        dev_url = postgres_url(
            host=dev_db["host"],
            port=dev_db["port"],
            database=dev_db["database"],
            username=dev_db["username"],
            password=dev_db["password"],
        )
        run_atlas(
            client,
            image_ref=atlas_image_ref,
            host_repo_root=host_repo_root,
            command=[
                "migrate",
                "lint",
                "--dir",
                f"file:///workspace/{migrations_path}",
                "--dev-url",
                dev_url,
            ],
        )
    return {
        "target_id": target_id,
        "path": migrations_path,
        "status": "passed",
    }


def diff_preview(snapshot_content: str, live_content: str, *, label: str) -> list[str]:
    diff = list(
        difflib.unified_diff(
            snapshot_content.splitlines(),
            live_content.splitlines(),
            fromfile=f"{label}-snapshot",
            tofile=f"{label}-live",
            lineterm="",
        )
    )
    if len(diff) > 200:
        return diff[:200] + ["... diff truncated ..."]
    return diff


def maybe_publish_drift_events(
    *,
    subject: str,
    records: list[dict[str, Any]],
    context: dict[str, Any],
) -> dict[str, Any]:
    if not records:
        return {"published": False, "count": 0}
    credentials = resolve_nats_credentials(context)
    nats_url = os.environ.get("LV3_NATS_URL", "").strip()
    if nats_url:
        publish_nats_events(records, nats_url=nats_url, credentials=credentials)
        return {"published": True, "count": len(records), "url": nats_url}

    with guest_tunnel(context, "docker-runtime-lv3", remote_bind="127.0.0.1:4222") as local_port:
        tunnel_url = f"nats://127.0.0.1:{local_port}"
        publish_nats_events(records, nats_url=tunnel_url, credentials=credentials)
        return {"published": True, "count": len(records), "url": tunnel_url, "tunneled": True}


def maybe_publish_ntfy(
    *,
    catalog: dict[str, Any],
    context: dict[str, Any],
    drifted_ids: list[str],
) -> dict[str, Any]:
    if not drifted_ids:
        return {"published": False, "count": 0}

    notifications = require_mapping(
        catalog.get("notifications"),
        "config/atlas/catalog.json.notifications",
    )
    ntfy = require_mapping(ntfy := notifications.get("ntfy"), "config/atlas/catalog.json.notifications.ntfy")
    url = require_str(ntfy.get("url"), "config/atlas/catalog.json.notifications.ntfy.url")
    username = require_str(ntfy.get("username"), "config/atlas/catalog.json.notifications.ntfy.username")
    password_path = controller_secret_path(
        context,
        require_str(
            ntfy.get("password_secret_id"),
            "config/atlas/catalog.json.notifications.ntfy.password_secret_id",
        ),
    )
    if not password_path.exists():
        return {
            "published": False,
            "count": 0,
            "reason": f"ntfy password file missing at {password_path}",
        }

    password = password_path.read_text(encoding="utf-8").strip()
    token = urllib.parse.quote(f"{username}:{password}", safe="")
    request = urllib.request.Request(
        url,
        data=(
            "Atlas drift detected for database snapshots: " + ", ".join(sorted(drifted_ids))
        ).encode("utf-8"),
        headers={
            "Authorization": "Basic "
            + urllib.parse.quote_from_bytes(f"{username}:{password}".encode("utf-8"), safe=""),
            "Title": "Atlas drift detected",
            "Priority": "high",
            "Tags": "warning,atlas,postgres",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status >= 300:
                raise RuntimeError(f"ntfy publish failed with HTTP {response.status}")
    except Exception as exc:  # noqa: BLE001
        return {"published": False, "count": 0, "reason": str(exc), "auth_token_length": len(token)}
    return {"published": True, "count": len(drifted_ids)}


def run_validate(*, repo_root: Path, catalog_path: Path) -> dict[str, Any]:
    catalog = load_catalog(catalog_path)
    validate_catalog(catalog, repo_root=repo_root)
    return {
        "status": "ok",
        "catalog_path": str(catalog_path),
        "database_count": len(catalog["databases"]),
        "lint_target_count": len(catalog["lint_targets"]),
    }


def run_lint(
    *,
    repo_root: Path,
    catalog_path: Path,
    target_ids: tuple[str, ...],
) -> tuple[int, dict[str, Any]]:
    catalog = load_catalog(catalog_path)
    validate_catalog(catalog, repo_root=repo_root)
    changed_files = parse_changed_files()
    selected_targets = select_lint_targets(
        catalog,
        changed_files=changed_files,
        explicit_target_ids=target_ids,
    )
    if not selected_targets:
        return 0, {
            "status": "skipped",
            "catalog_path": str(catalog_path),
            "reason": "no Atlas-managed migration surfaces changed",
            "changed_files": list(changed_files or ()),
        }

    docker_sdk = load_docker_sdk()
    client = docker_sdk.from_env()
    atlas_image_ref = require_str(catalog.get("atlas_image_ref"), "config/atlas/catalog.json.atlas_image_ref")
    dev_postgres_image = require_str(
        catalog.get("dev_postgres_image"),
        "config/atlas/catalog.json.dev_postgres_image",
    )
    host_repo_root = ensure_repo_root_on_host(repo_root)
    results = [
        lint_target(
            client,
            atlas_image_ref=atlas_image_ref,
            dev_postgres_image=dev_postgres_image,
            host_repo_root=host_repo_root,
            target=target,
        )
        for target in selected_targets
    ]
    return 0, {
        "status": "ok",
        "catalog_path": str(catalog_path),
        "selected_targets": [entry["target_id"] for entry in results],
        "results": results,
        "changed_files": list(changed_files or ()),
    }


def run_snapshot(
    *,
    repo_root: Path,
    catalog_path: Path,
    database_ids: tuple[str, ...],
    write: bool,
) -> tuple[int, dict[str, Any]]:
    catalog = load_catalog(catalog_path)
    validate_catalog(catalog, repo_root=repo_root)
    selected_ids = set(database_ids)
    databases = [
        require_mapping(entry, "config/atlas/catalog.json.databases[]")
        for entry in require_list(catalog.get("databases"), "config/atlas/catalog.json.databases")
        if not selected_ids or require_str(entry.get("id"), "Atlas database id") in selected_ids
    ]
    if selected_ids and len(databases) != len(selected_ids):
        found = {require_str(entry.get("id"), "Atlas database id") for entry in databases}
        missing = sorted(selected_ids - found)
        raise ValueError(f"unknown Atlas database id(s): {', '.join(missing)}")

    docker_sdk = load_docker_sdk()
    client = docker_sdk.from_env()
    context = load_controller_context()
    atlas_image_ref = require_str(catalog.get("atlas_image_ref"), "config/atlas/catalog.json.atlas_image_ref")
    openbao = require_mapping(catalog.get("openbao"), "config/atlas/catalog.json.openbao")
    database_role = require_str(openbao.get("database_role"), "config/atlas/catalog.json.openbao.database_role")
    snapshot_results: list[dict[str, Any]] = []

    with resolve_openbao_url(catalog, context) as openbao_url:
        token = openbao_login(context, openbao_url, catalog)
        credentials = request_dynamic_credentials(openbao_url, token=token, role_name=database_role)
        with resolve_postgres_endpoint(catalog, context) as (postgres_host, postgres_port):
            for entry in databases:
                database_id = require_str(entry.get("id"), "Atlas database id")
                database_name = require_str(entry.get("database"), f"Atlas database {database_id}.database")
                snapshot_path = repo_root / require_str(
                    entry.get("snapshot_path"),
                    f"Atlas database {database_id}.snapshot_path",
                )
                schema = inspect_live_schema(
                    client,
                    atlas_image_ref=atlas_image_ref,
                    database_url=postgres_url(
                        host=postgres_host,
                        port=postgres_port,
                        database=database_name,
                        username=credentials["username"],
                        password=credentials["password"],
                    ),
                )
                if write:
                    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
                    snapshot_path.write_text(schema, encoding="utf-8")
                snapshot_results.append(
                    {
                        "database_id": database_id,
                        "database": database_name,
                        "snapshot_path": str(snapshot_path.relative_to(repo_root)),
                        "written": write,
                        "sha256": hash_text(schema),
                    }
                )
    return 0, {
        "status": "ok",
        "catalog_path": str(catalog_path),
        "write": write,
        "snapshots": snapshot_results,
    }


def run_drift(
    *,
    repo_root: Path,
    catalog_path: Path,
    write_receipts: bool,
    publish_nats: bool,
    publish_ntfy: bool,
) -> tuple[int, dict[str, Any]]:
    catalog = load_catalog(catalog_path)
    validate_catalog(catalog, repo_root=repo_root)
    docker_sdk = load_docker_sdk()
    client = docker_sdk.from_env()
    context = load_controller_context()
    atlas_image_ref = require_str(catalog.get("atlas_image_ref"), "config/atlas/catalog.json.atlas_image_ref")
    openbao = require_mapping(catalog.get("openbao"), "config/atlas/catalog.json.openbao")
    database_role = require_str(openbao.get("database_role"), "config/atlas/catalog.json.openbao.database_role")
    receipt_dir = repo_root / require_str(
        require_mapping(catalog.get("receipts"), "config/atlas/catalog.json.receipts").get("drift_dir"),
        "config/atlas/catalog.json.receipts.drift_dir",
    )
    receipt_dir.mkdir(parents=True, exist_ok=True)

    checked: list[dict[str, Any]] = []
    drifted: list[dict[str, Any]] = []
    event_records: list[dict[str, Any]] = []
    receipt_paths: list[str] = []
    with resolve_openbao_url(catalog, context) as openbao_url:
        token = openbao_login(context, openbao_url, catalog)
        credentials = request_dynamic_credentials(openbao_url, token=token, role_name=database_role)
        with resolve_postgres_endpoint(catalog, context) as (postgres_host, postgres_port):
            for entry in require_list(catalog.get("databases"), "config/atlas/catalog.json.databases"):
                entry = require_mapping(entry, "config/atlas/catalog.json.databases[]")
                database_id = require_str(entry.get("id"), "Atlas database id")
                database_name = require_str(entry.get("database"), f"Atlas database {database_id}.database")
                snapshot_path = repo_root / require_str(
                    entry.get("snapshot_path"),
                    f"Atlas database {database_id}.snapshot_path",
                )
                snapshot_content = normalize_snapshot(snapshot_path.read_text(encoding="utf-8"))
                live_content = inspect_live_schema(
                    client,
                    atlas_image_ref=atlas_image_ref,
                    database_url=postgres_url(
                        host=postgres_host,
                        port=postgres_port,
                        database=database_name,
                        username=credentials["username"],
                        password=credentials["password"],
                    ),
                )
                checked.append(
                    {
                        "database_id": database_id,
                        "database": database_name,
                        "snapshot_path": str(snapshot_path.relative_to(repo_root)),
                        "snapshot_sha256": hash_text(snapshot_content),
                        "live_sha256": hash_text(live_content),
                    }
                )
                if live_content == snapshot_content:
                    continue

                record = {
                    "schema_version": SUPPORTED_SCHEMA_VERSION,
                    "workflow_id": "atlas-drift-check",
                    "database_id": database_id,
                    "database": database_name,
                    "detected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "severity": "warning",
                    "status": "drift_detected",
                    "snapshot_path": str(snapshot_path.relative_to(repo_root)),
                    "snapshot_sha256": hash_text(snapshot_content),
                    "live_sha256": hash_text(live_content),
                    "diff_preview": diff_preview(snapshot_content, live_content, label=database_id),
                }
                drifted.append(record)
                if write_receipts:
                    receipt_path = receipt_dir / f"{database_id}-{time.strftime('%Y-%m-%d', time.gmtime())}.json"
                    write_json(receipt_path, record, indent=2, sort_keys=True)
                    receipt_paths.append(str(receipt_path.relative_to(repo_root)))
                event_records.append(
                    {
                        "subject": require_str(
                            require_mapping(
                                catalog.get("notifications"),
                                "config/atlas/catalog.json.notifications",
                            ).get("nats_subject"),
                            "config/atlas/catalog.json.notifications.nats_subject",
                        ),
                        "generated_at": record["detected_at"],
                        "payload": {
                            "database_id": database_id,
                            "database": database_name,
                            "severity": record["severity"],
                            "snapshot_path": record["snapshot_path"],
                            "snapshot_sha256": record["snapshot_sha256"],
                            "live_sha256": record["live_sha256"],
                        },
                    }
                )

    nats_result = {"published": False, "count": 0}
    if publish_nats and event_records:
        nats_result = maybe_publish_drift_events(
            subject=require_str(
                require_mapping(catalog.get("notifications"), "config/atlas/catalog.json.notifications").get("nats_subject"),
                "config/atlas/catalog.json.notifications.nats_subject",
            ),
            records=event_records,
            context=context,
        )

    ntfy_result = {"published": False, "count": 0}
    if publish_ntfy and drifted:
        ntfy_result = maybe_publish_ntfy(
            catalog=catalog,
            context=context,
            drifted_ids=[record["database_id"] for record in drifted],
        )

    status = "clean" if not drifted else "drift_detected"
    payload = {
        "status": status,
        "catalog_path": str(catalog_path),
        "checked_databases": checked,
        "drifted_databases": drifted,
        "drift_count": len(drifted),
        "receipt_paths": receipt_paths,
        "notifications": {
            "nats": nats_result,
            "ntfy": ntfy_result,
        },
    }
    return (0 if not drifted else DEFAULT_DRIFT_EXIT_CODE), payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run repo-managed Atlas schema automation.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root that owns the Atlas catalog and snapshots.",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_CATALOG,
        help="Path to the Atlas catalog JSON file.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="Output format.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate", help="Validate the Atlas catalog and committed snapshots.")

    lint_parser = subparsers.add_parser("lint", help="Run Atlas migrate lint for repo-managed migrations.")
    lint_parser.add_argument(
        "--target-id",
        action="append",
        default=[],
        help="Specific lint target id to run. Defaults to changed-only auto-selection or all targets.",
    )

    snapshot_parser = subparsers.add_parser(
        "snapshot",
        help="Inspect live PostgreSQL schemas and optionally rewrite committed Atlas HCL snapshots.",
    )
    snapshot_parser.add_argument(
        "--database-id",
        action="append",
        default=[],
        help="Specific database id to snapshot. Defaults to all Atlas-managed databases.",
    )
    snapshot_parser.add_argument(
        "--write",
        action="store_true",
        help="Rewrite the committed snapshot files in place.",
    )

    drift_parser = subparsers.add_parser(
        "drift",
        help="Compare live PostgreSQL schemas with committed Atlas HCL snapshots.",
    )
    drift_parser.add_argument(
        "--write-receipts",
        action="store_true",
        help="Write per-database drift receipts under receipts/atlas-drift when drift is found.",
    )
    drift_parser.add_argument(
        "--publish-nats",
        action="store_true",
        help="Publish platform.db.schema_drift events for drifted databases.",
    )
    drift_parser.add_argument(
        "--publish-ntfy",
        action="store_true",
        help="Publish one ntfy warning when drifted databases are detected.",
    )

    return parser


def print_text_payload(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    catalog_path = args.catalog.resolve()
    try:
        if args.command == "validate":
            exit_code, payload = 0, run_validate(repo_root=repo_root, catalog_path=catalog_path)
        elif args.command == "lint":
            exit_code, payload = run_lint(
                repo_root=repo_root,
                catalog_path=catalog_path,
                target_ids=tuple(args.target_id),
            )
        elif args.command == "snapshot":
            exit_code, payload = run_snapshot(
                repo_root=repo_root,
                catalog_path=catalog_path,
                database_ids=tuple(args.database_id),
                write=args.write,
            )
        elif args.command == "drift":
            exit_code, payload = run_drift(
                repo_root=repo_root,
                catalog_path=catalog_path,
                write_receipts=args.write_receipts,
                publish_nats=args.publish_nats,
                publish_ntfy=args.publish_ntfy,
            )
        else:
            raise ValueError(f"unsupported Atlas command '{args.command}'")

        if args.format == "json":
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print_text_payload(payload)
        return exit_code
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError, RuntimeError) as exc:
        return emit_cli_error("Atlas schema automation", exc)


if __name__ == "__main__":
    raise SystemExit(main())
