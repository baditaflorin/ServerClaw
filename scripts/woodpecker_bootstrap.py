#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from controller_automation_toolkit import emit_cli_error, write_json
from platform.ansible.woodpecker import (
    GiteaClient,
    GiteaError,
    WoodpeckerError,
    bootstrap_woodpecker,
    ensure_gitea_oauth_application,
)


def load_text(path: str | None) -> str | None:
    if not path:
        return None
    resolved = Path(path).expanduser()
    if not resolved.exists():
        return None
    return resolved.read_text(encoding="utf-8").strip()


def write_secret_file(path: str, value: str) -> None:
    resolved = Path(path).expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(value.rstrip("\n") + "\n", encoding="utf-8")
    resolved.chmod(0o600)


def command_prepare_oauth(args) -> int:
    api_token = load_text(args.token_file)
    if not api_token:
        raise ValueError(f"Missing Gitea API token in {args.token_file}")
    existing_client_id = load_text(args.existing_client_id_file)
    existing_client_secret = load_text(args.existing_client_secret_file)
    client = GiteaClient(args.gitea_url, api_token, verify_ssl=args.verify_ssl)
    payload = ensure_gitea_oauth_application(
        client,
        name=args.app_name,
        redirect_uri=args.redirect_uri,
        existing_client_id=existing_client_id,
        existing_client_secret=existing_client_secret,
    )
    write_secret_file(args.client_id_output, payload["client_id"])
    write_secret_file(args.client_secret_output, payload["client_secret"])
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_apply(args) -> int:
    gitea_password = load_text(args.password_file)
    if not gitea_password:
        raise ValueError(f"Missing Gitea password in {args.password_file}")
    gitea_api_token = load_text(args.gitea_token_file)
    if not gitea_api_token:
        raise ValueError(f"Missing Gitea API token in {args.gitea_token_file}")
    spec = json.loads(Path(args.spec_file).expanduser().read_text(encoding="utf-8"))
    existing_api_token = load_text(args.existing_token_file)
    secret_spec = spec.get("secret", {})

    summary = bootstrap_woodpecker(
        controller_base_url=args.base_url,
        login_base_url=args.login_base_url,
        gitea_api_url=args.gitea_url,
        gitea_api_token=gitea_api_token,
        gitea_username=args.username,
        gitea_password=gitea_password,
        repo_full_name=spec["repo"]["full_name"],
        secret_name=secret_spec.get("name"),
        secret_value=load_text(secret_spec.get("value_file")),
        secret_events=list(secret_spec.get("events") or ["push", "pull_request", "manual"]),
        verify_ssl=args.verify_ssl,
        login_verify_ssl=args.login_verify_ssl,
        existing_api_token=existing_api_token,
    )

    auth_payload = {
        "base_url": args.base_url.rstrip("/"),
        "login_base_url": args.login_base_url.rstrip("/"),
        "public_url": args.login_base_url.rstrip("/"),
        "gitea_api_url": args.gitea_url.rstrip("/"),
        "gitea_api_token_file": str(Path(args.gitea_token_file).expanduser()),
        "username": args.username,
        "password_file": str(Path(args.password_file).expanduser()),
        "api_token": summary.api_token,
        "api_token_file": str(Path(args.api_token_output).expanduser()),
        "verify_ssl": args.verify_ssl,
        "login_verify_ssl": args.login_verify_ssl,
        "repo_full_name": spec["repo"]["full_name"],
        "repo_id": int(summary.repo["id"]),
    }
    write_json(Path(args.auth_json_output).expanduser(), auth_payload, mode=0o600)
    write_secret_file(args.api_token_output, summary.api_token)
    print(json.dumps(auth_payload, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap and manage the repo-owned Woodpecker CI control plane.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare-oauth", help="Create or reconcile the Gitea OAuth application used by Woodpecker.")
    prepare.add_argument("--gitea-url", required=True, help="Gitea API base URL.")
    prepare.add_argument("--token-file", required=True, help="Path to the Gitea admin API token file.")
    prepare.add_argument("--app-name", required=True, help="Gitea OAuth application name.")
    prepare.add_argument("--redirect-uri", required=True, help="Redirect URI registered for Woodpecker.")
    prepare.add_argument("--client-id-output", required=True, help="Path to write the OAuth client id.")
    prepare.add_argument("--client-secret-output", required=True, help="Path to write the OAuth client secret.")
    prepare.add_argument("--existing-client-id-file", help="Optional existing local client id file to preserve when possible.")
    prepare.add_argument("--existing-client-secret-file", help="Optional existing local client secret file to preserve when possible.")
    prepare.add_argument("--verify-ssl", action="store_true", help="Verify TLS certificates for the Gitea API.")
    prepare.set_defaults(func=command_prepare_oauth)

    apply_cmd = subparsers.add_parser("apply", help="Login to Woodpecker through Gitea, create the governed API token, and activate the seed repository.")
    apply_cmd.add_argument("--base-url", required=True, help="Controller-facing Woodpecker base URL.")
    apply_cmd.add_argument("--login-base-url", required=True, help="User-facing Woodpecker base URL used for the Gitea login flow.")
    apply_cmd.add_argument("--gitea-url", required=True, help="Gitea API base URL.")
    apply_cmd.add_argument("--username", required=True, help="Gitea username to log into Woodpecker.")
    apply_cmd.add_argument("--password-file", required=True, help="Path to the Gitea password file.")
    apply_cmd.add_argument("--gitea-token-file", required=True, help="Path to the Gitea admin API token file.")
    apply_cmd.add_argument("--spec-file", required=True, help="Path to the JSON bootstrap specification.")
    apply_cmd.add_argument("--existing-token-file", help="Optional existing Woodpecker API token file to reuse when valid.")
    apply_cmd.add_argument("--auth-json-output", required=True, help="Path to the persisted Woodpecker auth JSON file.")
    apply_cmd.add_argument("--api-token-output", required=True, help="Path to the persisted Woodpecker API token file.")
    apply_cmd.add_argument("--verify-ssl", action="store_true", help="Verify TLS certificates for the controller-facing Woodpecker API.")
    apply_cmd.add_argument("--login-verify-ssl", action="store_true", help="Verify TLS certificates for the public Woodpecker login flow.")
    apply_cmd.set_defaults(func=command_apply)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, GiteaError, WoodpeckerError, json.JSONDecodeError) as exc:
        raise SystemExit(emit_cli_error("Woodpecker bootstrap", exc))
