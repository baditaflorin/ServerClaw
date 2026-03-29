from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


SESSION_BASE_DIRNAME = ".lv3-session-workspaces"
LOCAL_STATE_DIRNAME = "session-workspaces"


@dataclass(frozen=True)
class SessionWorkspace:
    session_id: str
    session_slug: str
    checkout_root: str
    local_state_root: str
    nats_prefix: str
    state_namespace: str
    receipt_suffix: str
    remote_workspace_root: str | None = None


def _git_toplevel(path: Path) -> Path:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return path.resolve()
    resolved = completed.stdout.strip()
    return Path(resolved).resolve() if resolved else path.resolve()


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return normalized or "session"


def _stable_session_id(checkout_root: Path) -> str:
    digest = hashlib.sha1(str(checkout_root.resolve()).encode("utf-8")).hexdigest()[:10]
    return f"{checkout_root.name}-{digest}"


def resolve_session_workspace(
    *,
    repo_root: Path,
    remote_workspace_base: Path | None = None,
    session_id: str | None = None,
) -> SessionWorkspace:
    checkout_root = _git_toplevel(repo_root)
    requested_session_id = session_id or os.environ.get("LV3_SESSION_ID", "").strip() or _stable_session_id(checkout_root)
    session_slug = _slugify(requested_session_id)
    local_state_root = checkout_root / ".local" / LOCAL_STATE_DIRNAME / session_slug
    remote_workspace_root = None
    if remote_workspace_base is not None:
        remote_workspace_root = str(remote_workspace_base / SESSION_BASE_DIRNAME / session_slug / "repo")
    return SessionWorkspace(
        session_id=requested_session_id,
        session_slug=session_slug,
        checkout_root=str(checkout_root),
        local_state_root=str(local_state_root),
        nats_prefix=f"platform.ws.{session_slug}",
        state_namespace=f"ws:{session_slug}",
        receipt_suffix=session_slug,
        remote_workspace_root=remote_workspace_root,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository path or any path inside the checkout.",
    )
    parser.add_argument(
        "--remote-workspace-base",
        type=Path,
        help="Optional remote base directory that should receive a session-scoped repo checkout.",
    )
    parser.add_argument(
        "--session-id",
        help="Explicit session identifier. Defaults to LV3_SESSION_ID or a stable checkout-derived id.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "shell"),
        default="json",
        help="Output format.",
    )
    return parser.parse_args(argv)


def shell_lines(workspace: SessionWorkspace) -> str:
    payload = {
        "LV3_SESSION_ID": workspace.session_id,
        "LV3_SESSION_SLUG": workspace.session_slug,
        "LV3_SESSION_LOCAL_ROOT": workspace.local_state_root,
        "LV3_SESSION_NATS_PREFIX": workspace.nats_prefix,
        "LV3_SESSION_STATE_NAMESPACE": workspace.state_namespace,
        "LV3_SESSION_RECEIPT_SUFFIX": workspace.receipt_suffix,
    }
    if workspace.remote_workspace_root is not None:
        payload["LV3_REMOTE_WORKSPACE_ROOT"] = workspace.remote_workspace_root
    return "\n".join(f"{key}={json.dumps(value)}" for key, value in payload.items())


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    workspace = resolve_session_workspace(
        repo_root=args.repo_root,
        remote_workspace_base=args.remote_workspace_base,
        session_id=args.session_id,
    )
    if args.format == "shell":
        print(shell_lines(workspace))
    else:
        print(json.dumps(asdict(workspace), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
