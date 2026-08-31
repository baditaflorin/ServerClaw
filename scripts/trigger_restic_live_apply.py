#!/usr/bin/env python3
"""Run the ADR 0302 restic workflow on docker-runtime through the managed SSH path."""

from __future__ import annotations

import os

import argparse
import json
import re
import shlex
import subprocess
from pathlib import Path, PurePosixPath

import yaml

from controller_automation_toolkit import emit_cli_error, resolve_repo_local_path
from drift_lib import build_guest_ssh_command, load_controller_context, run_command


LOCAL_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REMOTE_REPO_ROOT = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server")
DEFAULT_REMOTE_CATALOG_PATH = f"{DEFAULT_REMOTE_REPO_ROOT}/config/restic-file-backup-catalog.json"
DEFAULT_REMOTE_BACKUP_RECEIPTS_DIR = f"{DEFAULT_REMOTE_REPO_ROOT}/receipts/restic-backups"
DEFAULT_REMOTE_LATEST_SNAPSHOT_RECEIPT = f"{DEFAULT_REMOTE_REPO_ROOT}/receipts/restic-snapshots-latest.json"
DEFAULT_REMOTE_RESTORE_VERIFY_DIR = f"{DEFAULT_REMOTE_REPO_ROOT}/receipts/restic-restore-verifications"
DEFAULT_REMOTE_RUNTIME_STATE_DIR = "/var/lib/lv3/restic-config-backup"
DEFAULT_REMOTE_CACHE_DIR = f"{DEFAULT_REMOTE_RUNTIME_STATE_DIR}/cache"
DEFAULT_RUNTIME_CREDENTIAL_FILE = "/run/lv3-systemd-credentials/restic-config-backup/runtime-config.json"
DEFAULT_FALLBACK_REMOTE_SCRIPT_PATH = "/opt/api-gateway/service/scripts/restic_config_backup.py"
DEFAULT_FALLBACK_REMOTE_CATALOG_PATH = "/etc/lv3/restic-config-backup/restic-file-backup-catalog.json"
REMOTE_RUNTIME_SUPPORT_FILES = (
    ("scripts/restic_config_backup.py", 0o755),
    ("scripts/outline_client.py", 0o644),
    ("scripts/script_bootstrap.py", 0o644),
    ("scripts/controller_automation_toolkit.py", 0o644),
    ("scripts/ntfy_publish.py", 0o644),
    ("scripts/validation_toolkit.py", 0o644),
    ("platform/__init__.py", 0o644),
    ("platform/datetime_compat.py", 0o644),
    ("platform/enum_compat.py", 0o644),
    ("platform/events/__init__.py", 0o644),
    ("platform/events/taxonomy.py", 0o644),
    ("platform/repo.py", 0o644),
    ("platform/retry/__init__.py", 0o644),
    ("platform/retry/classification.py", 0o644),
    ("platform/retry/policy.py", 0o644),
    ("config/event-taxonomy.yaml", 0o644),
    ("config/ntfy/topics.yaml", 0o644),
    ("config/retry-policies.yaml", 0o644),
    ("config/restic-file-backup-catalog.json", 0o644),
    ("versions/stack.yaml", 0o644),
)
SYNCABLE_REPORT_KEYS = ("receipt_path", "latest_snapshot_receipt")
RESTIC_REMOTE_COMMAND_TIMEOUT_SECONDS = int(os.environ.get("RESTIC_TRIGGER_TIMEOUT_SECONDS", "180"))
SIMPLE_JINJA_VARIABLE_PATTERN = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")


def extract_report_json(stdout: str) -> dict | None:
    for line in reversed(stdout.splitlines()):
        if line.startswith("REPORT_JSON="):
            return json.loads(line.removeprefix("REPORT_JSON="))
    return None


def build_remote_command(
    *,
    mode: str,
    triggered_by: str,
    repo_root: str,
    credential_file: str,
    live_apply_trigger: bool,
    fallback_script_path: str = DEFAULT_FALLBACK_REMOTE_SCRIPT_PATH,
    fallback_catalog_path: str = DEFAULT_FALLBACK_REMOTE_CATALOG_PATH,
    prefer_fallback_script: bool = False,
) -> str:
    primary_script_path = f"{repo_root}/scripts/restic_config_backup.py"
    primary_catalog_path = f"{repo_root}/config/restic-file-backup-catalog.json"
    command = [
        "--backup-receipts-dir",
        f"{repo_root}/receipts/restic-backups",
        "--latest-snapshot-receipt",
        f"{repo_root}/receipts/restic-snapshots-latest.json",
        "--restore-verification-dir",
        f"{repo_root}/receipts/restic-restore-verifications",
        "--runtime-state-dir",
        DEFAULT_REMOTE_RUNTIME_STATE_DIR,
        "--cache-dir",
        DEFAULT_REMOTE_CACHE_DIR,
        "--credential-file",
        credential_file,
        "--mode",
        mode,
        "--triggered-by",
        triggered_by,
        "--print-report-json",
    ]
    if live_apply_trigger:
        command.append("--live-apply-trigger")
    rendered_args = " ".join(shlex.quote(item) for item in command)
    prefer_fallback_line = ""
    if prefer_fallback_script:
        prefer_fallback_line = 'if [ -f "$fallback_script_path" ]; then script_path="$fallback_script_path"; fi'

    shell_script = "\n".join(
        [
            "set -euo pipefail",
            f"script_path={shlex.quote(primary_script_path)}",
            f"fallback_script_path={shlex.quote(fallback_script_path)}",
            f"catalog_path={shlex.quote(primary_catalog_path)}",
            f"fallback_catalog_path={shlex.quote(fallback_catalog_path)}",
            prefer_fallback_line,
            'if [ ! -f "$script_path" ] && [ -f "$fallback_script_path" ]; then',
            '  script_path="$fallback_script_path"',
            "fi",
            'if [ ! -f "$script_path" ]; then',
            '  echo "restic_config_backup.py is missing from both $script_path and $fallback_script_path" >&2',
            "  exit 2",
            "fi",
            'if [ ! -f "$catalog_path" ] && [ -f "$fallback_catalog_path" ]; then',
            '  catalog_path="$fallback_catalog_path"',
            "fi",
            'if [ ! -f "$catalog_path" ]; then',
            '  echo "restic-file-backup-catalog.json is missing from both $catalog_path and $fallback_catalog_path" >&2',
            "  exit 2",
            "fi",
            f'export PYTHONPATH="{repo_root}:${{PYTHONPATH:-}}"',
            (
                f'exec python3 "$script_path" --repo-root {shlex.quote(repo_root)} '
                f'--catalog "$catalog_path" {rendered_args}'
            ),
        ]
    )
    return " ".join(
        shlex.quote(item)
        for item in [
            "sudo",
            "/bin/bash",
            "-lc",
            shell_script,
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trigger ADR 0302 live restic workflows on docker-runtime.")
    parser.add_argument("--env", default="production")
    parser.add_argument("--mode", choices=["backup", "restore-verify"], default="backup")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--credential-file", default=None)
    parser.add_argument("--triggered-by", default="manual")
    parser.add_argument("--live-apply-trigger", action="store_true")
    return parser


def sync_remote_runtime_file(
    context: dict,
    *,
    target: str,
    local_path: Path,
    remote_path: str,
    mode: int,
) -> None:
    remote_parent = str(PurePosixPath(remote_path).parent)
    remote_command = (
        f"sudo install -d -o root -g root -m 0755 {shlex.quote(remote_parent)}"
        f" && sudo tee {shlex.quote(remote_path)} >/dev/null"
        f" && sudo chmod {mode:o} {shlex.quote(remote_path)}"
    )
    command = build_guest_ssh_command(context, target, remote_command)
    completed = subprocess.run(
        command,
        input=local_path.read_text(encoding="utf-8"),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "remote sync failed"
        raise RuntimeError(f"{remote_path}: {detail}")


def remote_file_exists(
    context: dict,
    *,
    target: str,
    path: str,
) -> bool:
    remote_command = f"sudo test -s {shlex.quote(path)}"
    command = build_guest_ssh_command(context, target, remote_command)
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def resolve_openbao_init_local_file() -> Path:
    candidate_paths = (
        LOCAL_REPO_ROOT / "inventory" / "group_vars" / "all" / "main.yml",
        LOCAL_REPO_ROOT / "inventory" / "group_vars" / "all.yml",
    )
    for group_vars in candidate_paths:
        if not group_vars.is_file():
            continue
        payload = yaml.safe_load(group_vars.read_text(encoding="utf-8")) or {}
        init_path = resolve_group_var_path(
            str(payload.get("openbao_init_local_file") or "").strip(),
            payload,
        )
        if init_path:
            shared_local_root_prefix = "{{ repo_shared_local_root }}/"
            if init_path.startswith(shared_local_root_prefix):
                repo_relative_local_path = Path(".local") / init_path.removeprefix(shared_local_root_prefix)
                return resolve_repo_local_path(repo_relative_local_path, repo_root=LOCAL_REPO_ROOT)
            return resolve_repo_local_path(init_path, repo_root=LOCAL_REPO_ROOT)

    rendered_candidates = ", ".join(str(path.relative_to(LOCAL_REPO_ROOT)) for path in candidate_paths)
    raise ValueError(
        f"openbao_init_local_file is not declared in any supported inventory defaults file ({rendered_candidates})"
    )


def resolve_group_var_path(value: str, payload: dict) -> str:
    """Resolve simple same-file Jinja scalar references in a local artifact path."""

    if not value:
        return value

    substitutions = {key: item for key, item in payload.items() if isinstance(key, str) and isinstance(item, str)}
    substitutions["repo_shared_local_root"] = str(resolve_repo_local_path(".local", repo_root=LOCAL_REPO_ROOT))
    rendered = value
    for _ in range(16):
        updated = SIMPLE_JINJA_VARIABLE_PATTERN.sub(
            lambda match: substitutions.get(match.group(1), match.group(0)),
            rendered,
        )
        if updated == rendered:
            break
        rendered = updated

    unresolved = SIMPLE_JINJA_VARIABLE_PATTERN.search(rendered)
    if unresolved is not None:
        raise ValueError(f"openbao_init_local_file references unresolved variable '{unresolved.group(1)}'")
    return rendered


def resolve_remote_repo_root(explicit_repo_root: str | None) -> str:
    """Resolve the managed runtime checkout path from the selected identity overlay."""

    explicit = str(explicit_repo_root or "").strip()
    if explicit:
        return explicit

    environment_value = os.environ.get("PLATFORM_REPO_ROOT", "").strip()
    if environment_value:
        return environment_value

    identity_paths = [LOCAL_REPO_ROOT / "inventory" / "group_vars" / "all" / "identity.yml"]
    selected_overlay = os.environ.get("PLATFORM_IDENTITY_OVERLAY", "").strip()
    if selected_overlay:
        identity_paths.append(Path(selected_overlay).expanduser())

    identity: dict[str, object] = {}
    for path in identity_paths:
        if not path.is_file():
            continue
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"identity overlay must contain a mapping: {path}")
        identity.update(payload)

    raw_path = str(identity.get("platform_repo_checkout_path") or "").strip()
    if not raw_path:
        repo_name = str(identity.get("platform_repo_name") or "").strip()
        raw_path = f"/srv/{repo_name}" if repo_name else DEFAULT_REMOTE_REPO_ROOT

    resolved = resolve_group_var_path(raw_path, identity)
    candidate = PurePosixPath(resolved)
    if not candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"managed restic repository path must be an absolute safe path: {resolved}")
    return str(candidate)


def resolve_runtime_credential_file(explicit_credential_file: str | None) -> str:
    """Resolve the service credential path for the selected deployment identity."""

    explicit = str(explicit_credential_file or "").strip()
    if explicit:
        candidate = PurePosixPath(explicit)
        if not candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"restic credential path must be an absolute safe path: {explicit}")
        return str(candidate)

    config_prefix = os.environ.get("PLATFORM_CONFIG_PREFIX", "").strip()
    selected_overlay = os.environ.get("PLATFORM_IDENTITY_OVERLAY", "").strip()
    if not config_prefix and selected_overlay:
        overlay_path = Path(selected_overlay).expanduser()
        if not overlay_path.is_file():
            raise ValueError(f"selected identity overlay is missing: {overlay_path}")
        payload = yaml.safe_load(overlay_path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"identity overlay must contain a mapping: {overlay_path}")
        configured_prefix = str(payload.get("platform_config_prefix") or "").strip()
        if configured_prefix and "{{" not in configured_prefix:
            config_prefix = configured_prefix
        if not config_prefix:
            platform_domain = str(payload.get("platform_domain") or "").strip()
            if platform_domain and "{{" not in platform_domain:
                config_prefix = platform_domain.split(".", 1)[0]

    if not config_prefix:
        return DEFAULT_RUNTIME_CREDENTIAL_FILE
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", config_prefix):
        raise ValueError("platform credential configuration prefix contains unsupported characters")
    return f"/run/{config_prefix}-systemd-credentials/restic-config-backup/runtime-config.json"


def run_local_converge_restic(env: str) -> None:
    init_path = resolve_openbao_init_local_file()
    if not init_path.is_file():
        raise ValueError(f"OpenBao init payload is missing locally: {init_path}")

    # A parent live-apply can use scoped Ansible tags.  Do not let GNU make
    # propagate those command-line overrides into this dependency converge:
    # restic's credential bootstrap is deliberately untagged and must always
    # run before the trigger checks the runtime credential file.
    command = ["make", "converge-restic-config-backup", f"env={env}", "EXTRA_ARGS="]
    completed = subprocess.run(
        command,
        cwd=str(LOCAL_REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "local restic converge failed"
        raise RuntimeError(detail)


def ensure_remote_runtime_credentials(
    context: dict,
    *,
    env: str,
    credential_file: str,
    refresh: bool = False,
    target: str = "docker-runtime",
) -> None:
    if refresh:
        run_local_converge_restic(env)
    elif remote_file_exists(context, target=target, path=credential_file):
        return

    if not refresh and not remote_file_exists(context, target=target, path=credential_file):
        run_local_converge_restic(env)

    if not remote_file_exists(context, target=target, path=credential_file):
        raise RuntimeError(
            f"restic runtime credentials are still missing on {target} after converge: {credential_file}"
        )


def normalize_repo_relative_path(path: str) -> PurePosixPath:
    candidate = PurePosixPath(str(path).strip())
    if candidate.is_absolute():
        raise ValueError(f"expected a repo-relative path, got absolute path: {path}")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError(f"receipt sync path must stay within the repo root: {path}")
    if not candidate.parts or candidate.parts[0] != "receipts":
        raise ValueError(f"receipt sync path must stay under receipts/: {path}")
    return candidate


def fetch_remote_repo_file(
    context: dict,
    *,
    target: str,
    repo_root: str,
    relative_path: str,
) -> str:
    relative = normalize_repo_relative_path(relative_path)
    remote_path = str(PurePosixPath(repo_root) / relative)
    remote_command = f"sudo cat {shlex.quote(remote_path)}"
    command = build_guest_ssh_command(context, target, remote_command)
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "remote download failed"
        raise RuntimeError(f"{remote_path}: {detail}")
    return completed.stdout


def sync_reported_receipt_artifacts(
    context: dict,
    *,
    target: str,
    repo_root: str,
    report: dict | None,
) -> list[str]:
    if not isinstance(report, dict):
        return []

    synced: list[str] = []
    for key in SYNCABLE_REPORT_KEYS:
        relative_path = report.get(key)
        if not isinstance(relative_path, str) or not relative_path.strip():
            continue
        relative = normalize_repo_relative_path(relative_path)
        local_path = LOCAL_REPO_ROOT / Path(*relative.parts)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(
            fetch_remote_repo_file(
                context,
                target=target,
                repo_root=repo_root,
                relative_path=relative_path,
            ),
            encoding="utf-8",
        )
        synced.append(relative_path)
    return synced


def ensure_remote_runtime_support_files(context: dict, *, repo_root: str, target: str = "docker-runtime") -> None:
    repo_root_path = PurePosixPath(repo_root)
    for relative_path, mode in REMOTE_RUNTIME_SUPPORT_FILES:
        local_path = LOCAL_REPO_ROOT / relative_path
        if not local_path.is_file():
            raise ValueError(f"required runtime support file is missing locally: {local_path}")
        remote_path = str(repo_root_path / relative_path)
        sync_remote_runtime_file(
            context,
            target=target,
            local_path=local_path,
            remote_path=remote_path,
            mode=mode,
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.env != "production":
            print(
                json.dumps(
                    {
                        "status": "skipped",
                        "reason": "restic live apply only runs against production",
                        "env": args.env,
                    },
                    indent=2,
                )
            )
            return 0

        credential_file = resolve_runtime_credential_file(args.credential_file)
        context = load_controller_context()
        repo_root = resolve_remote_repo_root(args.repo_root)
        ensure_remote_runtime_support_files(context, repo_root=repo_root)
        ensure_remote_runtime_credentials(
            context,
            env=args.env,
            credential_file=credential_file,
            refresh=args.live_apply_trigger and args.mode == "backup",
        )
        prefer_fallback_script = os.environ.get("RESTIC_USE_FALLBACK_SCRIPT") == "1"
        remote_command = build_remote_command(
            mode=args.mode,
            triggered_by=args.triggered_by,
            repo_root=repo_root,
            credential_file=credential_file,
            live_apply_trigger=args.live_apply_trigger,
            prefer_fallback_script=prefer_fallback_script,
        )
        command = build_guest_ssh_command(context, "docker-runtime", remote_command)
        outcome = run_command(command, timeout=RESTIC_REMOTE_COMMAND_TIMEOUT_SECONDS)
        report = extract_report_json(outcome.stdout)
        payload = {
            "status": "ok" if outcome.returncode == 0 else "error",
            "target": "docker-runtime",
            "command": remote_command,
            "returncode": outcome.returncode,
            "stdout": outcome.stdout.strip(),
            "stderr": outcome.stderr.strip(),
        }
        allow_timeout = os.environ.get("RESTIC_ALLOW_TIMEOUT") == "1"
        if outcome.returncode != 0 and allow_timeout and "timed out" in (outcome.stderr or "").lower():
            payload["status"] = "warning"
            payload["warning"] = "Restic live-apply trigger timed out; see stderr for details."
            print(json.dumps(payload, indent=2))
            if getattr(args, "print_report_json", False):
                print("REPORT_JSON=" + json.dumps(payload, separators=(",", ":")))
            return 0
        if outcome.returncode == 0:
            synced_paths = sync_reported_receipt_artifacts(
                context,
                target="docker-runtime",
                repo_root=repo_root,
                report=report,
            )
            if synced_paths:
                payload["synced_local_paths"] = synced_paths
        if report is not None:
            payload["report"] = report
            if isinstance(report, dict):
                payload["summary"] = report.get("summary") or ((report.get("report") or {}).get("summary"))
        print(json.dumps(payload, indent=2))
        return 0 if outcome.returncode == 0 else 1
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        return emit_cli_error("Restic live apply trigger", exc)


if __name__ == "__main__":
    raise SystemExit(main())
