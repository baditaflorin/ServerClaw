from __future__ import annotations

import json
from pathlib import Path

import platform as stdlib_platform
import pytest

from repo_package_loader import load_repo_package


GOAL_COMPILER_MODULE = load_repo_package(
    "lv3_goal_compiler_test",
    Path(__file__).resolve().parents[2] / "platform" / "goal_compiler",
)
GoalCompilationError = GOAL_COMPILER_MODULE.GoalCompilationError
GoalCompiler = GOAL_COMPILER_MODULE.GoalCompiler


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture()
def compiler_repo(tmp_path: Path) -> Path:
    write(
        tmp_path / "config" / "service-capability-catalog.json",
        json.dumps(
            {
                "services": [
                    {"id": "netbox", "name": "NetBox", "vm": "netbox-lv3"},
                    {"id": "grafana", "name": "Grafana", "vm": "monitoring-lv3"},
                    {"id": "loki", "name": "Loki", "vm": "monitoring-lv3"},
                    {"id": "prometheus", "name": "Prometheus", "vm": "monitoring-lv3"},
                ]
            }
        )
        + "\n",
    )
    write(
        tmp_path / "config" / "workflow-catalog.json",
        json.dumps(
            {
                "workflows": {
                    "validate": {"description": "Validate repository", "live_impact": "repo_only"},
                    "converge-netbox": {"description": "Converge NetBox", "live_impact": "guest_live"},
                    "converge-monitoring": {"description": "Converge monitoring", "live_impact": "guest_live"},
                }
            }
        )
        + "\n",
    )
    write(
        tmp_path / "inventory" / "hosts.yml",
        """
all:
  children:
    lv3_guests:
      hosts:
        netbox-lv3:
          ansible_host: 10.10.10.30
        monitoring-lv3:
          ansible_host: 10.10.10.40
""".strip()
        + "\n",
    )
    write(
        tmp_path / ".local" / "state" / "world-state" / "proxmox_vms.json",
        json.dumps(
            {
                "items": [
                    {"service_id": "netbox", "name": "netbox-lv3", "vmid": 130},
                    {"service_id": "grafana", "name": "monitoring-lv3", "vmid": 140},
                ]
            }
        )
        + "\n",
    )
    return tmp_path


def test_platform_shim_preserves_stdlib_api() -> None:
    assert isinstance(stdlib_platform.system(), str)


def test_compile_deploy_service_with_scope_binding(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)

    result = compiler.compile("deploy netbox")

    assert result.matched_rule_id == "deploy-service"
    assert result.dispatch_workflow_id == "converge-netbox"
    assert result.intent.action == "deploy"
    assert result.intent.target.services == ["netbox"]
    assert result.intent.scope.allowed_hosts == ["netbox-lv3"]
    assert result.intent.scope.allowed_vmids == [130]
    assert result.intent.requires_approval is True
    assert result.intent.resource_claims == [
        {"resource": "service:netbox", "access": "write"},
        {"resource": "vm:netbox-lv3", "access": "read"},
    ]


def test_compile_alias_group_uses_group_workflow(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)

    result = compiler.compile("deploy the monitoring stack")

    assert result.intent.target.kind == "service_group"
    assert result.intent.target.services == ["grafana", "loki", "prometheus"]
    assert result.dispatch_workflow_id == "converge-monitoring"


def test_compile_direct_workflow_keeps_compatibility(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)

    result = compiler.compile("validate", dispatch_args={"mode": "strict"})

    assert result.matched_rule_id == "direct-workflow-id"
    assert result.dispatch_workflow_id == "validate"
    assert result.dispatch_payload == {"mode": "strict"}
    assert result.intent.action == "execute"


def test_compile_parse_error_is_explicit(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)

    with pytest.raises(GoalCompilationError) as excinfo:
        compiler.compile("dploy netbox")

    assert excinfo.value.code == "PARSE_ERROR"
