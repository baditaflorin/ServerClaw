#!/usr/bin/env python3
"""Run manifest-defined Docker checks in parallel."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_MANIFEST = Path("config/check-runner-manifest.json")
SPINNER_FRAMES = "|/-\\"


@dataclass(frozen=True)
class CheckDefinition:
    label: str
    image: str
    command: str
    working_dir: str
    timeout_seconds: int


@dataclass(frozen=True)
class CheckResult:
    label: str
    status: str
    returncode: int
    duration_seconds: float
    stdout: str
    stderr: str
    docker_command: list[str]


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
) -> list[str]:
    mount_args = ["-v", f"{workspace.resolve()}:/workspace"]
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

    return [
        docker_binary,
        "run",
        "--rm",
        "--cpus=4",
        *mount_args,
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


def execute_check(
    check: CheckDefinition,
    workspace: Path,
    docker_binary: str,
) -> CheckResult:
    docker_command = build_docker_command(check, workspace, docker_binary)
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
        status = "passed" if completed.returncode == 0 else "failed"
        return CheckResult(
            label=check.label,
            status=status,
            returncode=completed.returncode,
            duration_seconds=time.monotonic() - started,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
            docker_command=docker_command,
        )
    except subprocess.TimeoutExpired as exc:
        return CheckResult(
            label=check.label,
            status="timed_out",
            returncode=124,
            duration_seconds=time.monotonic() - started,
            stdout=normalize_process_output(exc.stdout),
            stderr=normalize_process_output(exc.stderr),
            docker_command=docker_command,
        )


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
