#!/usr/bin/env python3

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from controller_automation_toolkit import REPO_ROOT, emit_cli_error, shared_repo_path


DEFAULT_TOKEN_FILE = shared_repo_path(".local", "gitea", "admin-token.txt")
DEFAULT_OWNER = "ops"
DEFAULT_REPOSITORY = "proxmox_florin_server"
DEFAULT_SOURCE_REF = "HEAD"
DEFAULT_TARGET_REF = "main"
DEFAULT_GITEA_URL = "http://100.64.0.1:3009"
TEMP_REF_PREFIX = "refs/tmp/gitea-publish"


def read_token(path: Path) -> str:
    token = path.read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError(f"{path} is empty")
    return token


def git_commit_for_ref(source_ref: str) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", f"{source_ref}^{{commit}}"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(completed.stderr.strip() or f"unable to resolve git ref '{source_ref}'")
    return completed.stdout.strip()


def git_tree_for_ref(source_ref: str) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", f"{source_ref}^{{tree}}"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(completed.stderr.strip() or f"unable to resolve tree for git ref '{source_ref}'")
    return completed.stdout.strip()


def build_remote_url(base_url: str, owner: str, repository: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Gitea URL must use http or https")
    if not parsed.netloc:
        raise ValueError("Gitea URL must include a hostname")
    return urllib.parse.urlunparse(
        parsed._replace(path=f"/{owner}/{repository}.git", params="", query="", fragment="")
    )


def authenticated_git_env(token: str) -> dict[str, str]:
    auth_header = base64.b64encode(f"ops-gitea:{token}".encode("utf-8")).decode("ascii")
    env = dict(os.environ)
    env.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.extraHeader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Basic {auth_header}",
        }
    )
    return env


def fetch_remote_target_ref(remote_url: str, target_ref: str, env: dict[str, str]) -> str | None:
    remote_ref = f"refs/heads/{target_ref}"
    ls_remote = subprocess.run(
        ["git", "ls-remote", "--exit-code", remote_url, remote_ref],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if ls_remote.returncode != 0:
        return None

    temp_ref = f"{TEMP_REF_PREFIX}/{target_ref}"
    fetch = subprocess.run(
        [
            "git",
            "fetch",
            "--quiet",
            remote_url,
            f"{remote_ref}:{temp_ref}",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if fetch.returncode != 0:
        raise RuntimeError(fetch.stderr.strip() or fetch.stdout.strip() or "git fetch failed")
    return temp_ref


def delete_ref(ref_name: str | None) -> None:
    if not ref_name:
        return
    subprocess.run(
        ["git", "update-ref", "-d", ref_name],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def build_snapshot_commit(
    *,
    source_ref: str,
    source_commit: str,
    parent_ref: str | None = None,
) -> str:
    tree = git_tree_for_ref(source_ref)
    command = ["git", "commit-tree", tree]
    if parent_ref:
        command.extend(["-p", parent_ref])
    command.extend(
        [
            "-m",
            f"Publish internal Gitea snapshot for {source_commit}",
            "-m",
            f"Source ref: {source_ref}\nSource commit: {source_commit}",
        ]
    )
    env = dict(os.environ)
    env.setdefault("GIT_AUTHOR_NAME", "LV3 Gitea Publisher")
    env.setdefault("GIT_AUTHOR_EMAIL", "ops@lv3.org")
    env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
    env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git commit-tree failed")
    return completed.stdout.strip()


def push_ref(remote_url: str, published_ref: str, target_ref: str, token: str) -> None:
    try:
        env = authenticated_git_env(token)
        temp_ref = fetch_remote_target_ref(remote_url, target_ref, env)
        snapshot_commit = build_snapshot_commit(
            source_ref=published_ref,
            source_commit=git_commit_for_ref(published_ref),
            parent_ref=temp_ref,
        )
        completed = subprocess.run(
            [
                "git",
                "-c",
                "pack.window=0",
                "-c",
                "pack.depth=0",
                "push",
                "--no-verify",
                remote_url,
                f"{snapshot_commit}:refs/heads/{target_ref}",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "git push failed")
        return snapshot_commit
    finally:
        delete_ref(locals().get("temp_ref"))


def fetch_repo_tree_entry(base_url: str, owner: str, repository: str, path: str, ref: str, token: str) -> dict:
    encoded_ref = urllib.parse.quote(ref)
    url = f"{base_url}/api/v1/repos/{owner}/{repository}/git/trees/{encoded_ref}?recursive=1"
    request = urllib.request.Request(url, headers={"Authorization": f"token {token}"})
    with urllib.request.urlopen(request) as response:
        payload = json.load(response)

    for entry in payload.get("tree", []):
        if entry.get("path") == path:
            return entry
    raise FileNotFoundError(f"{path} was not found in {owner}/{repository}@{ref}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish the current repo ref into the managed internal Gitea repository.")
    parser.add_argument("--gitea-url", default=DEFAULT_GITEA_URL)
    parser.add_argument("--owner", default=DEFAULT_OWNER)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--source-ref", default=DEFAULT_SOURCE_REF)
    parser.add_argument("--target-ref", default=DEFAULT_TARGET_REF)
    parser.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN_FILE)
    parser.add_argument(
        "--verify-path",
        default=".gitea/workflows/renovate.yml",
        help="Repository path to verify via the Gitea contents API after the push completes.",
    )
    args = parser.parse_args()

    try:
        source_commit = git_commit_for_ref(args.source_ref)
        token = read_token(args.token_file)
        remote_url = build_remote_url(args.gitea_url, args.owner, args.repository)
        published_commit = push_ref(remote_url, args.source_ref, args.target_ref, token)
        verified = fetch_repo_tree_entry(
            args.gitea_url.rstrip("/"),
            args.owner,
            args.repository,
            args.verify_path,
            args.target_ref,
            token,
        )
    except (OSError, ValueError, RuntimeError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return emit_cli_error("Publish Gitea repo", exc)

    print(
        json.dumps(
            {
                "source_ref": args.source_ref,
                "source_commit": source_commit,
                "published_commit": published_commit,
                "target_ref": args.target_ref,
                "remote_url": remote_url,
                "verified_path": args.verify_path,
                "verified_sha": verified.get("sha"),
                "verified_type": verified.get("type"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
