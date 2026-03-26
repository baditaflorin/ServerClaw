from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from platform.faults import FaultInjector, load_scenario_catalog


REPO_ROOT = Path(__file__).resolve().parents[1]


class FakeDockerClient:
    def __init__(self) -> None:
        self.stopped: list[str] = []
        self.started: list[str] = []
        self.paused: list[str] = []
        self.unpaused: list[str] = []
        self.exec_calls: list[tuple[str, list[str]]] = []
        self.exec_result: tuple[int, str] = (0, "")

    def stop(self, action):
        target = action.container_name or f"{action.compose_project}/{action.compose_service}"
        self.stopped.append(target)
        return type("Token", (), {"container_id": "abc123", "target_description": target, "restore_action": "start"})()

    def pause(self, action):
        target = action.container_name or f"{action.compose_project}/{action.compose_service}"
        self.paused.append(target)
        return type("Token", (), {"container_id": "abc123", "target_description": target, "restore_action": "unpause"})()

    def start(self, token) -> None:
        self.started.append(token.target_description)

    def unpause(self, token) -> None:
        self.unpaused.append(token.target_description)

    def exec(self, container_name: str, argv: list[str]) -> tuple[int, str]:
        self.exec_calls.append((container_name, argv))
        return self.exec_result


def test_is_first_sunday_utc() -> None:
    from platform.faults import is_first_sunday_utc

    assert is_first_sunday_utc(datetime(2026, 4, 5, 3, 0, tzinfo=UTC)) is True
    assert is_first_sunday_utc(datetime(2026, 4, 12, 3, 0, tzinfo=UTC)) is False


def test_load_scenario_catalog_resolves_known_scenarios() -> None:
    catalog = load_scenario_catalog(REPO_ROOT / "config" / "fault-scenarios.yaml")

    assert catalog.scheduled_scenario_names == (
        "fault:keycloak-unavailable",
        "fault:openbao-unavailable",
    )
    keycloak = catalog.scenarios["fault:keycloak-unavailable"]
    openbao = catalog.scenarios["fault:openbao-unavailable"]
    assert keycloak.fault.compose_project == "keycloak"
    assert openbao.fault.kind == "service_pause"
    assert keycloak.before_probes[0].url == "http://127.0.0.1:18080/realms/lv3/.well-known/openid-configuration"
    assert keycloak.before_probes[0].execution_context == "host_network_helper"
    assert keycloak.before_probes[1].headers == (("Host", "sso.lv3.org"),)
    assert keycloak.during_probes[0].expect == "unreachable"


def test_fault_injector_restores_container_after_success() -> None:
    catalog = load_scenario_catalog(REPO_ROOT / "config" / "fault-scenarios.yaml")
    scenario = catalog.scenarios["fault:openbao-unavailable"]
    docker = FakeDockerClient()
    injector = FaultInjector(docker_client=docker, sleep=lambda _: None)
    states = {
        "openbao:readiness": ["reachable", "unreachable", "reachable"],
    }

    def fake_probe(probe):
        key = probe.name
        state = states[key].pop(0)
        return type(
            "ProbeResult",
            (),
            {
                "name": probe.name,
                "kind": probe.kind,
                "expect": probe.expect,
                "passed": (probe.expect == "reachable" and state == "reachable")
                or (probe.expect == "unreachable" and state == "unreachable"),
                "observed": state,
                "status_code": 200 if state == "reachable" else None,
                "duration_seconds": 0.1,
            },
        )()

    injector._run_probe = fake_probe  # type: ignore[method-assign]

    result = injector.run_scenario(scenario)

    assert result.status == "passed"
    assert docker.paused == ["lv3-openbao"]
    assert docker.unpaused == ["lv3-openbao"]
    assert docker.stopped == []
    assert docker.started == []


def test_fault_injector_fails_when_baseline_probe_is_not_healthy() -> None:
    catalog = load_scenario_catalog(REPO_ROOT / "config" / "fault-scenarios.yaml")
    scenario = catalog.scenarios["fault:keycloak-unavailable"]
    docker = FakeDockerClient()
    injector = FaultInjector(docker_client=docker, sleep=lambda _: None)

    def fake_probe(_probe):
        return type(
            "ProbeResult",
            (),
            {
                "name": "baseline",
                "kind": "http",
                "expect": "reachable",
                "passed": False,
                "observed": "HTTP 503",
                "status_code": 503,
                "duration_seconds": 0.1,
            },
        )()

    injector._run_probe = fake_probe  # type: ignore[method-assign]

    result = injector.run_scenario(scenario)

    assert result.status == "failed"
    assert docker.stopped == []
    assert result.notes == ("baseline probes failed before fault injection",)


def test_fault_injector_runs_host_network_http_probe_via_helper_container() -> None:
    docker = FakeDockerClient()
    docker.exec_result = (0, '{"ok":true}')
    injector = FaultInjector(docker_client=docker, sleep=lambda _: None)
    probe = load_scenario_catalog(REPO_ROOT / "config" / "fault-scenarios.yaml").scenarios[
        "fault:keycloak-unavailable"
    ].before_probes[1]

    result = injector._run_probe(probe)

    assert result.passed is True
    assert docker.exec_calls == [
        (
            "windmill-openbao-agent",
            [
                "wget",
                "-qO-",
                "-T",
                "10",
                "-t",
                "1",
                "--no-check-certificate",
                "--header=Host: sso.lv3.org",
                "https://10.10.10.10/realms/lv3/.well-known/openid-configuration",
            ],
        )
    ]
