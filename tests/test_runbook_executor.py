from __future__ import annotations

import json
from pathlib import Path

import pytest

import runbook_executor as executor_module


class FakeRunner:
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[tuple[str, dict[str, object], int | None]] = []

    def run_workflow(
        self, workflow_id: str, payload: dict[str, object], *, timeout_seconds: int | None = None
    ) -> object:
        self.calls.append((workflow_id, payload, timeout_seconds))
        return self.handler(workflow_id, payload, timeout_seconds)


@pytest.fixture()
def runbook_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LV3_MUTATION_AUDIT_FILE", "off")
    (tmp_path / "config").mkdir()
    (tmp_path / "docs" / "runbooks").mkdir(parents=True)
    (tmp_path / "config" / "workflow-catalog.json").write_text(
        json.dumps(
            {
                "workflows": {
                    "check-cert-expiry": {"description": "Check certificate expiry"},
                    "renew-service-cert": {"description": "Renew the service certificate"},
                    "verify-service-health": {"description": "Verify service health"},
                    "rollback-service-cert": {"description": "Rollback certificate state"},
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return tmp_path


def test_executor_runs_yaml_defined_runbook(runbook_repo: Path) -> None:
    (runbook_repo / "docs" / "runbooks" / "renew-certificate.yaml").write_text(
        """
id: renew-certificate
title: Renew a service certificate
automation:
  eligible: true
steps:
  - id: check-expiry
    workflow_id: check-cert-expiry
    params:
      service: "{{ params.service }}"
    success_condition: "result.days_remaining <= 14"
  - id: renew-cert
    workflow_id: renew-service-cert
    params:
      service: "{{ params.service }}"
      previous_days: "{{ steps.check-expiry.result.days_remaining }}"
    success_condition: "result.new_expiry_days >= 90"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    def handler(workflow_id: str, payload: dict[str, object], _timeout: int | None) -> object:
        if workflow_id == "check-cert-expiry":
            assert payload == {"service": "grafana"}
            return {"days_remaining": 6}
        if workflow_id == "renew-service-cert":
            assert payload == {"service": "grafana", "previous_days": 6}
            return {"new_expiry_days": 365}
        raise AssertionError(workflow_id)

    runner = FakeRunner(handler)
    executor = executor_module.RunbookExecutor(
        repo_root=runbook_repo,
        workflow_runner=runner,
        store=executor_module.RunbookRunStore(runbook_repo / ".local" / "runbooks" / "runs"),
        sleep_fn=lambda *_args, **_kwargs: None,
    )

    record = executor.execute("renew-certificate", {"service": "grafana"})

    assert record["status"] == "completed"
    assert record["step_results"]["check-expiry"]["result"]["days_remaining"] == 6
    assert record["step_results"]["renew-cert"]["result"]["new_expiry_days"] == 365
    assert [call[0] for call in runner.calls] == ["check-cert-expiry", "renew-service-cert"]


def test_executor_runs_json_defined_runbook_with_retry(runbook_repo: Path) -> None:
    (runbook_repo / "docs" / "runbooks" / "verify-health.json").write_text(
        json.dumps(
            {
                "id": "verify-health",
                "title": "Verify service health",
                "automation": {"eligible": True},
                "steps": [
                    {
                        "id": "verify-health",
                        "type": "diagnostic",
                        "workflow_id": "verify-service-health",
                        "params": {"service": "{{ params.service }}"},
                        "success_condition": "result.status == 'healthy'",
                        "on_failure": "retry_once",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    attempts = {"count": 0}

    def handler(workflow_id: str, payload: dict[str, object], _timeout: int | None) -> object:
        assert workflow_id == "verify-service-health"
        assert payload == {"service": "grafana"}
        attempts["count"] += 1
        if attempts["count"] == 1:
            return {"status": "degraded"}
        return {"status": "healthy"}

    runner = FakeRunner(handler)
    executor = executor_module.RunbookExecutor(
        repo_root=runbook_repo,
        workflow_runner=runner,
        store=executor_module.RunbookRunStore(runbook_repo / ".local" / "runbooks" / "runs"),
        sleep_fn=lambda *_args, **_kwargs: None,
    )

    record = executor.execute("verify-health", {"service": "grafana"})

    assert record["status"] == "completed"
    assert record["step_results"]["verify-health"]["attempts"] == 2
    assert attempts["count"] == 2


def test_executor_can_resume_escalated_run(runbook_repo: Path) -> None:
    (runbook_repo / "docs" / "runbooks" / "repair-service.yaml").write_text(
        """
id: repair-service
title: Repair one service
automation:
  eligible: true
steps:
  - id: verify
    workflow_id: verify-service-health
    params:
      service: "{{ params.service }}"
    success_condition: "result.status == 'healthy'"
    on_failure: escalate
""".strip()
        + "\n",
        encoding="utf-8",
    )

    attempts = {"count": 0}

    def handler(workflow_id: str, payload: dict[str, object], _timeout: int | None) -> object:
        assert workflow_id == "verify-service-health"
        assert payload == {"service": "grafana"}
        attempts["count"] += 1
        if attempts["count"] == 1:
            return {"status": "degraded"}
        return {"status": "healthy"}

    store = executor_module.RunbookRunStore(runbook_repo / ".local" / "runbooks" / "runs")
    executor = executor_module.RunbookExecutor(
        repo_root=runbook_repo,
        workflow_runner=FakeRunner(handler),
        store=store,
        sleep_fn=lambda *_args, **_kwargs: None,
    )

    first = executor.execute("repair-service", {"service": "grafana"})
    resumed = executor.resume(first["run_id"])

    assert first["status"] == "escalated"
    assert resumed["status"] == "completed"
    assert resumed["step_results"]["verify"]["attempts"] == 2


def test_executor_supports_pause_steps_and_reentry_summary(runbook_repo: Path) -> None:
    (runbook_repo / "docs" / "runbooks" / "review-gate.yaml").write_text(
        """
id: review-gate
title: Review validation gate and return to task
automation:
  eligible: true
  delivery_surfaces:
    - api_gateway
steps:
  - id: summarize-gate
    type: diagnostic
    workflow_id: verify-service-health
    params:
      service: "{{ params.service }}"
    success_condition: "result.status == 'healthy'"
    on_failure: escalate
  - id: operator-review
    type: pause
    description: Review the saved validation gate summary before continuing.
    params: {}
  - id: summarize-after-review
    type: diagnostic
    workflow_id: verify-service-health
    params:
      service: "{{ params.service }}"
    success_condition: "result.status == 'healthy'"
    on_failure: escalate
""".strip()
        + "\n",
        encoding="utf-8",
    )

    runner = FakeRunner(lambda *_args, **_kwargs: {"status": "healthy"})
    store = executor_module.RunbookRunStore(runbook_repo / ".local" / "runbooks" / "runs")
    executor = executor_module.RunbookExecutor(
        repo_root=runbook_repo,
        workflow_runner=runner,
        store=store,
        sleep_fn=lambda *_args, **_kwargs: None,
    )

    paused = executor.execute("review-gate", {"service": "grafana"}, surface="api_gateway")
    described = executor.describe_task(paused["run_id"])
    resumed = executor.resume(paused["run_id"])

    assert paused["status"] == "escalated"
    assert paused["next_step_index"] == 2
    assert described["reentry"]["summary"]["headline"].startswith("Awaiting confirmation")
    assert described["reentry"]["summary"]["last_safe_resume_point"]["message"].startswith("After summarize-gate")
    assert resumed["status"] == "completed"
    assert [call[0] for call in runner.calls] == ["verify-service-health", "verify-service-health"]


def test_executor_enforces_delivery_surface_allowlist(runbook_repo: Path) -> None:
    (runbook_repo / "docs" / "runbooks" / "gateway-only.yaml").write_text(
        """
id: gateway-only
title: Gateway only diagnostic
automation:
  eligible: true
  delivery_surfaces:
    - api_gateway
steps:
  - id: verify
    workflow_id: verify-service-health
    params:
      service: "{{ params.service }}"
    success_condition: "result.status == 'healthy'"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    executor = executor_module.RunbookExecutor(
        repo_root=runbook_repo,
        workflow_runner=FakeRunner(lambda *_args, **_kwargs: {"status": "healthy"}),
        store=executor_module.RunbookRunStore(runbook_repo / ".local" / "runbooks" / "runs"),
        sleep_fn=lambda *_args, **_kwargs: None,
    )

    with pytest.raises(executor_module.RunbookSurfaceError):
        executor.preview("gateway-only", {"service": "grafana"}, surface="cli")

    record = executor.execute("gateway-only", {"service": "grafana"}, surface="api_gateway")
    assert record["status"] == "completed"
