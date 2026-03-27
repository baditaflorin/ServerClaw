from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor

import pytest

import scripts.risk_scorer.context as risk_context
import lv3_cli
from platform.diff_engine import DiffEngine
from platform.diff_engine.adapters.ansible_adapter import AnsibleAdapter
from platform.diff_engine.adapters.cert_adapter import CertAdapter
from platform.diff_engine.adapters.dns_adapter import DNSAdapter
from platform.diff_engine.adapters.docker_adapter import DockerAdapter
from platform.diff_engine.adapters.opentofu_adapter import OpenTofuAdapter
from platform.diff_engine.registry import AdapterSpec, DiffAdapterRegistry
from platform.diff_engine.schema import ChangedObject, SemanticDiff
from scripts.risk_scorer.models import ExecutionIntent, RiskClass, RiskScore


class FakeWorldState:
    def __init__(self, surfaces: dict[str, Any]) -> None:
        self.surfaces = surfaces

    def get(self, surface: str, *, allow_stale: bool = False) -> Any:
        del allow_stale
        if surface not in self.surfaces:
            raise RuntimeError(surface)
        return self.surfaces[surface]


@pytest.fixture()
def diff_repo(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "inventory").mkdir()
    (tmp_path / "playbooks").mkdir()
    (tmp_path / "Makefile").write_text("\n")

    (tmp_path / "config" / "diff-adapters.yaml").write_text(
        """
schema_version: 1.0.0
adapters:
  ansible:
    class: platform.diff_engine.adapters.ansible_adapter.AnsibleAdapter
    surface: ansible
    enabled: true
    timeout_seconds: 90
  opentofu:
    class: platform.diff_engine.adapters.opentofu_adapter.OpenTofuAdapter
    surface: opentofu
    enabled: true
    timeout_seconds: 90
  docker:
    class: platform.diff_engine.adapters.docker_adapter.DockerAdapter
    surface: docker
    enabled: true
    timeout_seconds: 30
  dns:
    class: platform.diff_engine.adapters.dns_adapter.DNSAdapter
    surface: dns
    enabled: true
    timeout_seconds: 30
  cert:
    class: platform.diff_engine.adapters.cert_adapter.CertAdapter
    surface: cert
    enabled: true
    timeout_seconds: 30
""".strip()
        + "\n"
    )
    (tmp_path / "config" / "workflow-catalog.json").write_text(
        json.dumps(
            {
                "workflows": {
                    "converge-netbox": {
                        "description": "Converge NetBox",
                        "live_impact": "guest_live",
                        "implementation_refs": ["playbooks/netbox.yml"],
                    },
                    "converge-grafana": {
                        "description": "Converge Grafana",
                        "live_impact": "external_live",
                        "implementation_refs": ["playbooks/grafana.yml"],
                    },
                    "opaque-live-change": {
                        "description": "Unknown live change",
                        "live_impact": "guest_live",
                    },
                }
            },
            indent=2,
        )
        + "\n"
    )
    (tmp_path / "config" / "service-capability-catalog.json").write_text(
        json.dumps(
            {
                "services": [
                    {
                        "id": "netbox",
                        "name": "NetBox",
                        "vm": "docker-runtime-lv3",
                        "image_catalog_ids": ["netbox_runtime", "netbox_redis_runtime"],
                        "internal_url": "http://100.118.189.95:8004",
                    },
                    {
                        "id": "windmill",
                        "name": "Windmill",
                        "vm": "docker-runtime-lv3",
                        "internal_url": "http://127.0.0.1:18081",
                        "environments": {"production": {"status": "active", "url": "http://127.0.0.1:18081"}},
                    },
                    {
                        "id": "grafana",
                        "name": "Grafana",
                        "vm": "monitoring-lv3",
                        "subdomain": "grafana.lv3.org",
                        "public_url": "https://grafana.lv3.org",
                    },
                ]
            },
            indent=2,
        )
        + "\n"
    )
    (tmp_path / "config" / "controller-local-secrets.json").write_text(
        json.dumps(
            {
                "secrets": {
                    "windmill_superadmin_secret": {"path": str(tmp_path / "windmill-token.txt")},
                }
            },
            indent=2,
        )
        + "\n"
    )
    (tmp_path / "config" / "image-catalog.json").write_text(
        json.dumps(
            {
                "images": {
                    "netbox_runtime": {
                        "service_id": "netbox",
                        "container_name": "netbox-netbox-1",
                        "runtime_host": "docker-runtime-lv3",
                        "ref": "docker.io/netboxcommunity/netbox:v4.5.4",
                        "apply_targets": ["converge-netbox"],
                    },
                    "netbox_redis_runtime": {
                        "service_id": "netbox",
                        "container_name": "netbox-redis-1",
                        "runtime_host": "docker-runtime-lv3",
                        "ref": "docker.io/valkey/valkey:8.1.5-alpine",
                        "apply_targets": ["converge-netbox"],
                    },
                }
            },
            indent=2,
        )
        + "\n"
    )
    (tmp_path / "config" / "subdomain-catalog.json").write_text(
        json.dumps(
            {
                "subdomains": [
                    {
                        "fqdn": "grafana.lv3.org",
                        "service_id": "grafana",
                        "target": "10.10.10.40",
                        "target_port": 443,
                        "status": "active",
                        "exposure": "edge-published",
                    }
                ]
            },
            indent=2,
        )
        + "\n"
    )
    (tmp_path / "config" / "certificate-catalog.json").write_text(
        json.dumps(
            {
                "certificates": [
                    {
                        "id": "grafana-edge",
                        "service_id": "grafana",
                        "expected_issuer": "letsencrypt",
                        "endpoint": {"host": "grafana.lv3.org", "port": 443, "server_name": "grafana.lv3.org"},
                        "policy": {"warn_days": 21, "critical_days": 14},
                    }
                ]
            },
            indent=2,
        )
        + "\n"
    )
    (tmp_path / "inventory" / "hosts.yml").write_text("all:\n  children: {}\n")
    (tmp_path / "playbooks" / "netbox.yml").write_text("---\n- hosts: all\n")
    (tmp_path / "playbooks" / "grafana.yml").write_text("---\n- hosts: all\n")
    (tmp_path / "windmill-token.txt").write_text("secret-token\n")
    return tmp_path


def test_ansible_adapter_parses_changed_tasks(diff_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stdout = json.dumps(
        {
            "plays": [
                {
                    "tasks": [
                        {
                            "task": {"name": "netbox_runtime : render compose file"},
                            "hosts": {
                                "docker-runtime-lv3": {
                                    "changed": True,
                                    "diff": [{"before": "image: old", "after": "image: new"}],
                                }
                            },
                        }
                    ]
                }
            ]
        }
    )
    captured_env: dict[str, str] = {}

    def runner(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        del args
        captured_env.update(kwargs["env"])
        return subprocess.CompletedProcess(["ansible-playbook"], 2, stdout=stdout, stderr="")

    monkeypatch.setattr("platform.diff_engine.adapters.ansible_adapter.shutil.which", lambda command: "/usr/bin/ansible-playbook")

    adapter = AnsibleAdapter(
        repo_root=diff_repo,
        spec=AdapterSpec("ansible", "x.AnsibleAdapter", "ansible"),
        runner=runner,
    )
    changes = adapter.compute_diff(
        {"workflow_id": "converge-netbox", "target_vm": "docker-runtime-lv3"},
        world_state=None,
        workflow={"implementation_refs": ["playbooks/netbox.yml"]},
        service={"vm": "docker-runtime-lv3"},
    )

    assert len(changes) == 1
    assert changes[0].object_id == "docker-runtime-lv3:render compose file"
    assert changes[0].confidence == "exact"
    assert captured_env["LV3_RUN_ID"].startswith("ansible-diff-")
    assert captured_env["ANSIBLE_LOCAL_TEMP"].startswith(str(diff_repo / ".local" / "runs"))
    assert captured_env["ANSIBLE_RETRY_FILES_SAVE_PATH"].startswith(str(diff_repo / ".local" / "runs"))
    assert captured_env["ANSIBLE_LOG_PATH"].startswith(str(diff_repo / ".local" / "runs"))


def test_opentofu_adapter_parses_plan_json(diff_repo: Path) -> None:
    def runner(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        del args
        plan_dir = Path(kwargs["env"]["LV3_RUN_TOFU_DIR"])
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "production.plan.json").write_text(
            json.dumps(
                {
                    "resource_changes": [
                        {
                            "address": "module.proxmox_vm",
                            "change": {"actions": ["create"], "before": None, "after": {"vmid": 9001}},
                        }
                    ]
                }
            )
        )
        return subprocess.CompletedProcess(["./scripts/tofu_exec.sh"], 0, stdout="", stderr="")

    adapter = OpenTofuAdapter(
        repo_root=diff_repo,
        spec=AdapterSpec("opentofu", "x.OpenTofuAdapter", "opentofu"),
        runner=runner,
    )
    changes = adapter.compute_diff(
        {"workflow_id": "vm-create", "arguments": {}},
        world_state=None,
        workflow={},
        service=None,
    )

    assert len(changes) == 1
    assert changes[0].change_kind == "create"
    assert changes[0].object_id == "module.proxmox_vm"


def test_opentofu_adapter_parallel_runs_use_distinct_namespaces(diff_repo: Path) -> None:
    seen_plan_dirs: list[str] = []
    lock = threading.Lock()

    def runner(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        del args
        plan_dir = Path(kwargs["env"]["LV3_RUN_TOFU_DIR"])
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "production.plan.json").write_text(
            json.dumps(
                {
                    "resource_changes": [
                        {
                            "address": "module.parallel_vm",
                            "change": {"actions": ["update"], "before": {"vmid": 1}, "after": {"vmid": 1}},
                        }
                    ]
                }
            )
        )
        with lock:
            seen_plan_dirs.append(str(plan_dir))
        return subprocess.CompletedProcess(["./scripts/tofu_exec.sh"], 0, stdout="", stderr="")

    adapter = OpenTofuAdapter(
        repo_root=diff_repo,
        spec=AdapterSpec("opentofu", "x.OpenTofuAdapter", "opentofu"),
        runner=runner,
    )

    def run_once() -> list[ChangedObject]:
        return adapter.compute_diff(
            {"workflow_id": "vm-update", "arguments": {}},
            world_state=None,
            workflow={},
            service=None,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _item: run_once(), range(2)))

    assert all(result and result[0].object_id == "module.parallel_vm" for result in results)
    assert len(set(seen_plan_dirs)) == 2


def test_docker_adapter_detects_updates_and_restarts(diff_repo: Path) -> None:
    adapter = DockerAdapter(repo_root=diff_repo, spec=AdapterSpec("docker", "x.DockerAdapter", "docker"))
    world_state = FakeWorldState(
        {
            "container_inventory": [
                {
                    "name": "netbox-netbox-1",
                    "image": "docker.io/netboxcommunity/netbox:v4.5.3",
                    "state": "running",
                },
                {
                    "name": "netbox-redis-1",
                    "image": "docker.io/valkey/valkey:8.1.5-alpine",
                    "state": "exited",
                },
            ]
        }
    )
    changes = adapter.compute_diff(
        {"workflow_id": "converge-netbox", "target_service_id": "netbox"},
        world_state=world_state,
        workflow={},
        service={"id": "netbox", "image_catalog_ids": ["netbox_runtime", "netbox_redis_runtime"]},
    )

    assert [item.change_kind for item in changes] == ["update", "restart"]


def test_dns_adapter_detects_catalog_drift(diff_repo: Path) -> None:
    adapter = DNSAdapter(repo_root=diff_repo, spec=AdapterSpec("dns", "x.DNSAdapter", "dns"))
    world_state = FakeWorldState(
        {
            "dns_records": [
                {
                    "fqdn": "grafana.lv3.org",
                    "target": "10.10.10.41",
                    "target_port": 443,
                    "status": "active",
                    "exposure": "edge-published",
                }
            ]
        }
    )
    changes = adapter.compute_diff(
        {"workflow_id": "converge-grafana", "target_service_id": "grafana"},
        world_state=world_state,
        workflow={},
        service={"id": "grafana", "subdomain": "grafana.lv3.org", "public_url": "https://grafana.lv3.org"},
    )

    assert len(changes) == 1
    assert changes[0].change_kind == "update"
    assert changes[0].object_id == "grafana.lv3.org"


def test_cert_adapter_detects_issuer_drift(diff_repo: Path) -> None:
    adapter = CertAdapter(repo_root=diff_repo, spec=AdapterSpec("cert", "x.CertAdapter", "cert"))
    world_state = FakeWorldState(
        {
            "tls_cert_expiry": {
                "certificates": [
                    {
                        "fqdn": "grafana.lv3.org",
                        "status": "ok",
                        "issuer": [[["organizationName", "step-ca"]]],
                        "not_after": "2099-01-01T00:00:00+00:00",
                    }
                ]
            }
        }
    )
    changes = adapter.compute_diff(
        {"workflow_id": "converge-grafana", "target_service_id": "grafana"},
        world_state=world_state,
        workflow={},
        service={"id": "grafana", "subdomain": "grafana.lv3.org", "public_url": "https://grafana.lv3.org"},
    )

    assert len(changes) == 1
    assert changes[0].change_kind == "renew"


def test_diff_engine_marks_unknown_surface(diff_repo: Path) -> None:
    engine = DiffEngine(repo_root=diff_repo, registry=DiffAdapterRegistry(repo_root=diff_repo))
    diff = engine.compute({"workflow_id": "opaque-live-change", "arguments": {}, "live_impact": "guest_live"})

    assert diff.total_changes == 1
    assert diff.unknown_count == 1
    assert diff.changed_objects[0].change_kind == "unknown"


def test_compile_workflow_intent_uses_semantic_diff_counts(diff_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    diff = SemanticDiff(
        intent_id="converge-netbox:123456789abc",
        computed_at="2026-03-24T00:00:00+00:00",
        changed_objects=(
            ChangedObject(
                surface="docker_container",
                object_id="netbox-netbox-1",
                change_kind="update",
                before=None,
                after=None,
                confidence="exact",
                reversible=True,
            ),
        ),
        total_changes=3,
        irreversible_count=1,
        unknown_count=2,
        adapters_used=("docker",),
        elapsed_ms=12,
    )
    monkeypatch.setattr(risk_context, "compute_semantic_diff", lambda payload, repo_root=None: diff)

    payload = risk_context.compile_workflow_intent("converge-netbox", {}, repo_root=diff_repo)

    assert payload["expected_change_count"] == 3
    assert payload["irreversible_count"] == 1
    assert payload["unknown_count"] == 2
    assert payload["semantic_diff"] is diff


def test_lv3_run_dry_run_prints_predicted_changes(
    diff_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    diff = SemanticDiff(
        intent_id="converge-netbox:123456789abc",
        computed_at="2026-03-24T00:00:00+00:00",
        changed_objects=(
            ChangedObject(
                surface="docker_container",
                object_id="netbox-netbox-1",
                change_kind="update",
                before=None,
                after=None,
                confidence="exact",
                reversible=True,
                notes="new image tag",
            ),
        ),
        total_changes=1,
        irreversible_count=0,
        unknown_count=0,
        adapters_used=("docker",),
        elapsed_ms=5,
    )
    monkeypatch.setattr(risk_context, "compute_semantic_diff", lambda payload, repo_root=None: diff)
    monkeypatch.setattr(lv3_cli, "REPO_ROOT", diff_repo)

    exit_code = lv3_cli.main(["run", "converge-netbox", "--dry-run"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Predicted changes (1 objects):" in captured.out
    assert "docker_container:netbox-netbox-1 update new image tag" in captured.out


def test_compiled_intent_ledger_event_stores_semantic_diff() -> None:
    diff = SemanticDiff(
        intent_id="converge-netbox:123456789abc",
        computed_at="2026-03-24T00:00:00+00:00",
        changed_objects=(),
        total_changes=0,
        irreversible_count=0,
        unknown_count=0,
        adapters_used=(),
        elapsed_ms=1,
    )
    intent = ExecutionIntent(
        intent_id="converge-netbox:123456789abc",
        workflow_id="converge-netbox",
        workflow_description="Converge NetBox",
        arguments={},
        live_impact="guest_live",
        target_service_id="netbox",
        target_vm="docker-runtime-lv3",
        rule_risk_class=RiskClass.MEDIUM,
        computed_risk_class=RiskClass.LOW,
        final_risk_class=RiskClass.MEDIUM,
        requires_approval=False,
        rollback_verified=True,
        expected_change_count=0,
        irreversible_count=0,
        unknown_count=0,
        scoring_context={},
        risk_score=RiskScore(
            score=0.0,
            risk_class=RiskClass.LOW,
            final_risk_class=RiskClass.MEDIUM,
            approval_gate="SOFT",
            dimension_breakdown={},
            scoring_version="1.0.0",
            stale=False,
            stale_reasons=(),
        ),
        semantic_diff=diff,
    )
    captured: dict[str, Any] = {}

    class FakeWriter:
        def __init__(self, *, dsn: str) -> None:
            captured["dsn"] = dsn

        def write(self, **kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return kwargs

    result = lv3_cli.maybe_write_compiled_intent_event(intent, dsn="postgres://ledger", writer_factory=FakeWriter)

    assert result is not None
    assert captured["event_type"] == "intent.compiled"
    assert captured["before_state"]["intent_id"] == "converge-netbox:123456789abc"
