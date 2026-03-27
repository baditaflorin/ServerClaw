from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

import scaffold_service
import test_scaffold_service


def build_repo(root: Path) -> None:
    helper = test_scaffold_service.ScaffoldServiceTests()
    helper.build_repo(root)


def load_service_completeness(monkeypatch: pytest.MonkeyPatch, root: Path):
    monkeypatch.setenv("LV3_REPO_ROOT", str(root))
    import service_completeness

    return importlib.reload(service_completeness)


def scaffold_demo_service(root: Path) -> None:
    exit_code = scaffold_service.main(
        [
            "--repo-root",
            str(root),
            "--name",
            "test-echo",
            "--description",
            "Echo test service.",
            "--category",
            "automation",
            "--vm",
            "docker-runtime-lv3",
            "--port",
            "8181",
            "--subdomain",
            "test-echo.lv3.org",
            "--exposure",
            "private-only",
            "--image",
            "docker.io/hashicorp/http-echo:latest",
            "--today",
            "2026-03-23",
        ]
    )
    assert exit_code == 0


def test_scaffolded_service_passes_completeness_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build_repo(tmp_path)
    scaffold_demo_service(tmp_path)

    service_completeness = load_service_completeness(monkeypatch, tmp_path)
    results, failures = service_completeness.validate_services(["test_echo"])

    assert not failures
    assert results[0].passing


def test_missing_generated_artifact_blocks_non_grandfathered_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_repo(tmp_path)
    scaffold_demo_service(tmp_path)
    (tmp_path / "config" / "grafana" / "dashboards" / "test-echo.json").unlink()

    service_completeness = load_service_completeness(monkeypatch, tmp_path)
    result = service_completeness.evaluate_service("test_echo")

    assert not result.passing
    assert any(item.item_id == "grafana_dashboard" for item in result.failing_items)


def test_legacy_service_uses_grandfathered_suppressions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_repo(tmp_path)
    service_completeness = load_service_completeness(monkeypatch, tmp_path)
    completeness_path = tmp_path / "config" / "service-completeness.json"
    completeness = json.loads(completeness_path.read_text())
    completeness["suppression_presets"] = {
        "legacy-service": {item_id: "2026-09-23" for item_id in service_completeness.CHECKLIST_IDS}
    }
    completeness["services"]["docker_runtime"]["suppression_preset"] = "legacy-service"
    completeness_path.write_text(json.dumps(completeness, indent=2) + "\n")

    service_completeness = load_service_completeness(monkeypatch, tmp_path)
    result = service_completeness.evaluate_service("docker_runtime")

    assert result.passing
    grandfathered_items = {item.item_id: item.grandfathered_until for item in result.items if item.grandfathered_until}
    assert grandfathered_items["api_gateway"] == "2026-09-23"
