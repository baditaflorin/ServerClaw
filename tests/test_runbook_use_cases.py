from __future__ import annotations

import json
from pathlib import Path

import pytest

from platform.use_cases.runbooks import (
    RunbookRunStore,
    RunbookSurfaceError,
    RunbookUseCaseService,
    WindmillWorkflowRunner,
)


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], int | None]] = []

    def run_workflow(
        self, workflow_id: str, payload: dict[str, object], *, timeout_seconds: int | None = None
    ) -> object:
        self.calls.append((workflow_id, payload, timeout_seconds))
        return {"status": "ok"}


@pytest.fixture()
def runbook_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LV3_MUTATION_AUDIT_FILE", "off")
    (tmp_path / "docs" / "runbooks").mkdir(parents=True)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "workflow-catalog.json").write_text(
        json.dumps({"workflows": {"example-workflow": {"description": "Example"}}}, indent=2) + "\n",
        encoding="utf-8",
    )
    return tmp_path


def test_runbook_use_case_service_filters_by_delivery_surface(runbook_repo: Path) -> None:
    (runbook_repo / "docs" / "runbooks" / "default.yaml").write_text(
        """
id: default-runbook
title: Default runbook
automation:
  eligible: true
steps:
  - id: one
    workflow_id: example-workflow
    params: {}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (runbook_repo / "docs" / "runbooks" / "portal-only.yaml").write_text(
        """
id: portal-only
title: Portal-only runbook
automation:
  eligible: true
  delivery_surfaces:
    - portal
steps:
  - id: one
    workflow_id: example-workflow
    params: {}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (runbook_repo / "docs" / "runbooks" / "gateway-only.yaml").write_text(
        """
id: gateway-only
title: Gateway-only runbook
automation:
  eligible: true
  delivery_surface: api_gateway
steps:
  - id: one
    workflow_id: example-workflow
    params: {}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (runbook_repo / "docs" / "runbooks" / "docs-only.yaml").write_text(
        """
id: docs-only
title: Docs only
automation:
  eligible: false
steps:
  - id: one
    workflow_id: example-workflow
    params: {}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    service = RunbookUseCaseService(repo_root=runbook_repo, workflow_runner=FakeRunner())

    gateway_runbooks = service.list_runbooks(surface="api_gateway")
    ops_portal_runbooks = service.list_runbooks(surface="ops_portal")

    assert [item["id"] for item in gateway_runbooks] == ["gateway-only"]
    assert [item["id"] for item in ops_portal_runbooks] == ["portal-only"]


def test_runbook_use_case_service_rejects_disallowed_surface(runbook_repo: Path) -> None:
    (runbook_repo / "docs" / "runbooks" / "portal-only.yaml").write_text(
        """
id: portal-only
title: Portal-only runbook
automation:
  eligible: true
  delivery_surfaces:
    - portal
steps:
  - id: one
    workflow_id: example-workflow
    params: {}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    service = RunbookUseCaseService(repo_root=runbook_repo, workflow_runner=FakeRunner())

    with pytest.raises(RunbookSurfaceError, match="portal-only"):
        service.execute("portal-only", {}, surface="api_gateway")


def test_windmill_workflow_runner_accepts_legacy_repo_root_argument(tmp_path: Path) -> None:
    runner = WindmillWorkflowRunner(base_url="https://windmill.example", token="token", repo_root=tmp_path)

    assert runner.repo_root == tmp_path


def test_runbook_use_case_service_lists_task_reentry_models(runbook_repo: Path) -> None:
    (runbook_repo / "docs" / "runbooks" / "portal-review.yaml").write_text(
        """
id: portal-review
title: Portal review flow
automation:
  eligible: true
  delivery_surfaces:
    - ops_portal
steps:
  - id: diagnose
    workflow_id: example-workflow
    params: {}
  - id: confirm
    type: pause
    description: Review the saved diagnostics before continuing.
    params: {}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    service = RunbookUseCaseService(repo_root=runbook_repo, workflow_runner=FakeRunner())
    paused = service.execute("portal-review", {}, surface="ops_portal")
    tasks = service.list_tasks(surface="ops_portal")

    assert paused["status"] == "escalated"
    assert tasks[0]["run_id"] == paused["run_id"]
    assert tasks[0]["attention_required"] is True
    assert tasks[0]["summary"]["headline"].startswith("Awaiting confirmation")


def test_runbook_use_case_service_tolerates_legacy_task_records_without_titles(runbook_repo: Path) -> None:
    (runbook_repo / "docs" / "runbooks" / "portal-review.yaml").write_text(
        """
id: portal-review
title: Portal review flow
automation:
  eligible: true
  delivery_surfaces:
    - ops_portal
steps:
  - id: diagnose
    workflow_id: example-workflow
    params: {}
  - id: confirm
    type: pause
    description: Review the saved diagnostics before continuing.
    params: {}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    store = RunbookRunStore(runbook_repo / ".local" / "runbooks" / "runs")
    store.save(
        {
            "run_id": "legacy-run",
            "runbook_id": "portal-review",
            "runbook_source": str(runbook_repo / "docs" / "runbooks" / "portal-review.yaml"),
            "delivery_surface": "ops_portal",
            "status": "escalated",
            "created_at": "2026-03-25T09:00:00Z",
            "current_step": "confirm",
            "next_step_index": 1,
            "params": {},
            "step_results": {
                "diagnose": {
                    "status": "completed",
                    "finished_at": "2026-03-25T09:02:00Z",
                    "result": {"summary": "ok"},
                },
                "confirm": {
                    "status": "paused",
                    "finished_at": "2026-03-25T09:03:00Z",
                    "result": {"message": "Review the saved diagnostics before continuing."},
                },
            },
            "history": [
                {
                    "step_id": "confirm",
                    "status": "paused",
                    "finished_at": "2026-03-25T09:03:00Z",
                }
            ],
        }
    )
    service = RunbookUseCaseService(repo_root=runbook_repo, workflow_runner=FakeRunner(), store=store)

    tasks = service.list_tasks(surface="ops_portal")

    assert tasks[0]["run_id"] == "legacy-run"
    assert tasks[0]["runbook_title"] == "Portal review flow"
    assert tasks[0]["summary"]["headline"].startswith("Awaiting confirmation")
    assert any(item["detail"] == "Portal review flow started from Ops Portal." for item in tasks[0]["activity"])
