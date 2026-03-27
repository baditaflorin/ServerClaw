from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    scripts_dir = REPO_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def configure_paths(module, repo_root: Path) -> None:
    module.VERSION_PATH = repo_root / "VERSION"
    module.STACK_PATH = repo_root / "versions" / "stack.yaml"
    module.SERVICE_CATALOG_PATH = repo_root / "config" / "service-capability-catalog.json"
    module.STATIC_CONFIG_PATH = repo_root / "config" / "manifest-static.yaml"
    module.SCHEMA_PATH = repo_root / "docs" / "schema" / "platform-manifest.schema.json"
    module.ADR_DIR = repo_root / "docs" / "adr"
    module.RUNBOOK_DIR = repo_root / "docs" / "runbooks"
    module.RELEASE_NOTES_DIR = repo_root / "docs" / "release-notes"
    module.DEFAULT_OUTPUT_PATH = repo_root / "build" / "platform-manifest.json"
    module.DEFAULT_INCIDENT_DIR = repo_root / ".local" / "triage" / "reports"
    module.load_workflow_catalog_data = lambda: json.loads((repo_root / "config" / "workflow-catalog.json").read_text())
    module.load_workflow_defaults_data = lambda: {
        "default_budget": {
            "max_duration_seconds": 300,
            "max_steps": 50,
            "max_concurrent_instances": 1,
            "max_touched_hosts": 1,
            "max_restarts": 0,
            "max_rollback_depth": 1,
            "escalation_action": "notify_and_abort",
        },
        "default_resource_reservation": {
            "cpu_milli": 500,
            "memory_mb": 256,
            "disk_iops": 30,
            "estimated_duration_seconds": 180,
        },
    }
    module.list_active_windows_best_effort = lambda **_kwargs: {}
    module.build_slo_status_entries = lambda **_kwargs: []
    module.collect_live_apply_entries = lambda service_catalog: [
        {
            "service_ids": ["netbox"],
            "timestamp": "2026-03-24T09:00:00Z",
        }
    ]


def make_repo(tmp_path: Path) -> Path:
    write(tmp_path / "VERSION", "1.2.0\n")
    write(
        tmp_path / "versions" / "stack.yaml",
        """
schema_version: 1.0.0
repo_version: 1.2.0
platform_version: 0.40.0
desired_state:
  host_id: proxmox_florin
  provider: hetzner-dedicated
  identity_taxonomy:
    managed_identities:
      - id: lv3-agent-hub
        class: agent
        principal: lv3-agent-hub
        owner: Repository automation
      - id: lv3-automation-proxmox
        class: agent
        principal: lv3-automation@pve
        owner: Repository automation
""".strip()
        + "\n",
    )
    write(
        tmp_path / "config" / "manifest-static.yaml",
        """
schema_version: "1.0.0"
environment: production
refresh_interval_minutes: 60
identity:
  platform_name: lv3.org
  operator: Florin Badita
  description: Test platform manifest.
registered_agents:
  - agent_id: agent/observation-loop
    trust_tier: T2
    description: Observation loop.
    status: active
    principal: lv3-agent-hub
    owner: Repository automation
    source_identity_id: lv3-agent-hub
agentic_architecture:
  overview: Test pipeline.
  entry_points:
    - component: Platform CLI
      endpoint: lv3 <instruction>
      adr: "0090"
  pipeline:
    - Validation gate (ADR 0087)
  autonomous_loop:
    - Observation loop (ADR 0071)
data_sources:
  service_catalog: config/service-capability-catalog.json
  workflow_catalog: config/workflow-catalog.json
""".strip()
        + "\n",
    )
    write(
        tmp_path / "docs" / "schema" / "platform-manifest.schema.json",
        (REPO_ROOT / "docs" / "schema" / "platform-manifest.schema.json").read_text(encoding="utf-8"),
    )
    write(
        tmp_path / "config" / "service-capability-catalog.json",
        json.dumps(
            {
                "services": [
                    {
                        "id": "netbox",
                        "name": "NetBox",
                        "description": "IPAM",
                        "category": "automation",
                        "lifecycle_status": "active",
                        "health_probe_id": "netbox",
                        "public_url": "https://netbox.lv3.org",
                        "environments": {"production": {"status": "active", "url": "https://netbox.lv3.org"}},
                    },
                    {
                        "id": "grafana",
                        "name": "Grafana",
                        "description": "Dashboards",
                        "category": "observability",
                        "lifecycle_status": "active",
                        "public_url": "https://grafana.lv3.org",
                        "environments": {"production": {"status": "active", "url": "https://grafana.lv3.org"}},
                    },
                ]
            },
            indent=2,
        )
        + "\n",
    )
    write(
        tmp_path / "config" / "controller-local-secrets.json",
        json.dumps({"secrets": {}}, indent=2) + "\n",
    )
    write(
        tmp_path / "config" / "workflow-defaults.yaml",
        """
default_budget:
  max_duration_seconds: 300
  max_steps: 50
  max_concurrent_instances: 1
  max_touched_hosts: 1
  max_restarts: 0
  max_rollback_depth: 1
  escalation_action: notify_and_abort
default_resource_reservation:
  cpu_milli: 500
  memory_mb: 256
  disk_iops: 30
  estimated_duration_seconds: 180
""".strip()
        + "\n",
    )
    write(
        tmp_path / "config" / "workflow-catalog.json",
        json.dumps(
            {
                "workflows": {
                    "converge-netbox": {
                        "description": "Deploy NetBox",
                        "lifecycle_status": "active",
                        "preferred_entrypoint": {
                            "kind": "make_target",
                            "target": "converge-netbox",
                            "command": "make converge-netbox",
                        },
                        "preflight": {"required": False},
                        "validation_targets": ["validate"],
                        "live_impact": "guest_live",
                        "owner_runbook": "docs/runbooks/configure-netbox.md",
                        "implementation_refs": ["Makefile", "docs/runbooks/configure-netbox.md"],
                        "outputs": ["NetBox converged."],
                        "verification_commands": ["make validate"],
                        "execution_class": "mutation",
                    },
                    "validate": {
                        "description": "Validate repo",
                        "lifecycle_status": "active",
                        "preferred_entrypoint": {
                            "kind": "make_target",
                            "target": "validate",
                            "command": "make validate",
                        },
                        "preflight": {"required": False},
                        "validation_targets": [],
                        "live_impact": "repo_only",
                        "owner_runbook": "docs/runbooks/validate-repository-automation.md",
                        "implementation_refs": ["Makefile", "docs/runbooks/validate-repository-automation.md"],
                        "outputs": ["Repository validation complete."],
                        "verification_commands": ["make validate"],
                        "execution_class": "diagnostic",
                    },
                }
            },
            indent=2,
        )
        + "\n",
    )
    write(tmp_path / "Makefile", "validate:\nconverge-netbox:\n")
    write(tmp_path / "docs" / "runbooks" / "configure-netbox.md", "# Configure NetBox\n\n1. Apply.\n2. Verify.\n")
    write(
        tmp_path / "docs" / "runbooks" / "validate-repository-automation.md",
        "# Validate Repository Automation\n\n1. Run validation.\n",
    )
    write(
        tmp_path / "docs" / "adr" / "0132-self-describing-platform-manifest.md",
        "# ADR 0132: Self-Describing Platform Manifest\n\n- Status: Proposed\n- Implementation Status: Not Implemented\n",
    )
    write(
        tmp_path / "docs" / "adr" / "0128-platform-health-composite-index.md",
        "# ADR 0128: Platform Health Composite Index\n\n- Status: Proposed\n- Implementation Status: Not Implemented\n",
    )
    write(
        tmp_path / "docs" / "release-notes" / "1.1.0.md",
        "# Release 1.1.0\n\nReleased on: 2026-03-23\n\n## Summary\n\n- Added prior release baseline.\n",
    )
    write(
        tmp_path / "docs" / "release-notes" / "1.2.0.md",
        "# Release 1.2.0\n\nReleased on: 2026-03-24\n\n## Summary\n\n- Added the platform manifest generator.\n- Added schema validation.\n",
    )
    write(
        tmp_path / "receipts" / "live-applies" / "2026-03-24-netbox.json",
        json.dumps(
            {
                "receipt_id": "r1",
                "summary": "netbox deploy",
                "applied_on": "2026-03-24T09:00:00Z",
                "workflow_id": "converge-netbox",
                "targets": [{"kind": "vm", "name": "netbox"}],
                "verification": [{"check": "http", "result": "pass", "observed": "ok"}],
            }
        )
        + "\n",
    )
    return tmp_path


def test_build_manifest_generates_schema_compliant_payload(tmp_path: Path) -> None:
    module = load_module("platform_manifest_test", "scripts/platform_manifest.py")
    repo_root = make_repo(tmp_path)
    configure_paths(module, repo_root)

    manifest = module.build_manifest(
        generated_at=module.parse_datetime("2026-03-24T12:00:00Z"),
        incident_dir=repo_root / ".local" / "triage" / "reports",
    )

    assert manifest["manifest_version"] == "1.0.0"
    assert manifest["repo_version"] == "1.2.0"
    assert manifest["recent_changes"]["last_version"] == "1.1.0"
    assert manifest["health"]["services"]["netbox"]["status"] == "healthy"
    assert manifest["capabilities"]["available_workflows"][0]["id"] == "converge-netbox"
    assert manifest["agents"]["registered"][0]["agent_id"] == "agent/observation-loop"
    assert manifest["known_gaps"][0]["adr"] == "0128"


def test_check_detects_manifest_drift(tmp_path: Path) -> None:
    module = load_module("platform_manifest_test_drift", "scripts/platform_manifest.py")
    repo_root = make_repo(tmp_path)
    configure_paths(module, repo_root)
    output_path = repo_root / "build" / "platform-manifest.json"

    module.write_manifest(
        output_path,
        generated_at=module.parse_datetime("2026-03-24T12:00:00Z"),
        prometheus_url=None,
        incident_dir=repo_root / ".local" / "triage" / "reports",
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    payload["identity"]["platform_name"] = "broken"
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    try:
        module.check_manifest(
            output_path,
            generated_at=module.parse_datetime("2026-03-24T12:00:00Z"),
            prometheus_url=None,
            incident_dir=repo_root / ".local" / "triage" / "reports",
        )
    except ValueError as exc:
        assert "out of date" in str(exc)
    else:  # pragma: no cover - explicit failure branch
        raise AssertionError("expected drift detection to fail")
