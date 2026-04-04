#!/usr/bin/env python3
"""Build, publish, verify, and stage anonymized seed-data snapshots."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import secrets
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, repo_path, resolve_repo_local_path, write_json


SEED_CATALOG_PATH = repo_path("config", "seed-data-catalog.json")
CONTROLLER_SECRETS_PATH = repo_path("config", "controller-local-secrets.json")
SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")
WORKFLOW_CATALOG_PATH = repo_path("config", "workflow-catalog.json")


def catalog_repo_root() -> Path:
    return SEED_CATALOG_PATH.parent.parent


def _load_drift_helpers():
    from drift_lib import build_guest_ssh_command, load_controller_context, run_command

    return build_guest_ssh_command, load_controller_context, run_command


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    path = path or SEED_CATALOG_PATH
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Seed catalog must be an object: {path}")
    classes = payload.get("classes")
    if not isinstance(classes, dict) or not classes:
        raise ValueError(f"{path} must define at least one seed class")
    return payload


def seed_classes(catalog: dict[str, Any] | None = None) -> list[str]:
    active_catalog = catalog or load_catalog()
    return sorted(str(name) for name in active_catalog["classes"].keys())


def require_seed_class(seed_class: str, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    active_catalog = catalog or load_catalog()
    classes = active_catalog["classes"]
    if seed_class not in classes:
        raise ValueError(f"Unknown seed class '{seed_class}'")
    payload = classes[seed_class]
    if not isinstance(payload, dict):
        raise ValueError(f"Seed class '{seed_class}' must be an object")
    datasets = payload.get("datasets")
    if not isinstance(datasets, dict) or not datasets:
        raise ValueError(f"Seed class '{seed_class}' must define dataset counts")
    return payload


def load_controller_secret_manifest(path: Path | None = None) -> dict[str, Any]:
    path = path or CONTROLLER_SECRETS_PATH
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Controller secret manifest must be an object: {path}")
    secrets_map = payload.get("secrets")
    if not isinstance(secrets_map, dict):
        raise ValueError(f"{path} must define a 'secrets' object")
    return payload


def anonymization_secret_path(catalog: dict[str, Any] | None = None) -> Path:
    active_catalog = catalog or load_catalog()
    secret_id = str(active_catalog["controller_secret_id"])
    manifest = load_controller_secret_manifest()
    secret_entry = manifest["secrets"].get(secret_id)
    if not isinstance(secret_entry, dict):
        raise ValueError(f"Unknown controller secret '{secret_id}' in {CONTROLLER_SECRETS_PATH}")
    if str(secret_entry.get("kind")) != "file":
        raise ValueError(f"Controller secret '{secret_id}' must use kind=file")
    return resolve_repo_local_path(str(secret_entry["path"]), repo_root=catalog_repo_root())


def ensure_anonymization_secret(catalog: dict[str, Any] | None = None) -> str:
    path = anonymization_secret_path(catalog)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(secrets.token_hex(32) + "\n", encoding="utf-8")
        path.chmod(0o600)
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"Anonymization secret is empty: {path}")
    return value


def local_snapshot_root(catalog: dict[str, Any] | None = None) -> Path:
    active_catalog = catalog or load_catalog()
    return catalog_repo_root().joinpath(*Path(str(active_catalog["local_snapshot_root"])).parts)


def guest_stage_root(catalog: dict[str, Any] | None = None) -> str:
    active_catalog = catalog or load_catalog()
    return str(active_catalog["guest_stage_root"])


def service_catalog_summary() -> dict[str, Any]:
    payload = load_json(SERVICE_CATALOG_PATH)
    services = payload.get("services", [])
    if not isinstance(services, list):
        raise ValueError(f"{SERVICE_CATALOG_PATH} must define a services list")
    public_count = 0
    for service in services:
        if not isinstance(service, dict):
            continue
        public_url = service.get("public_url")
        if isinstance(public_url, str) and public_url.strip():
            public_count += 1
    return {
        "service_count": len([service for service in services if isinstance(service, dict)]),
        "public_service_count": public_count,
    }


def workflow_catalog_summary() -> dict[str, Any]:
    payload = load_json(WORKFLOW_CATALOG_PATH)
    workflows = payload.get("workflows", {})
    if not isinstance(workflows, dict):
        raise ValueError(f"{WORKFLOW_CATALOG_PATH} must define a workflows object")
    return {"workflow_count": len(workflows)}


def collect_live_observations(catalog: dict[str, Any]) -> dict[str, Any]:
    observations: dict[str, Any] = {
        "service_catalog": service_catalog_summary(),
        "workflow_catalog": workflow_catalog_summary(),
        "postgres": {"status": "unavailable", "databases": []},
    }
    build_guest_ssh_command, load_controller_context, run_command = _load_drift_helpers()
    context = load_controller_context()
    databases = catalog.get("managed_postgres_databases", [])
    if not isinstance(databases, list):
        raise ValueError("managed_postgres_databases must be a list")

    db_entries: list[dict[str, Any]] = []
    try:
        for db_name in databases:
            db_name = str(db_name)
            table_count_command = (
                "sudo -u postgres psql "
                f"-d {shlex.quote(db_name)} -Atqc "
                "\"SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema NOT IN ('pg_catalog','information_schema');\""
            )
            row_count_command = (
                "sudo -u postgres psql "
                f"-d {shlex.quote(db_name)} -Atqc "
                "\"SELECT COALESCE(sum(n_live_tup),0)::bigint FROM pg_stat_user_tables;\""
            )
            table_count_result = run_command(build_guest_ssh_command(context, "postgres-lv3", table_count_command))
            row_count_result = run_command(build_guest_ssh_command(context, "postgres-lv3", row_count_command))
            if table_count_result.returncode != 0:
                raise RuntimeError(table_count_result.stderr or table_count_result.stdout or db_name)
            if row_count_result.returncode != 0:
                raise RuntimeError(row_count_result.stderr or row_count_result.stdout or db_name)
            db_entries.append(
                {
                    "database": db_name,
                    "table_count": int((table_count_result.stdout or "0").strip()),
                    "estimated_row_count": int((row_count_result.stdout or "0").strip()),
                }
            )
        observations["postgres"] = {
            "status": "ok",
            "database_count": len(db_entries),
            "databases": db_entries,
            "total_table_count": sum(item["table_count"] for item in db_entries),
            "estimated_total_rows": sum(item["estimated_row_count"] for item in db_entries),
        }
    except Exception as exc:  # noqa: BLE001
        observations["postgres"] = {
            "status": "unavailable",
            "error": str(exc),
            "databases": db_entries,
        }
    return observations


def snapshot_signature(seed_class: str, class_config: dict[str, Any], observations: dict[str, Any]) -> str:
    payload = {
        "seed_class": seed_class,
        "datasets": class_config["datasets"],
        "observations": observations,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def snapshot_id(seed_class: str, class_config: dict[str, Any], observations: dict[str, Any]) -> str:
    signature = snapshot_signature(seed_class, class_config, observations)
    return f"{seed_class}-{signature[:12]}"


def snapshot_dir(seed_class: str, snapshot_name: str, *, catalog: dict[str, Any] | None = None) -> Path:
    return local_snapshot_root(catalog) / seed_class / snapshot_name


def latest_local_snapshot(seed_class: str, *, catalog: dict[str, Any] | None = None) -> Path | None:
    root = local_snapshot_root(catalog) / seed_class
    if not root.exists():
        return None
    candidates = sorted(path for path in root.iterdir() if path.is_dir() and (path / "manifest.json").exists())
    return candidates[-1] if candidates else None


def resolve_local_snapshot_dir(
    seed_class: str,
    *,
    snapshot_name: str | None = None,
    catalog: dict[str, Any] | None = None,
) -> Path:
    if snapshot_name:
        target = snapshot_dir(seed_class, snapshot_name, catalog=catalog)
        if not (target / "manifest.json").exists():
            raise FileNotFoundError(f"Unknown seed snapshot '{snapshot_name}' for class '{seed_class}'")
        return target
    latest = latest_local_snapshot(seed_class, catalog=catalog)
    if latest is None:
        raise FileNotFoundError(f"No local seed snapshot built for class '{seed_class}'")
    return latest


def deterministic_token(secret_value: str, namespace: str, index: int, *, length: int = 12) -> str:
    digest = hmac.new(
        secret_value.encode("utf-8"),
        f"{namespace}:{index}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:length]


def dataset_rows(seed_class: str, dataset: str, count: int, *, secret_value: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(1, count + 1):
        token = deterministic_token(secret_value, f"{seed_class}:{dataset}", index)
        suffix = f"{index:04d}"
        if dataset == "identities":
            rows.append(
                {
                    "seed_id": f"user-{suffix}",
                    "username": f"{seed_class}-user-{suffix}",
                    "email": f"{seed_class}-user-{suffix}@seed.invalid",
                    "display_name": f"{seed_class.title()} User {suffix}",
                    "role": ["viewer", "operator", "admin"][index % 3],
                    "pseudonym": token,
                }
            )
        elif dataset == "sessions":
            rows.append(
                {
                    "session_id": f"session-{suffix}",
                    "identity_id": f"user-{((index - 1) % max(count // 2, 1)) + 1:04d}",
                    "state": "active" if index % 5 else "expired",
                    "csrf_token": token,
                }
            )
        elif dataset == "workflow_runs":
            rows.append(
                {
                    "run_id": f"wf-{suffix}",
                    "workflow_slug": f"{seed_class}-workflow-{(index % 17) + 1:02d}",
                    "owner_id": f"user-{((index - 1) % 16) + 1:04d}",
                    "status": ["success", "queued", "failed", "running"][index % 4],
                    "trace_token": token,
                }
            )
        elif dataset == "messages":
            rows.append(
                {
                    "message_id": f"msg-{suffix}",
                    "channel": f"{seed_class}-channel-{(index % 12) + 1:02d}",
                    "author_id": f"user-{((index - 1) % 16) + 1:04d}",
                    "body": f"synthetic message {suffix} {token}",
                }
            )
        elif dataset == "assets":
            rows.append(
                {
                    "asset_id": f"asset-{suffix}",
                    "kind": ["service", "host", "database", "queue"][index % 4],
                    "name": f"{seed_class}-asset-{suffix}",
                    "stable_key": token,
                }
            )
        elif dataset == "audit_events":
            rows.append(
                {
                    "event_id": f"audit-{suffix}",
                    "actor_id": f"user-{((index - 1) % 16) + 1:04d}",
                    "action": f"{seed_class}.synthetic.{(index % 9) + 1}",
                    "target": f"{seed_class}-asset-{((index - 1) % 20) + 1:04d}",
                    "trace_id": token,
                }
            )
        else:
            rows.append({"id": f"{dataset}-{suffix}", "token": token})
    return rows


def write_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(snapshot_path: Path) -> dict[str, Any]:
    manifest = load_json(snapshot_path / "manifest.json")
    if not isinstance(manifest, dict):
        raise ValueError(f"Snapshot manifest must be an object: {snapshot_path / 'manifest.json'}")
    return manifest


def build_snapshot(seed_class: str, *, catalog: dict[str, Any] | None = None) -> Path:
    active_catalog = catalog or load_catalog()
    class_config = require_seed_class(seed_class, active_catalog)
    observations = collect_live_observations(active_catalog)
    secret_value = ensure_anonymization_secret(active_catalog)
    snapshot_name = snapshot_id(seed_class, class_config, observations)
    target_dir = snapshot_dir(seed_class, snapshot_name, catalog=active_catalog)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    dataset_checksums: dict[str, str] = {}
    for dataset_name, raw_count in sorted(class_config["datasets"].items()):
        rows = dataset_rows(seed_class, dataset_name, int(raw_count), secret_value=secret_value)
        dataset_path = target_dir / f"{dataset_name}.ndjson"
        write_ndjson(dataset_path, rows)
        dataset_checksums[dataset_path.name] = sha256_file(dataset_path)

    manifest = {
        "schema_version": "1.0.0",
        "seed_class": seed_class,
        "snapshot_id": snapshot_name,
        "description": class_config.get("description", ""),
        "catalog_path": str(SEED_CATALOG_PATH.relative_to(catalog_repo_root())),
        "observation_fingerprint": snapshot_signature(seed_class, class_config, observations),
        "dataset_counts": {name: int(value) for name, value in sorted(class_config["datasets"].items())},
        "observations": observations,
        "checksums": dataset_checksums,
    }
    write_json(target_dir / "manifest.json", manifest, sort_keys=True)
    return target_dir


def verify_local_snapshot(snapshot_path: Path) -> dict[str, Any]:
    manifest = load_manifest(snapshot_path)
    checksums = manifest.get("checksums", {})
    if not isinstance(checksums, dict) or not checksums:
        raise ValueError(f"{snapshot_path / 'manifest.json'} must define file checksums")
    verified: list[str] = []
    for filename, expected in checksums.items():
        file_path = snapshot_path / filename
        if not file_path.exists():
            raise FileNotFoundError(file_path)
        observed = sha256_file(file_path)
        if observed != expected:
            raise ValueError(f"Checksum mismatch for {file_path.name}: {observed} != {expected}")
        verified.append(filename)
    return {
        "seed_class": manifest["seed_class"],
        "snapshot_id": manifest["snapshot_id"],
        "verified_files": sorted(verified),
    }


def ssh_base_command_for_inventory_target(target: str) -> list[str]:
    build_guest_ssh_command, load_controller_context, _run_command = _load_drift_helpers()
    context = load_controller_context()
    return build_guest_ssh_command(context, target, "true")[:-1]


def run_ssh(ssh_base: list[str], remote_command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*ssh_base, remote_command],
        text=True,
        capture_output=True,
        check=False,
    )


def stream_directory_to_remote(
    snapshot_path: Path,
    ssh_base: list[str],
    remote_dir: str,
    *,
    directory_mode: str = "0755",
    sudo: bool = False,
) -> None:
    remote_command = (
        f"{'sudo ' if sudo else ''}install -d -m {shlex.quote(directory_mode)} {shlex.quote(remote_dir)} "
        f"&& {'sudo ' if sudo else ''}tar -C {shlex.quote(remote_dir)} -xf -"
    )
    tar_process = subprocess.Popen(
        ["tar", "-C", str(snapshot_path), "-cf", "-", "."],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
    )
    try:
        ssh_process = subprocess.Popen(
            [*ssh_base, remote_command],
            stdin=tar_process.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert tar_process.stdout is not None
        tar_process.stdout.close()
        ssh_stdout, ssh_stderr = ssh_process.communicate()
        tar_stderr = tar_process.stderr.read().decode("utf-8", errors="replace") if tar_process.stderr else ""
        tar_returncode = tar_process.wait()
        if tar_returncode != 0:
            raise RuntimeError(tar_stderr.strip() or f"tar exited with {tar_returncode}")
        if ssh_process.returncode != 0:
            detail = ssh_stderr.strip() or ssh_stdout.strip() or f"ssh exited with {ssh_process.returncode}"
            raise RuntimeError(detail)
    finally:
        if tar_process.poll() is None:
            tar_process.kill()


def remote_snapshot_dir(snapshot_path: Path, *, catalog: dict[str, Any] | None = None) -> str:
    active_catalog = catalog or load_catalog()
    manifest = load_manifest(snapshot_path)
    base_path = str(active_catalog["remote_store"]["base_path"])
    return f"{base_path.rstrip('/')}/{manifest['seed_class']}/{manifest['snapshot_id']}"


def publish_snapshot(
    seed_class: str,
    *,
    snapshot_name: str | None = None,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_catalog = catalog or load_catalog()
    snapshot_path = resolve_local_snapshot_dir(seed_class, snapshot_name=snapshot_name, catalog=active_catalog)
    manifest = load_manifest(snapshot_path)
    ssh_base = ssh_base_command_for_inventory_target(str(active_catalog["remote_store"]["host"]))
    remote_dir = remote_snapshot_dir(snapshot_path, catalog=active_catalog)
    stream_directory_to_remote(
        snapshot_path,
        ssh_base,
        remote_dir,
        directory_mode=str(active_catalog["remote_store"].get("directory_mode", "0750")),
        sudo=True,
    )
    result = run_ssh(
        ssh_base,
        f"sudo test -f {shlex.quote(remote_dir + '/manifest.json')} && sudo cat {shlex.quote(remote_dir + '/manifest.json')}",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or remote_dir)
    remote_manifest = json.loads(result.stdout)
    if remote_manifest.get("snapshot_id") != manifest["snapshot_id"]:
        raise ValueError("Published snapshot manifest does not match local snapshot id")
    return {
        "seed_class": manifest["seed_class"],
        "snapshot_id": manifest["snapshot_id"],
        "remote_dir": remote_dir,
    }


def verify_remote_snapshot(
    seed_class: str,
    *,
    snapshot_name: str | None = None,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_catalog = catalog or load_catalog()
    snapshot_path = resolve_local_snapshot_dir(seed_class, snapshot_name=snapshot_name, catalog=active_catalog)
    manifest = load_manifest(snapshot_path)
    ssh_base = ssh_base_command_for_inventory_target(str(active_catalog["remote_store"]["host"]))
    remote_dir = remote_snapshot_dir(snapshot_path, catalog=active_catalog)
    python_body = (
        "import hashlib, json, pathlib\n"
        f"root = pathlib.Path({remote_dir!r})\n"
        "manifest = json.loads((root / 'manifest.json').read_text())\n"
        "checksums = {}\n"
        "for name in sorted(manifest['checksums']):\n"
        "    checksums[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()\n"
        "print(json.dumps({'snapshot_id': manifest['snapshot_id'], 'checksums': checksums}, sort_keys=True))\n"
    )
    command = f"sudo python3 - <<'PY'\n{python_body}PY"
    result = run_ssh(ssh_base, command)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or remote_dir)
    remote_payload = json.loads(result.stdout)
    if remote_payload["snapshot_id"] != manifest["snapshot_id"]:
        raise ValueError("Remote snapshot id does not match local manifest")
    if remote_payload["checksums"] != manifest["checksums"]:
        raise ValueError("Remote snapshot checksums do not match local manifest")
    return {
        "seed_class": manifest["seed_class"],
        "snapshot_id": manifest["snapshot_id"],
        "remote_dir": remote_dir,
        "verified_files": sorted(manifest["checksums"].keys()),
    }


def stage_snapshot_with_ssh(
    snapshot_path: Path,
    ssh_base: list[str],
    remote_dir: str,
    *,
    sudo: bool = True,
) -> dict[str, Any]:
    stream_directory_to_remote(snapshot_path, ssh_base, remote_dir, directory_mode="0755", sudo=sudo)
    verify = run_ssh(
        ssh_base,
        f"{'sudo ' if sudo else ''}test -f {shlex.quote(remote_dir + '/manifest.json')}",
    )
    if verify.returncode != 0:
        raise RuntimeError(verify.stderr.strip() or verify.stdout.strip() or remote_dir)
    manifest = load_manifest(snapshot_path)
    return {
        "seed_class": manifest["seed_class"],
        "snapshot_id": manifest["snapshot_id"],
        "remote_dir": remote_dir,
    }


def stage_snapshot_to_remote_dir(
    seed_class: str,
    ssh_base: list[str],
    *,
    remote_dir: str,
    snapshot_name: str | None = None,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_catalog = catalog or load_catalog()
    snapshot_path = resolve_local_snapshot_dir(seed_class, snapshot_name=snapshot_name, catalog=active_catalog)
    return stage_snapshot_with_ssh(snapshot_path, ssh_base, remote_dir, sudo=True)


def list_snapshots(seed_class: str | None = None, *, catalog: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    active_catalog = catalog or load_catalog()
    classes = [seed_class] if seed_class else seed_classes(active_catalog)
    rows: list[dict[str, Any]] = []
    for class_name in classes:
        root = local_snapshot_root(active_catalog) / class_name
        if not root.exists():
            continue
        for path in sorted(root.iterdir()):
            if not path.is_dir() or not (path / "manifest.json").exists():
                continue
            manifest = load_manifest(path)
            rows.append(
                {
                    "seed_class": class_name,
                    "snapshot_id": manifest["snapshot_id"],
                    "path": str(path),
                }
            )
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)

    build = subparsers.add_parser("build", help="Build one anonymized seed snapshot locally.")
    build.add_argument("--seed-class", required=True)

    publish = subparsers.add_parser("publish", help="Publish one local snapshot to backup-lv3.")
    publish.add_argument("--seed-class", required=True)
    publish.add_argument("--snapshot-id")

    verify = subparsers.add_parser("verify", help="Verify one local or remote snapshot.")
    verify.add_argument("--seed-class", required=True)
    verify.add_argument("--snapshot-id")
    verify.add_argument("--remote", action="store_true")

    listing = subparsers.add_parser("list", help="List available local snapshots.")
    listing.add_argument("--seed-class")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        catalog = load_catalog()
        if args.action == "build":
            snapshot_path = build_snapshot(args.seed_class, catalog=catalog)
            manifest = load_manifest(snapshot_path)
            print(json.dumps({"snapshot_path": str(snapshot_path), **manifest}, indent=2, sort_keys=True))
            return 0
        if args.action == "publish":
            result = publish_snapshot(args.seed_class, snapshot_name=args.snapshot_id, catalog=catalog)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.action == "verify":
            if args.remote:
                result = verify_remote_snapshot(args.seed_class, snapshot_name=args.snapshot_id, catalog=catalog)
            else:
                snapshot_path = resolve_local_snapshot_dir(args.seed_class, snapshot_name=args.snapshot_id, catalog=catalog)
                result = verify_local_snapshot(snapshot_path)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.action == "list":
            print(json.dumps(list_snapshots(seed_class=args.seed_class, catalog=catalog), indent=2, sort_keys=True))
            return 0
        raise ValueError(f"Unsupported action '{args.action}'")
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("seed snapshots", exc)


if __name__ == "__main__":
    raise SystemExit(main())
