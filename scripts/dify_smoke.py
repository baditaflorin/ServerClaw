#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from dify_api import DifyClient, read_secret
from sync_tools_to_dify import sync_tool_provider


SMOKE_WORKFLOW_NAME = "lv3-dify-smoke"
MINIMAL_WORKFLOW_DSL = """version: "0.6.0"
kind: app
app:
  name: lv3-dify-smoke
  mode: workflow
workflow:
  graph:
    nodes: []
  features: {}
"""


def candidate_repo_roots(repo_root: Path) -> list[Path]:
    candidates = [repo_root]
    git_dir = repo_root / ".git"
    if git_dir.is_file():
        gitdir_line = next(
            (line for line in git_dir.read_text(encoding="utf-8").splitlines() if line.startswith("gitdir: ")),
            None,
        )
        if gitdir_line:
            common_root = (Path(gitdir_line.removeprefix("gitdir: ").strip()).resolve().parents[2]).resolve()
            if common_root not in candidates:
                candidates.append(common_root)
    return candidates


def maybe_langfuse_trace_config(repo_root: Path) -> dict[str, str] | None:
    public_key: Path | None = None
    secret_key: Path | None = None
    config_root = repo_root
    for candidate_root in candidate_repo_roots(repo_root):
        local_dir = candidate_root / ".local" / "langfuse"
        candidate_public_key = local_dir / "project-public-key.txt"
        candidate_secret_key = local_dir / "project-secret-key.txt"
        if candidate_public_key.exists() and candidate_secret_key.exists():
            public_key = candidate_public_key
            secret_key = candidate_secret_key
            config_root = candidate_root
            break
    if not public_key or not secret_key:
        return None
    platform_vars_path = config_root / "inventory" / "group_vars" / "platform.yml"
    langfuse_host = "https://langfuse.lv3.org"
    if platform_vars_path.exists():
        platform_vars = yaml.safe_load(platform_vars_path.read_text(encoding="utf-8")) or {}
        langfuse_host = (
            (
                platform_vars.get("platform_service_topology", {})
                .get("langfuse", {})
                .get("urls", {})
                .get("internal")
            )
            or langfuse_host
        )
    return {
        "public_key": public_key.read_text(encoding="utf-8").strip(),
        "secret_key": secret_key.read_text(encoding="utf-8").strip(),
        "host": langfuse_host,
    }


def ensure_smoke_app(client: DifyClient) -> dict[str, Any]:
    imported = client.import_yaml(
        yaml_content=MINIMAL_WORKFLOW_DSL,
        name=SMOKE_WORKFLOW_NAME,
        description="Repo-managed ADR 0197 smoke workflow",
    )
    if imported.get("app_id"):
        return imported
    import_id = imported.get("id") or imported.get("import_id")
    if not import_id:
        raise RuntimeError(f"unexpected Dify import response: {imported}")
    confirmed = client.confirm_import(str(import_id))
    if not confirmed.get("app_id"):
        raise RuntimeError(f"unexpected Dify import confirmation response: {confirmed}")
    return confirmed


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Dify setup, tool sync, import/export, and tracing.")
    parser.add_argument("--base-url", required=True, help="Public Dify base URL")
    parser.add_argument("--admin-email", required=True, help="Dify admin email")
    parser.add_argument("--admin-name", default="Florin Badita", help="Dify admin name for first-time setup")
    parser.add_argument("--admin-password-file", required=True, help="Path to the Dify admin password file")
    parser.add_argument("--init-password-file", help="Optional path to the Dify init-validation password file")
    parser.add_argument("--tools-api-key-file", help="Optional path to the Dify tools gateway API key file")
    parser.add_argument("--gateway-base-url", default="https://api.lv3.org", help="Platform API gateway base URL")
    parser.add_argument("--provider-name", default="lv3_platform", help="Dify API tool provider name")
    parser.add_argument(
        "--export-path",
        default="platform/dify-workflows/lv3-dify-smoke.yml",
        help="Path to write the exported workflow DSL",
    )
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]), help="Repo root")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    admin_password = read_secret(args.admin_password_file)
    init_password = read_secret(args.init_password_file) if args.init_password_file else None

    client = DifyClient(args.base_url)
    client.setup(
        email=args.admin_email,
        name=args.admin_name,
        password=admin_password,
        init_password=init_password,
    )
    login_payload = client.login(email=args.admin_email, password=admin_password)

    tool_sync_summary: dict[str, Any] | None = None
    if args.tools_api_key_file:
        tool_sync_summary = sync_tool_provider(
            client,
            provider_name=args.provider_name,
            gateway_base_url=args.gateway_base_url,
            tools_api_key=read_secret(args.tools_api_key_file),
        )

    app_payload = ensure_smoke_app(client)
    app_id = str(app_payload["app_id"])

    trace_summary: dict[str, Any] | None = None
    langfuse_trace_config = maybe_langfuse_trace_config(repo_root)
    if langfuse_trace_config:
        client.upsert_trace_config(app_id, provider="langfuse", config=langfuse_trace_config)
        trace_summary = client.get_trace_config(app_id, provider="langfuse")

    exported = client.export_app(app_id)
    export_path = (repo_root / args.export_path).resolve()
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(exported.rstrip() + "\n", encoding="utf-8")

    summary = {
        "setup_step": client.setup_status().get("step"),
        "login_result": login_payload.get("result"),
        "app_id": app_id,
        "tool_provider": tool_sync_summary["action"] if tool_sync_summary else "skipped",
        "tool_count": tool_sync_summary["tool_count"] if tool_sync_summary else 0,
        "trace_configured": bool(trace_summary),
        "export_path": str(export_path.relative_to(repo_root)),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
