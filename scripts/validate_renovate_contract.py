#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
RENOVATE_CONFIG_PATH = REPO_ROOT / "renovate.json"
RENOVATE_WORKFLOW_PATH = REPO_ROOT / ".gitea" / "workflows" / "renovate.yml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_renovate_config() -> None:
    config = load_json(RENOVATE_CONFIG_PATH)
    require(
        config.get("$schema") == "https://docs.renovatebot.com/renovate-schema.json",
        "renovate.json must declare the canonical Renovate schema",
    )
    require("platform" not in config, "renovate.json must not declare the global-only platform option")
    require(config.get("dependencyDashboard") is True, "renovate.json must enable the dependency dashboard")
    require(config.get("automerge") is False, "renovate.json must disable automerge")
    require(config.get("platformAutomerge") is False, "renovate.json must disable platform automerge")
    require(
        config.get("baseBranchPatterns") == ["main"],
        "renovate.json must target the main branch with baseBranchPatterns",
    )
    labels = config.get("labels", [])
    require("dependencies" in labels and "renovate" in labels, "renovate.json must label Renovate PRs clearly")

    custom_managers = config.get("customManagers", [])
    require(
        any("image-catalog" in "".join(manager.get("managerFilePatterns", [])) for manager in custom_managers),
        "renovate.json must manage config/image-catalog.json image refs",
    )
    require(
        any("roles" in "".join(manager.get("managerFilePatterns", [])) and "defaults" in "".join(manager.get("managerFilePatterns", [])) for manager in custom_managers),
        "renovate.json must manage Ansible role default image refs",
    )
    require(
        any("versions" in "".join(manager.get("managerFilePatterns", [])) and "stack" in "".join(manager.get("managerFilePatterns", [])) for manager in custom_managers),
        "renovate.json must manage at least one versions/stack.yaml service version",
    )


def validate_workflow() -> None:
    workflow = yaml.safe_load(RENOVATE_WORKFLOW_PATH.read_text(encoding="utf-8"))
    workflow_text = RENOVATE_WORKFLOW_PATH.read_text(encoding="utf-8")

    require(workflow.get("name") == "renovate", ".gitea/workflows/renovate.yml must be named renovate")
    trigger = workflow.get("on") or workflow.get(True) or {}
    require("schedule" in trigger and "workflow_dispatch" in trigger, "Renovate workflow must support schedule and manual dispatch")

    job = workflow["jobs"]["renovate"]
    require(job.get("runs-on") == "self-hosted", "Renovate workflow must target the self-hosted runner")
    require("registry.localhost/check-runner/renovate:" in workflow_text, "Renovate workflow must pull the Renovate image through Harbor")
    require("@sha256:" in workflow_text, "Renovate workflow must pin the Renovate image to a digest")
    require("ghcr.io/renovatebot/renovate" not in workflow_text, "Renovate workflow must not pull the runtime image directly from GHCR")
    require("scripts/renovate_runtime_token.py create" in workflow_text, "Renovate workflow must mint a short-lived runtime token")
    require("scripts/renovate_runtime_token.py cleanup" in workflow_text, "Renovate workflow must revoke the short-lived runtime token")
    require("RENOVATE_BOOTSTRAP_ENV" in workflow_text, "Renovate workflow must source the mounted OpenBao-rendered credential bundle")
    require("-e RENOVATE_GIT_AUTHOR \\" in workflow_text, "Renovate workflow must pass the global git author into the runtime container")
    require("-e RENOVATE_REQUIRE_CONFIG \\" in workflow_text, "Renovate workflow must force optional config handling for branch-local validation")
    require("-e RENOVATE_ONBOARDING \\" in workflow_text, "Renovate workflow must disable onboarding during branch-local validation")
    require(
        "Bootstrap Docker CLI and discover runner host paths" in workflow_text,
        "Renovate workflow must discover runner host paths explicitly",
    )
    require('current_container_id="${HOSTNAME:-$(hostname)}"' in workflow_text, "Renovate workflow must inspect the active job container to recover its workspace host path")
    require("/var/run/lv3/renovate" in workflow_text, "Renovate workflow must discover the host-side Renovate credential directory from the runner mount")
    require(".tmp/docker-bin.path" in workflow_text, "Renovate workflow must persist the discovered Docker executable path for later steps")
    require(".tmp/workspace-host.path" in workflow_text, "Renovate workflow must persist the discovered workspace host path for later steps")
    require(".tmp/bootstrap-host.path" in workflow_text, "Renovate workflow must persist the discovered credential host path for later steps")
    require("/var/run/lv3/renovate:ro" in workflow_text, "Renovate workflow must mount the Renovate credential bundle read-only")


def main() -> int:
    validate_renovate_config()
    validate_workflow()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
