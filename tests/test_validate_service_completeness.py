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
            "docker-runtime",
            "--port",
            "8181",
            "--subdomain",
            "test-echo.example.com",
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


def test_missing_dependency_health_gate_blocks_non_grandfathered_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_repo(tmp_path)
    scaffold_demo_service(tmp_path)
    compose_path = (
        tmp_path
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "test_echo_runtime"
        / "templates"
        / "docker-compose.yml.j2"
    )
    compose_text = compose_path.read_text(encoding="utf-8")
    compose_path.write_text(
        compose_text.replace("condition: service_healthy", "condition: service_started"),
        encoding="utf-8",
    )

    service_completeness = load_service_completeness(monkeypatch, tmp_path)
    result = service_completeness.evaluate_service("test_echo")

    assert not result.passing
    assert any(item.item_id == "dependency_health_gate" for item in result.failing_items)


def test_legacy_service_uses_grandfathered_suppressions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_find_adr_path_prefers_service_specific_match_when_ids_are_duplicated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_repo(tmp_path)
    adr_dir = tmp_path / "docs" / "adr"
    generic = adr_dir / "0288-crawl4ai-as-the-llm-optimised-web-content-crawler.md"
    specific = adr_dir / "0288-flagsmith-as-the-feature-flag-and-remote-configuration-service.md"
    generic.write_text("# ADR 0288 generic\n", encoding="utf-8")
    specific.write_text("# ADR 0288 flagsmith\n", encoding="utf-8")

    service_completeness = load_service_completeness(monkeypatch, tmp_path)

    assert (
        service_completeness.find_adr_path(
            "0288",
            service_id="flagsmith",
            service_name="Flagsmith",
        )
        == specific
    )
