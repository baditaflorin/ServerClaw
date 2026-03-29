#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, repo_path


REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = repo_path("config", "repo-deploy-catalog.json")
SCHEMA_PATH = repo_path("docs", "schema", "repo-deploy-catalog.schema.json")
SUPPORTED_SCHEMA_VERSION = "1.0.0"
ALLOWED_SOURCES = {"auto", "public", "private-deploy-key"}
ALLOWED_BUILD_PACKS = {"nixpacks", "static", "dockerfile", "dockercompose"}
ALLOWED_LLM_ASSISTANCE = {"allowed", "required", "prohibited"}


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def require_int(value: Any, path: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    if value < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    return value


def load_repo_deploy_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must be a JSON object")
    return payload


def validate_repo_deploy_catalog(payload: dict[str, Any], *, path: Path = CATALOG_PATH) -> None:
    if require_str(payload.get("$schema"), f"{path}.$schema") != "docs/schema/repo-deploy-catalog.schema.json":
        raise ValueError(f"{path}.$schema must reference docs/schema/repo-deploy-catalog.schema.json")
    if require_str(payload.get("schema_version"), f"{path}.schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(f"{path}.schema_version must be {SUPPORTED_SCHEMA_VERSION}")

    profiles = require_list(payload.get("profiles"), f"{path}.profiles")
    if not profiles:
        raise ValueError(f"{path}.profiles must not be empty")

    seen_ids: set[str] = set()
    for index, item in enumerate(profiles):
        profile_path = f"{path}.profiles[{index}]"
        profile = require_mapping(item, profile_path)
        profile_id = require_str(profile.get("id"), f"{profile_path}.id")
        if profile_id in seen_ids:
            raise ValueError(f"{profile_path}.id duplicates '{profile_id}'")
        seen_ids.add(profile_id)

        require_str(profile.get("description"), f"{profile_path}.description")
        require_str(profile.get("repo"), f"{profile_path}.repo")
        require_str(profile.get("branch"), f"{profile_path}.branch")
        source = require_str(profile.get("source"), f"{profile_path}.source")
        if source not in ALLOWED_SOURCES:
            raise ValueError(f"{profile_path}.source must be one of {sorted(ALLOWED_SOURCES)}")
        require_str(profile.get("app_name"), f"{profile_path}.app_name")
        require_str(profile.get("project"), f"{profile_path}.project")
        require_str(profile.get("environment"), f"{profile_path}.environment")
        build_pack = require_str(profile.get("build_pack"), f"{profile_path}.build_pack")
        if build_pack not in ALLOWED_BUILD_PACKS:
            raise ValueError(f"{profile_path}.build_pack must be one of {sorted(ALLOWED_BUILD_PACKS)}")
        require_str(profile.get("ports"), f"{profile_path}.ports")
        llm_assistance = require_str(profile.get("llm_assistance"), f"{profile_path}.llm_assistance")
        if llm_assistance not in ALLOWED_LLM_ASSISTANCE:
            raise ValueError(
                f"{profile_path}.llm_assistance must be one of {sorted(ALLOWED_LLM_ASSISTANCE)}"
            )

        compose_domains = require_list(profile.get("compose_domains", []), f"{profile_path}.compose_domains")
        seen_services: set[str] = set()
        for compose_index, compose_item in enumerate(compose_domains):
            compose_path = f"{profile_path}.compose_domains[{compose_index}]"
            compose_mapping = require_mapping(compose_item, compose_path)
            service_name = require_str(compose_mapping.get("service"), f"{compose_path}.service")
            if service_name in seen_services:
                raise ValueError(f"{compose_path}.service duplicates '{service_name}'")
            seen_services.add(service_name)
            require_str(compose_mapping.get("domain"), f"{compose_path}.domain")

        if build_pack == "dockercompose":
            require_str(profile.get("docker_compose_location"), f"{profile_path}.docker_compose_location")
            if not compose_domains:
                raise ValueError(f"{profile_path}.compose_domains must not be empty for dockercompose profiles")

        verification = profile.get("verification")
        if verification is not None:
            verification = require_mapping(verification, f"{profile_path}.verification")
            require_str(verification.get("url"), f"{profile_path}.verification.url")
            require_str(
                verification.get("activity_count_json_path"),
                f"{profile_path}.verification.activity_count_json_path",
            )
            require_int(
                verification.get("minimum_activity_count"),
                f"{profile_path}.verification.minimum_activity_count",
                1,
            )


def profile_by_id(profile_id: str, *, path: Path = CATALOG_PATH) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = load_repo_deploy_catalog(path)
    validate_repo_deploy_catalog(payload, path=path)
    for profile in payload["profiles"]:
        if profile["id"] == profile_id:
            return payload, profile
    raise KeyError(f"Unknown repo deploy profile '{profile_id}'")


def build_deploy_repo_args(
    profile: dict[str, Any],
    *,
    branch: str | None = None,
    wait: bool = False,
    force: bool = False,
    timeout: int = 900,
    max_deploy_attempts: int = 3,
    retry_delay: int = 15,
) -> list[str]:
    args: list[str] = [
        "--repo",
        str(profile["repo"]),
        "--branch",
        branch or str(profile["branch"]),
        "--source",
        str(profile["source"]),
        "--app-name",
        str(profile["app_name"]),
        "--project",
        str(profile["project"]),
        "--environment",
        str(profile["environment"]),
        "--build-pack",
        str(profile["build_pack"]),
        "--ports",
        str(profile["ports"]),
    ]
    optional_pairs = (
        ("base_directory", "--base-directory"),
        ("description_override", "--description"),
        ("private_key_uuid", "--private-key-uuid"),
        ("deploy_key_name", "--deploy-key-name"),
        ("deploy_key_path", "--deploy-key-path"),
        ("dockerfile_location", "--dockerfile-location"),
        ("docker_compose_location", "--docker-compose-location"),
        ("publish_directory", "--publish-directory"),
    )
    for profile_key, flag in optional_pairs:
        value = str(profile.get(profile_key, "")).strip()
        if value:
            args.extend([flag, value])
    for compose_domain in profile.get("compose_domains", []):
        args.extend(
            [
                "--compose-domain",
                f"{compose_domain['service']}={compose_domain['domain']}",
            ]
        )
    if wait:
        args.append("--wait")
    if force:
        args.append("--force")
    if timeout != 900:
        args.extend(["--timeout", str(timeout)])
    if max_deploy_attempts != 3:
        args.extend(["--max-deploy-attempts", str(max_deploy_attempts)])
    if retry_delay != 15:
        args.extend(["--retry-delay", str(retry_delay)])
    return args


def coolify_tool_command(coolify_args: list[str]) -> list[str]:
    return [
        "uv",
        "run",
        "--with",
        "pyyaml",
        "python",
        str(repo_path("scripts", "coolify_tool.py")),
        "deploy-repo",
        *coolify_args,
    ]


def show_profile(profile_id: str) -> int:
    _, profile = profile_by_id(profile_id)
    payload = {
        "profile": profile,
        "expanded_coolify_args": build_deploy_repo_args(profile),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def deploy_profile(
    profile_id: str,
    *,
    branch: str | None,
    wait: bool,
    force: bool,
    timeout: int,
    max_deploy_attempts: int,
    retry_delay: int,
    dry_run: bool,
) -> int:
    _, profile = profile_by_id(profile_id)
    coolify_args = build_deploy_repo_args(
        profile,
        branch=branch,
        wait=wait,
        force=force,
        timeout=timeout,
        max_deploy_attempts=max_deploy_attempts,
        retry_delay=retry_delay,
    )
    command = coolify_tool_command(coolify_args)
    if dry_run:
        print(json.dumps({"command": command, "profile_id": profile_id}, indent=2, sort_keys=True))
        return 0
    completed = subprocess.run(command, check=False)
    return int(completed.returncode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve named repo-deploy profiles into governed Coolify deploys.")
    subparsers = parser.add_subparsers(dest="action", required=True)

    show = subparsers.add_parser("show", help="Show one named repo-deploy profile and its expanded Coolify arguments.")
    show.add_argument("profile")

    deploy = subparsers.add_parser("deploy", help="Deploy one named repo-deploy profile through Coolify.")
    deploy.add_argument("profile")
    deploy.add_argument("--branch", help="Override the catalog branch.")
    deploy.add_argument("--wait", action="store_true", help="Wait for the deployment result.")
    deploy.add_argument("--force", action="store_true", help="Force a rebuild without cache.")
    deploy.add_argument("--timeout", type=int, default=900)
    deploy.add_argument("--max-deploy-attempts", type=int, default=3)
    deploy.add_argument("--retry-delay", type=int, default=15)
    deploy.add_argument("--dry-run", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.action == "show":
            return show_profile(args.profile)
        if args.action == "deploy":
            return deploy_profile(
                args.profile,
                branch=args.branch,
                wait=args.wait,
                force=args.force,
                timeout=args.timeout,
                max_deploy_attempts=args.max_deploy_attempts,
                retry_delay=args.retry_delay,
                dry_run=args.dry_run,
            )
        parser.print_help()
        return 0
    except (KeyError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        return emit_cli_error("Repo deploy profiles", exc)


if __name__ == "__main__":
    raise SystemExit(main())
