#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from controller_automation_toolkit import emit_cli_error, repo_path, write_json, load_operator_auth
from platform.ansible.woodpecker import (
    GiteaClient,
    GiteaError,
    WoodpeckerClient,
    WoodpeckerError,
    WoodpeckerSessionClient,
)


DEFAULT_AUTH_FILE = repo_path(".local", "woodpecker", "admin-auth.json")


def load_text(path: str | None) -> str | None:
    if not path:
        return None
    resolved = Path(path).expanduser()
    if not resolved.exists():
        return None
    return resolved.read_text(encoding="utf-8").strip()


def persist_auth(auth_file: str, auth: dict) -> None:
    resolved = Path(auth_file).expanduser()
    write_json(resolved, auth, mode=0o600)
    token_file = auth.get("api_token_file")
    if isinstance(token_file, str) and token_file.strip() and auth.get("api_token"):
        token_path = Path(token_file).expanduser()
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(str(auth["api_token"]).strip() + "\n", encoding="utf-8")
        token_path.chmod(0o600)


def build_client(auth_file: str) -> tuple[WoodpeckerClient, dict]:
    auth = load_operator_auth(auth_file)
    base_url = str(auth["base_url"]).rstrip("/")
    login_base_url = str(auth.get("login_base_url") or auth.get("public_url") or base_url).rstrip("/")
    verify_ssl = bool(auth.get("verify_ssl", True))
    login_verify_ssl = bool(auth.get("login_verify_ssl", True))
    api_token = str(auth.get("api_token", "")).strip()

    if api_token:
        client = WoodpeckerClient(base_url, api_token, verify_ssl=verify_ssl)
        if client.verify_api_token():
            return client, auth
        public_client = WoodpeckerClient(login_base_url, api_token, verify_ssl=login_verify_ssl)
        if public_client.verify_api_token():
            auth["base_url"] = login_base_url
            persist_auth(auth_file, auth)
            return public_client, auth

    username = str(auth.get("username", "")).strip()
    password = load_text(auth.get("password_file"))
    if not username or not password:
        raise WoodpeckerError("The Woodpecker auth file does not contain a usable username and password file")

    session = WoodpeckerSessionClient(
        login_base_url,
        verify_ssl=login_verify_ssl,
        redirect_fallback_base_url=str(auth.get("gitea_api_url") or "").strip() or None,
    )
    session.login_via_gitea(username, password)
    api_token = session.create_user_token()
    auth["api_token"] = api_token
    persist_auth(auth_file, auth)

    client = WoodpeckerClient(base_url, api_token, verify_ssl=verify_ssl)
    if client.verify_api_token():
        return client, auth
    public_client = WoodpeckerClient(login_base_url, api_token, verify_ssl=login_verify_ssl)
    if public_client.verify_api_token():
        auth["base_url"] = login_base_url
        persist_auth(auth_file, auth)
        return public_client, auth
    raise WoodpeckerError("The refreshed Woodpecker API token is not valid on the configured endpoints")


def repository_for_action(client: WoodpeckerClient, auth: dict, repo_name: str | None) -> dict:
    full_name = (repo_name or auth.get("repo_full_name") or "").strip()
    if not full_name:
        raise WoodpeckerError("Repository name is required for this action")
    repo = client.lookup_repository(full_name)
    if repo is None:
        raise WoodpeckerError(f"Woodpecker repository is not activated: {full_name}")
    return repo


def command_whoami(args) -> int:
    client, auth = build_client(args.auth_file)
    payload = client.get_user()
    payload["base_url"] = auth["base_url"]
    payload["repo_full_name"] = auth.get("repo_full_name")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_list_repos(args) -> int:
    client, _auth = build_client(args.auth_file)
    payload = client.list_user_repositories(include_inactive=args.all, name=args.name)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_activate_repo(args) -> int:
    client, auth = build_client(args.auth_file)
    full_name = (args.name or auth.get("repo_full_name") or "").strip()
    if not full_name:
        raise WoodpeckerError("Repository full name is required")
    existing = client.lookup_repository(full_name)
    if existing is not None:
        print(json.dumps(existing, indent=2, sort_keys=True))
        return 0
    gitea_url = str(auth.get("gitea_api_url", "")).strip()
    gitea_token = load_text(auth.get("gitea_api_token_file"))
    if not gitea_url or not gitea_token:
        raise WoodpeckerError("The Woodpecker auth file does not contain a usable Gitea API URL and token file")
    gitea_client = GiteaClient(gitea_url, gitea_token, verify_ssl=bool(auth.get("login_verify_ssl", True)))
    gitea_repo = gitea_client.get_repository(full_name)
    payload = client.activate_repository(gitea_repo["id"])
    payload = client.lookup_repository(full_name) or payload
    auth["repo_full_name"] = full_name
    auth["repo_id"] = int(payload["id"])
    persist_auth(args.auth_file, auth)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_list_secrets(args) -> int:
    client, auth = build_client(args.auth_file)
    repo = repository_for_action(client, auth, args.repo)
    print(json.dumps(client.list_repository_secrets(int(repo["id"])), indent=2, sort_keys=True))
    return 0


def command_upsert_secret(args) -> int:
    client, auth = build_client(args.auth_file)
    repo = repository_for_action(client, auth, args.repo)
    value = args.value or load_text(args.value_file)
    if value is None:
        raise WoodpeckerError("A secret value or value file is required")
    events = [item.strip() for item in args.events.split(",") if item.strip()]
    images = [item.strip() for item in args.images.split(",") if item.strip()]
    payload = client.ensure_repository_secret(
        int(repo["id"]),
        name=args.name,
        value=value,
        events=events or None,
        images=images or None,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_list_pipelines(args) -> int:
    client, auth = build_client(args.auth_file)
    repo = repository_for_action(client, auth, args.repo)
    payload = client.list_pipelines(int(repo["id"]), branch=args.branch)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _pipeline_number(payload: dict | None) -> int | None:
    if not isinstance(payload, dict):
        return None
    number = payload.get("number")
    if number is None:
        return None
    return int(number)


def _discover_triggered_pipeline(
    client: WoodpeckerClient,
    repo_id: int,
    *,
    branch: str,
    timeout_seconds: int,
    poll_seconds: int,
    baseline: list[dict],
) -> dict:
    known_numbers = {
        int(item["number"]) for item in baseline if isinstance(item, dict) and item.get("number") is not None
    }
    deadline = time.monotonic() + timeout_seconds
    latest: list[dict] = list(baseline)
    while time.monotonic() < deadline:
        latest = client.list_pipelines(repo_id, branch=branch)
        candidates = [item for item in latest if isinstance(item, dict) and item.get("number") is not None]
        unseen = [item for item in candidates if int(item["number"]) not in known_numbers]
        if unseen:
            return max(unseen, key=lambda item: int(item["number"]))
        time.sleep(poll_seconds)
    raise WoodpeckerError(
        "Woodpecker accepted the manual trigger request but no pipeline run became visible "
        f"for branch {branch!r} within {timeout_seconds} seconds"
    )


def command_trigger_pipeline(args) -> int:
    client, auth = build_client(args.auth_file)
    repo = repository_for_action(client, auth, args.repo)
    baseline = client.list_pipelines(int(repo["id"]), branch=args.branch) if args.wait else []
    payload = client.trigger_pipeline(
        int(repo["id"]),
        branch=args.branch,
        variables=dict(item.split("=", 1) for item in args.variable),
    )
    if args.wait:
        number = _pipeline_number(payload)
        if number is None:
            payload = _discover_triggered_pipeline(
                client,
                int(repo["id"]),
                branch=args.branch,
                timeout_seconds=args.timeout,
                poll_seconds=args.poll_interval,
                baseline=baseline,
            )
            number = _pipeline_number(payload)
        if number is None:
            raise WoodpeckerError("Woodpecker did not return or expose a pipeline number for the triggered run")
        payload = client.wait_for_pipeline(
            int(repo["id"]),
            number,
            timeout_seconds=args.timeout,
            poll_seconds=args.poll_interval,
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        state = str(payload.get("status") or payload.get("state") or "").strip().lower()
        return 0 if state == "success" else 1
    if payload is None:
        payload = {
            "accepted": True,
            "branch": args.branch,
            "repo_id": int(repo["id"]),
            "status": "accepted",
        }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run governed Woodpecker API actions.")
    parser.add_argument("--auth-file", default=str(DEFAULT_AUTH_FILE), help="Path to the Woodpecker auth JSON file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    whoami = subparsers.add_parser("whoami", help="Show the configured Woodpecker identity.")
    whoami.set_defaults(func=command_whoami)

    list_repos = subparsers.add_parser(
        "list-repos", help="List Woodpecker repositories visible to the configured user."
    )
    list_repos.add_argument("--all", action="store_true", help="Include inactive repositories.")
    list_repos.add_argument("--name", help="Optional repository-name filter.")
    list_repos.set_defaults(func=command_list_repos)

    activate = subparsers.add_parser(
        "activate-repo", help="Activate one repository in Woodpecker using the configured Gitea admin token."
    )
    activate.add_argument("--name", help="Repository in owner/name form.")
    activate.set_defaults(func=command_activate_repo)

    list_secrets = subparsers.add_parser("list-secrets", help="List Woodpecker secrets for one repository.")
    list_secrets.add_argument("--repo", help="Repository in owner/name form.")
    list_secrets.set_defaults(func=command_list_secrets)

    upsert_secret = subparsers.add_parser("upsert-secret", help="Create or update one Woodpecker repository secret.")
    upsert_secret.add_argument("--repo", help="Repository in owner/name form.")
    upsert_secret.add_argument("--name", required=True, help="Secret name.")
    upsert_secret.add_argument("--value", help="Secret value.")
    upsert_secret.add_argument("--value-file", help="Path to the secret value file.")
    upsert_secret.add_argument(
        "--events", default="push,pull_request,manual", help="Comma-separated Woodpecker secret event list."
    )
    upsert_secret.add_argument("--images", default="", help="Optional comma-separated image selector list.")
    upsert_secret.set_defaults(func=command_upsert_secret)

    list_pipelines = subparsers.add_parser("list-pipelines", help="List pipelines for one repository.")
    list_pipelines.add_argument("--repo", help="Repository in owner/name form.")
    list_pipelines.add_argument("--branch", help="Optional branch filter.")
    list_pipelines.set_defaults(func=command_list_pipelines)

    trigger = subparsers.add_parser("trigger-pipeline", help="Trigger one manual pipeline and optionally wait for it.")
    trigger.add_argument("--repo", help="Repository in owner/name form.")
    trigger.add_argument("--branch", required=True, help="Branch to run.")
    trigger.add_argument(
        "--variable", action="append", default=[], help="Optional key=value variable passed to the pipeline."
    )
    trigger.add_argument("--wait", action="store_true", help="Wait for the pipeline to finish.")
    trigger.add_argument("--timeout", type=int, default=900, help="Maximum wait time in seconds.")
    trigger.add_argument("--poll-interval", type=int, default=5, help="Polling interval in seconds.")
    trigger.set_defaults(func=command_trigger_pipeline)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, KeyError, ValueError, GiteaError, WoodpeckerError, json.JSONDecodeError) as exc:
        return emit_cli_error("Woodpecker", exc)


if __name__ == "__main__":
    raise SystemExit(main())
