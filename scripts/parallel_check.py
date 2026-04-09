#!/usr/bin/env python3
"""Run manifest-defined Docker checks in parallel."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_MANIFEST = Path("config/check-runner-manifest.json")
SPINNER_FRAMES = "|/-\\"
PASSTHROUGH_ENV_VARS = (
    "LV3_SNAPSHOT_ID",
    "LV3_SNAPSHOT_GENERATED_AT",
    "LV3_SNAPSHOT_SOURCE_COMMIT",
    "LV3_SNAPSHOT_BRANCH",
    "LV3_DOCKER_WORKSPACE_PATH",
    "LV3_VALIDATION_BASE_REF",
    "LV3_VALIDATION_CHANGED_FILES_JSON",
)
RUNNER_UNAVAILABLE_MARKERS = (
    "cannot connect to the docker daemon",
    "error during connect",
    "is the docker daemon running",
    "unable to find image 'registry.localhost/check-runner/",
    "unsupported manifest media type",
    "no matching manifest for",
    "pull access denied",
    "received unexpected http status: 502 bad gateway",
    "exec format error",
)


@dataclass(frozen=True)
class CheckDefinition:
    label: str
    image: str
    command: str
    working_dir: str
    timeout_seconds: int
    local_fallback_command: str | None = None
    native_command: str | None = None
    cache_mounts: tuple[str, ...] = ()


@dataclass(frozen=True)
class CheckResult:
    label: str
    status: str
    returncode: int
    duration_seconds: float
    stdout: str
    stderr: str
    docker_command: list[str]


def classify_runner_unavailable(stdout: str, stderr: str) -> str | None:
    combined = f"{stdout}\n{stderr}".lower()
    for marker in RUNNER_UNAVAILABLE_MARKERS:
        if marker in combined:
            return marker
    return None


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Docker-based repository checks defined in config/check-runner-manifest.json.",
    )
    parser.add_argument("checks", nargs="*", help="Specific check labels to run.")
    parser.add_argument("--all", action="store_true", help="Run every check in the manifest.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Path to the check runner manifest.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace to mount into the check runner containers.",
    )
    parser.add_argument(
        "--docker-binary",
        default=os.environ.get("DOCKER_BIN", "docker"),
        help="Docker-compatible binary to use for execution.",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=0,
        help="Maximum parallel checks. Defaults to the number requested.",
    )
    return parser.parse_args(argv)


def load_manifest(manifest_path: Path) -> dict[str, CheckDefinition]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"manifest {manifest_path} must contain a JSON object")

    checks: dict[str, CheckDefinition] = {}
    for label, config in payload.items():
        if not isinstance(config, dict):
            raise ValueError(f"manifest entry {label!r} must be an object")

        checks[label] = CheckDefinition(
            label=label,
            image=str(config["image"]),
            command=str(config["command"]),
            working_dir=str(config.get("working_dir", "/workspace")),
            timeout_seconds=int(config.get("timeout_seconds", 300)),
            local_fallback_command=(
                str(config["local_fallback_command"])
                if config.get("local_fallback_command")
                else None
            ),
            native_command=(
                str(config["native_command"])
                if config.get("native_command")
                else None
            ),
            cache_mounts=tuple(str(item) for item in config.get("cache_mounts", [])),
        )
    return checks


def resolve_checks(
    manifest: dict[str, CheckDefinition],
    requested: Iterable[str],
    run_all: bool,
) -> list[CheckDefinition]:
    requested_labels = list(requested)
    if run_all:
        return [manifest[label] for label in sorted(manifest)]
    if not requested_labels:
        raise ValueError("select one or more checks, or pass --all")

    missing = [label for label in requested_labels if label not in manifest]
    if missing:
        available = ", ".join(sorted(manifest))
        raise ValueError(
            f"unknown check(s): {', '.join(missing)}. Available checks: {available}"
        )
    return [manifest[label] for label in requested_labels]


def build_docker_command(
    check: CheckDefinition,
    workspace: Path,
    docker_binary: str,
    *,
    cidfile_path: Path | None = None,
) -> list[str]:
    workspace_mount_source = os.environ.get("LV3_DOCKER_WORKSPACE_PATH", "").strip()
    if not workspace_mount_source:
        workspace_mount_source = str(workspace.resolve())
    mount_args = ["-v", f"{workspace_mount_source}:/workspace"]
    env_args: list[str] = []
    safe_directories = sorted({"/workspace", check.working_dir})
    env_args.extend(["-e", f"GIT_CONFIG_COUNT={len(safe_directories)}"])
    for index, safe_directory in enumerate(safe_directories):
        env_args.extend(["-e", f"GIT_CONFIG_KEY_{index}=safe.directory"])
        env_args.extend(["-e", f"GIT_CONFIG_VALUE_{index}={safe_directory}"])
    for env_name in PASSTHROUGH_ENV_VARS:
        value = os.environ.get(env_name)
        if value:
            env_args.extend(["-e", f"{env_name}={value}"])
    git_metadata_file = workspace / ".git"
    if git_metadata_file.is_file():
        gitdir_line = git_metadata_file.read_text(encoding="utf-8").strip()
        if gitdir_line.startswith("gitdir:"):
            gitdir = Path(gitdir_line.split(":", 1)[1].strip()).resolve()
            common_dir = gitdir.joinpath("commondir")
            extra_mounts = {gitdir}
            if common_dir.exists():
                extra_mounts.add((gitdir / common_dir.read_text(encoding="utf-8").strip()).resolve())
            for path in sorted(extra_mounts):
                mount_args.extend(["-v", f"{path}:{path}:ro"])

    for cache_mount in check.cache_mounts:
        if cache_mount == "ansible_collections":
            host_path = os.environ.get("LV3_ANSIBLE_COLLECTIONS_DIR")
            if host_path:
                mount_args.extend(["-v", f"{Path(host_path).resolve()}:/opt/lv3/ansible-collections"])
                env_args.extend(["-e", "LV3_ANSIBLE_COLLECTIONS_DIR=/opt/lv3/ansible-collections"])
            sha_file = os.environ.get("LV3_ANSIBLE_COLLECTIONS_SHA_FILE")
            if sha_file:
                env_args.extend(["-e", f"LV3_ANSIBLE_COLLECTIONS_SHA_FILE={sha_file}"])
        elif cache_mount == "pip":
            host_path = os.environ.get("LV3_PIP_CACHE_DIR")
            if host_path:
                mount_args.extend(["-v", f"{Path(host_path).resolve()}:/root/.cache/pip"])
                env_args.extend(["-e", "PIP_CACHE_DIR=/root/.cache/pip"])
        elif cache_mount == "trivy":
            host_path = os.environ.get("LV3_TRIVY_CACHE_DIR")
            if host_path:
                mount_args.extend(["-v", f"{Path(host_path).resolve()}:/var/lib/trivy"])
                env_args.extend(["-e", "TRIVY_CACHE_DIR=/var/lib/trivy"])
        elif cache_mount == "policy_tools":
            host_path = os.environ.get("LV3_POLICY_TOOLCHAIN_ROOT")
            if host_path:
                mount_args.extend(["-v", f"{Path(host_path).resolve()}:/opt/lv3/policy-toolchain"])
                env_args.extend(["-e", "LV3_POLICY_TOOLCHAIN_ROOT=/opt/lv3/policy-toolchain"])
        elif cache_mount == "packer_plugins":
            host_path = os.environ.get("LV3_PACKER_PLUGIN_CACHE_DIR")
            if host_path:
                mount_args.extend(["-v", f"{Path(host_path).resolve()}:/root/.packer.d"])
                env_args.extend(
                    [
                        "-e",
                        "PACKER_CACHE_ROOT=/root/.packer.d",
                        "-e",
                        "PACKER_PLUGIN_PATH=/root/.packer.d/plugins",
                    ]
                )
        elif cache_mount == "docker_socket":
            socket_path = Path(os.environ.get("LV3_DOCKER_SOCKET_PATH", "/var/run/docker.sock")).resolve()
            if socket_path.exists():
                mount_args.extend(["-v", f"{socket_path}:{socket_path}"])
                env_args.extend(["-e", f"DOCKER_HOST=unix://{socket_path}"])
            host_workspace = workspace.resolve()
            mount_args.extend(["-v", f"{host_workspace}:{host_workspace}"])
            env_args.extend(["-e", f"LV3_HOST_WORKSPACE={host_workspace}"])

    return [
        docker_binary,
        "run",
        "--rm",
        "--cpus=4",
        *(["--cidfile", str(cidfile_path)] if cidfile_path is not None else []),
        *mount_args,
        *env_args,
        "-w",
        check.working_dir,
        check.image,
        "sh",
        "-c",
        check.command,
    ]


def normalize_process_output(output: bytes | str | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace").strip()
    return output.strip()


def cleanup_timed_out_container(
    docker_binary: str,
    workspace: Path,
    cidfile_path: Path,
) -> str:
    if not cidfile_path.exists():
        return ""
    container_id = cidfile_path.read_text(encoding="utf-8").strip()
    cidfile_path.unlink(missing_ok=True)
    if not container_id:
        return ""
    completed = subprocess.run(
        [docker_binary, "rm", "-f", container_id],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    details = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
    if completed.returncode == 0 or "No such container" in details:
        return ""
    return details or f"docker rm -f {container_id} exited with {completed.returncode}"


def should_use_local_fallback_command(check: CheckDefinition) -> bool:
    source = os.environ.get("LV3_VALIDATION_SOURCE", "").strip().lower()
    return bool(check.local_fallback_command and source.startswith("local-"))


def should_use_native_command(check: CheckDefinition) -> bool:
    """Return True when LV3_NATIVE_EXECUTION=1 and the check has a native_command.

    Native execution runs the check directly on the host (no Docker container)
    and is intended for the build server where all gate tools are pre-installed
    and pinned via Ansible (ADR 0362).
    """
    return bool(
        os.environ.get("LV3_NATIVE_EXECUTION") == "1"
        and check.native_command
    )


def execute_check(
    check: CheckDefinition,
    workspace: Path,
    docker_binary: str,
) -> CheckResult:
    cidfile_path: Path | None = None
    if should_use_native_command(check):
        docker_command = ["sh", "-c", check.native_command or check.command]
    elif should_use_local_fallback_command(check):
        docker_command = ["sh", "-c", check.local_fallback_command or check.command]
    else:
        cidfile_dir = workspace / ".local" / "validation-gate" / "docker-cids"
        cidfile_dir.mkdir(parents=True, exist_ok=True)
        cidfile_handle = tempfile.NamedTemporaryFile(
            dir=cidfile_dir,
            prefix=f"{check.label}-",
            suffix=".cid",
            delete=False,
        )
        cidfile_path = Path(cidfile_handle.name)
        cidfile_handle.close()
        cidfile_path.unlink(missing_ok=True)
        docker_command = build_docker_command(check, workspace, docker_binary, cidfile_path=cidfile_path)
    started = time.monotonic()

    try:
        completed = subprocess.run(
            docker_command,
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
            timeout=check.timeout_seconds,
        )
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        unavailable_reason = classify_runner_unavailable(stdout, stderr)
        if completed.returncode == 0:
            status = "passed"
        elif unavailable_reason is not None:
            status = "runner_unavailable"
        else:
            status = "failed"
        return CheckResult(
            label=check.label,
            status=status,
            returncode=completed.returncode,
            duration_seconds=time.monotonic() - started,
            stdout=stdout,
            stderr=stderr,
            docker_command=docker_command,
        )
    except subprocess.TimeoutExpired as exc:
        cleanup_details = (
            cleanup_timed_out_container(docker_binary, workspace, cidfile_path)
            if cidfile_path is not None
            else ""
        )
        stderr = normalize_process_output(exc.stderr)
        if cleanup_details:
            stderr = "\n".join(part for part in (stderr, f"cleanup: {cleanup_details}") if part)
        return CheckResult(
            label=check.label,
            status="timed_out",
            returncode=124,
            duration_seconds=time.monotonic() - started,
            stdout=normalize_process_output(exc.stdout),
            stderr=stderr,
            docker_command=docker_command,
        )
    except FileNotFoundError as exc:
        return CheckResult(
            label=check.label,
            status="runner_unavailable",
            returncode=127,
            duration_seconds=time.monotonic() - started,
            stdout="",
            stderr=str(exc),
            docker_command=docker_command,
        )
    finally:
        if cidfile_path is not None:
            cidfile_path.unlink(missing_ok=True)


def print_progress(
    requested: list[CheckDefinition],
    completed: dict[str, CheckResult],
    frame_index: int,
) -> None:
    parts: list[str] = []
    for check in requested:
        if check.label in completed:
            parts.append(f"{check.label}:done")
        else:
            parts.append(f"{check.label}:{SPINNER_FRAMES[frame_index % len(SPINNER_FRAMES)]}")
    sys.stdout.write("\r" + "  ".join(parts) + " " * 4)
    sys.stdout.flush()


def print_summary(results: list[CheckResult]) -> None:
    label_width = max(len("CHECK"), *(len(result.label) for result in results))
    status_width = max(len("STATUS"), *(len(result.status) for result in results))

    print("\nCHECK".ljust(label_width), "STATUS".ljust(status_width), "DURATION(s)")
    for result in sorted(results, key=lambda item: item.label):
        print(
            result.label.ljust(label_width),
            result.status.ljust(status_width),
            f"{result.duration_seconds:.2f}",
        )

    for result in sorted(results, key=lambda item: item.label):
        if result.status == "passed":
            continue
        print(f"\n[{result.label}] docker command")
        print(" ".join(result.docker_command))
        if result.stdout:
            print(f"[{result.label}] stdout")
            print(result.stdout)
        if result.stderr:
            print(f"[{result.label}] stderr")
            print(result.stderr)


def run_checks(
    checks: list[CheckDefinition],
    workspace: Path,
    docker_binary: str,
    jobs: int,
) -> list[CheckResult]:
    max_workers = jobs if jobs > 0 else len(checks)
    results: dict[str, CheckResult] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures: dict[Future[CheckResult], str] = {
            executor.submit(execute_check, check, workspace, docker_binary): check.label
            for check in checks
        }
        frame_index = 0
        while futures:
            done = [future for future in futures if future.done()]
            for future in done:
                result = future.result()
                results[result.label] = result
                futures.pop(future)

            if sys.stdout.isatty() and futures:
                print_progress(checks, results, frame_index)
                frame_index += 1
            time.sleep(0.1)

    if sys.stdout.isatty():
        sys.stdout.write("\r")
        sys.stdout.flush()

    return [results[check.label] for check in checks]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    manifest = load_manifest(args.manifest)
    checks = resolve_checks(manifest, args.checks, args.all)
    results = run_checks(checks, args.workspace.resolve(), args.docker_binary, args.jobs)
    print_summary(results)
    return 0 if all(result.status == "passed" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
