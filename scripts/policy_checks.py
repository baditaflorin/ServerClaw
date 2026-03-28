#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from platform.policy.toolchain import PolicyToolchain, ensure_policy_toolchain


POLICY_DIR = REPO_ROOT / "policy"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_repository_context(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    return {
        "command_catalog": load_json(repo_root / "config" / "command-catalog.json"),
        "workflow_catalog": load_json(repo_root / "config" / "workflow-catalog.json"),
        "service_catalog": load_json(repo_root / "config" / "service-capability-catalog.json"),
        "validation_gate": load_json(repo_root / "config" / "validation-gate.json"),
        "check_runner_manifest": load_json(repo_root / "config" / "check-runner-manifest.json"),
    }


def _run(command: list[str], *, cwd: Path, input_text: str | None = None) -> None:
    result = subprocess.run(
        command,
        cwd=cwd,
        input=input_text.encode("utf-8") if input_text is not None else None,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return
    stdout = result.stdout.decode("utf-8", errors="replace").strip()
    stderr = result.stderr.decode("utf-8", errors="replace").strip()
    details = "\n".join(
        part for part in [stdout, stderr] if part
    ).strip()
    if not details:
        details = f"command exited with status {result.returncode}"
    raise RuntimeError(f"{' '.join(command)} failed:\n{details}")


def run_opa_tests(repo_root: Path, toolchain: PolicyToolchain) -> None:
    _run(
        [
            str(toolchain.opa.path),
            "test",
            str(repo_root / "policy"),
        ],
        cwd=repo_root,
    )


def run_conftest_checks(repo_root: Path, toolchain: PolicyToolchain) -> None:
    context = build_repository_context(repo_root)
    with tempfile.TemporaryDirectory(prefix="lv3-policy-context-") as tmp_dir:
        context_path = Path(tmp_dir) / "repository-context.json"
        context_path.write_text(json.dumps(context, indent=2, sort_keys=True), encoding="utf-8")
        _run(
            [
                str(toolchain.conftest.path),
                "test",
                str(context_path),
                "--policy",
                str(repo_root / "policy" / "conftest"),
            ],
            cwd=repo_root,
        )


def validate_repository_policies(
    repo_root: Path = REPO_ROOT,
    *,
    toolchain: PolicyToolchain | None = None,
) -> None:
    effective_toolchain = toolchain or ensure_policy_toolchain(repo_root=repo_root)
    run_opa_tests(repo_root, effective_toolchain)
    run_conftest_checks(repo_root, effective_toolchain)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ADR 0230 OPA and Conftest validations.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root to validate.")
    parser.add_argument(
        "--write-context",
        type=Path,
        help="Write the consolidated repository context JSON to this path and exit.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run OPA unit tests plus Conftest repository checks.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo_root = args.repo_root.resolve()

    if args.write_context:
        context = build_repository_context(repo_root)
        args.write_context.write_text(json.dumps(context, indent=2, sort_keys=True), encoding="utf-8")
        print(args.write_context)
        return 0

    validate_repository_policies(repo_root)
    print(f"ADR 0230 policy checks OK: {repo_root / 'policy'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
