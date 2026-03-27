#!/usr/bin/env python3
"""Resolve controller-local run namespaces for mutable execution artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from session_workspace import resolve_session_workspace


@dataclass(frozen=True)
class RunNamespace:
    run_id: str
    run_slug: str
    checkout_root: str
    root: str
    ansible_dir: str
    ansible_tmp_dir: str
    ansible_retry_dir: str
    ansible_control_path_dir: str
    tofu_dir: str
    rendered_dir: str
    logs_dir: str
    receipts_dir: str
    ansible_log_path: str


def resolve_run_namespace(
    *,
    repo_root: Path,
    run_id: str | None = None,
) -> RunNamespace:
    requested_run_id = (
        run_id
        or os.environ.get("LV3_RUN_ID", "").strip()
        or os.environ.get("RUN_ID", "").strip()
        or None
    )
    session = resolve_session_workspace(repo_root=repo_root, session_id=requested_run_id)
    checkout_root = Path(session.checkout_root)
    root = checkout_root / ".local" / "runs" / session.session_slug
    ansible_dir = root / "ansible"
    logs_dir = root / "logs"
    control_path_key = hashlib.sha256(
        f"{checkout_root}:{session.session_slug}".encode("utf-8")
    ).hexdigest()[:12]
    control_path_dir = Path("/tmp") / "lv3-acp" / control_path_key
    return RunNamespace(
        run_id=session.session_id,
        run_slug=session.session_slug,
        checkout_root=str(checkout_root),
        root=str(root),
        ansible_dir=str(ansible_dir),
        ansible_tmp_dir=str(ansible_dir / "tmp"),
        ansible_retry_dir=str(ansible_dir / "retry"),
        ansible_control_path_dir=str(control_path_dir),
        tofu_dir=str(root / "tofu"),
        rendered_dir=str(root / "rendered"),
        logs_dir=str(logs_dir),
        receipts_dir=str(root / "receipts"),
        ansible_log_path=str(logs_dir / "ansible.log"),
    )


def ensure_run_namespace(namespace: RunNamespace) -> RunNamespace:
    for path in (
        namespace.root,
        namespace.ansible_dir,
        namespace.ansible_tmp_dir,
        namespace.ansible_retry_dir,
        namespace.ansible_control_path_dir,
        namespace.tofu_dir,
        namespace.rendered_dir,
        namespace.logs_dir,
        namespace.receipts_dir,
    ):
        Path(path).mkdir(parents=True, exist_ok=True)
    return namespace


def shell_lines(namespace: RunNamespace) -> str:
    payload = {
        "LV3_RUN_ID": namespace.run_id,
        "LV3_RUN_SLUG": namespace.run_slug,
        "LV3_RUN_NAMESPACE_ROOT": namespace.root,
        "LV3_RUN_ANSIBLE_DIR": namespace.ansible_dir,
        "LV3_RUN_ANSIBLE_TMP_DIR": namespace.ansible_tmp_dir,
        "LV3_RUN_ANSIBLE_RETRY_DIR": namespace.ansible_retry_dir,
        "LV3_RUN_ANSIBLE_CONTROL_PATH_DIR": namespace.ansible_control_path_dir,
        "LV3_RUN_TOFU_DIR": namespace.tofu_dir,
        "LV3_RUN_RENDERED_DIR": namespace.rendered_dir,
        "LV3_RUN_LOGS_DIR": namespace.logs_dir,
        "LV3_RUN_RECEIPTS_DIR": namespace.receipts_dir,
        "LV3_RUN_ANSIBLE_LOG_PATH": namespace.ansible_log_path,
    }
    return "\n".join(f"{key}={json.dumps(value)}" for key, value in payload.items())


def make_lines(namespace: RunNamespace) -> str:
    payload = {
        "RUN_NAMESPACE_SLUG": namespace.run_slug,
        "RUN_NAMESPACE_ROOT": namespace.root,
        "RUN_NAMESPACE_ANSIBLE_DIR": namespace.ansible_dir,
        "RUN_NAMESPACE_ANSIBLE_TMP_DIR": namespace.ansible_tmp_dir,
        "RUN_NAMESPACE_ANSIBLE_RETRY_DIR": namespace.ansible_retry_dir,
        "RUN_NAMESPACE_ANSIBLE_CONTROL_PATH_DIR": namespace.ansible_control_path_dir,
        "RUN_NAMESPACE_TOFU_DIR": namespace.tofu_dir,
        "RUN_NAMESPACE_RENDERED_DIR": namespace.rendered_dir,
        "RUN_NAMESPACE_LOGS_DIR": namespace.logs_dir,
        "RUN_NAMESPACE_RECEIPTS_DIR": namespace.receipts_dir,
        "RUN_NAMESPACE_ANSIBLE_LOG_PATH": namespace.ansible_log_path,
    }
    return "\n".join(f"{key} := {value}" for key, value in payload.items())


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository path or any path inside the checkout.",
    )
    parser.add_argument(
        "--run-id",
        help="Explicit run identifier. Defaults to LV3_RUN_ID/RUN_ID or the session workspace id.",
    )
    parser.add_argument(
        "--ensure",
        action="store_true",
        help="Create the namespace directories before printing the result.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "shell", "make"),
        default="json",
        help="Output format.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    namespace = resolve_run_namespace(repo_root=args.repo_root, run_id=args.run_id)
    if args.ensure:
        namespace = ensure_run_namespace(namespace)
    if args.format == "shell":
        print(shell_lines(namespace))
    elif args.format == "make":
        print(make_lines(namespace))
    else:
        print(json.dumps(asdict(namespace), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
