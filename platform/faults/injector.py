from __future__ import annotations

import http.client
import json
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from platform.datetime_compat import UTC, datetime
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO_PATH = REPO_ROOT / "config" / "fault-scenarios.yaml"
DEFAULT_REPORT_DIR = REPO_ROOT / ".local" / "fault-injection"


class ScenarioLoadError(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_first_sunday_utc(now: datetime | None = None) -> bool:
    current = now or _utc_now()
    normalized = current.astimezone(UTC)
    return normalized.weekday() == 6 and 1 <= normalized.day <= 7


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - guarded at runtime by wrappers
        raise RuntimeError("PyYAML is required to load config/fault-scenarios.yaml") from exc
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ScenarioLoadError(f"{path} must define a mapping at the top level")
    return payload


@dataclass(frozen=True)
class ProbeSpec:
    name: str
    kind: str
    expect: str
    execution_context: str = "worker"
    url: str | None = None
    method: str = "GET"
    expected_status: tuple[int, ...] = (200,)
    timeout_seconds: float = 5.0
    validate_tls: bool = True
    headers: tuple[tuple[str, str], ...] = ()
    host: str | None = None
    port: int | None = None
    body_regex: str | None = None


@dataclass(frozen=True)
class FaultAction:
    kind: str
    duration_seconds: int
    settle_seconds: int
    recovery_timeout_seconds: int
    stop_timeout_seconds: int = 1
    container_name: str | None = None
    compose_project: str | None = None
    compose_service: str | None = None


@dataclass(frozen=True)
class FaultScenario:
    name: str
    description: str
    expected_behaviour: str
    fault: FaultAction
    before_probes: tuple[ProbeSpec, ...] = ()
    during_probes: tuple[ProbeSpec, ...] = ()
    after_probes: tuple[ProbeSpec, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioCatalog:
    report_dir: Path
    scheduled_scenario_names: tuple[str, ...]
    scenarios: dict[str, FaultScenario]


@dataclass(frozen=True)
class ProbeResult:
    name: str
    kind: str
    expect: str
    passed: bool
    observed: str
    status_code: int | None = None
    duration_seconds: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "expect": self.expect,
            "passed": self.passed,
            "observed": self.observed,
            "status_code": self.status_code,
            "duration_seconds": self.duration_seconds,
        }


@dataclass(frozen=True)
class ScenarioResult:
    name: str
    status: str
    started_at: str
    completed_at: str
    duration_seconds: float
    description: str
    expected_behaviour: str
    before: tuple[ProbeResult, ...] = ()
    during: tuple[ProbeResult, ...] = ()
    after: tuple[ProbeResult, ...] = ()
    fault_target: str | None = None
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "description": self.description,
            "expected_behaviour": self.expected_behaviour,
            "fault_target": self.fault_target,
            "before": [entry.as_dict() for entry in self.before],
            "during": [entry.as_dict() for entry in self.during],
            "after": [entry.as_dict() for entry in self.after],
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class SuiteResult:
    status: str
    started_at: str
    completed_at: str
    duration_seconds: float
    scenario_count: int
    passed: int
    failed: int
    results: tuple[ScenarioResult, ...]
    report_file: str | None = None
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "scenario_count": self.scenario_count,
            "passed": self.passed,
            "failed": self.failed,
            "results": [result.as_dict() for result in self.results],
        }
        if self.report_file:
            payload["report_file"] = self.report_file
        if self.reason:
            payload["reason"] = self.reason
        return payload


@dataclass(frozen=True)
class FaultToken:
    container_id: str
    target_description: str
    restore_action: str


class UnixSocketHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, timeout: float = 5.0) -> None:
        super().__init__("localhost", timeout=timeout)
        self._socket_path = socket_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._socket_path)


class DockerSocketClient:
    def __init__(self, socket_path: str = "/var/run/docker.sock", timeout: float = 5.0) -> None:
        self.socket_path = socket_path
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, str]:
        connection = UnixSocketHTTPConnection(self.socket_path, timeout=self.timeout)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            payload = response.read().decode("utf-8")
            return response.status, payload
        finally:
            connection.close()

    def _resolve_container(self, action: FaultAction) -> tuple[str, str]:
        if action.container_name:
            status, payload = self._request(
                "GET",
                f"/containers/{urllib.parse.quote(action.container_name, safe='')}/json",
            )
            if status != 200:
                raise RuntimeError(f"docker inspect for '{action.container_name}' returned HTTP {status}")
            details = json.loads(payload)
            return str(details["Id"]), str(details.get("Name", action.container_name)).lstrip("/")

        if not action.compose_project or not action.compose_service:
            raise RuntimeError("service_kill actions must define either container_name or compose project/service")

        filters = {
            "label": [
                f"com.docker.compose.project={action.compose_project}",
                f"com.docker.compose.service={action.compose_service}",
            ]
        }
        encoded = urllib.parse.quote(json.dumps(filters, separators=(",", ":")), safe="")
        status, payload = self._request("GET", f"/containers/json?all=1&filters={encoded}")
        if status != 200:
            raise RuntimeError(f"docker list for '{action.compose_project}/{action.compose_service}' returned HTTP {status}")
        matches = json.loads(payload)
        if not isinstance(matches, list) or not matches:
            raise RuntimeError(
                f"no container found for compose service '{action.compose_project}/{action.compose_service}'"
            )
        if len(matches) > 1:
            raise RuntimeError(
                f"multiple containers found for compose service '{action.compose_project}/{action.compose_service}'"
            )
        container = matches[0]
        names = container.get("Names") or []
        description = str(names[0]).lstrip("/") if names else str(container["Id"])
        return str(container["Id"]), description

    def stop(self, action: FaultAction) -> FaultToken:
        container_id, description = self._resolve_container(action)
        status, payload = self._request(
            "POST",
            f"/containers/{container_id}/stop?t={action.stop_timeout_seconds}",
        )
        if status not in {204, 304}:
            raise RuntimeError(f"docker stop for '{description}' returned HTTP {status}: {payload.strip()}")
        return FaultToken(container_id=container_id, target_description=description, restore_action="start")

    def start(self, token: FaultToken) -> None:
        status, payload = self._request("POST", f"/containers/{token.container_id}/start")
        if status not in {204, 304}:
            raise RuntimeError(
                f"docker start for '{token.target_description}' returned HTTP {status}: {payload.strip()}"
            )

    def pause(self, action: FaultAction) -> FaultToken:
        container_id, description = self._resolve_container(action)
        status, payload = self._request("POST", f"/containers/{container_id}/pause")
        if status not in {204, 304}:
            raise RuntimeError(f"docker pause for '{description}' returned HTTP {status}: {payload.strip()}")
        return FaultToken(container_id=container_id, target_description=description, restore_action="unpause")

    def unpause(self, token: FaultToken) -> None:
        status, payload = self._request("POST", f"/containers/{token.container_id}/unpause")
        if status not in {204, 304}:
            raise RuntimeError(
                f"docker unpause for '{token.target_description}' returned HTTP {status}: {payload.strip()}"
            )

    def exec(self, container_name: str, argv: list[str]) -> tuple[int, str]:
        create_payload = json.dumps(
            {
                "AttachStdout": True,
                "AttachStderr": True,
                "Tty": True,
                "Cmd": argv,
            }
        )
        status, payload = self._request(
            "POST",
            f"/containers/{urllib.parse.quote(container_name, safe='')}/exec",
            body=create_payload,
            headers={"Content-Type": "application/json"},
        )
        if status != 201:
            raise RuntimeError(f"docker exec create for '{container_name}' returned HTTP {status}: {payload.strip()}")
        exec_id = str(json.loads(payload)["Id"])
        status, output = self._request(
            "POST",
            f"/exec/{exec_id}/start",
            body=json.dumps({"Detach": False, "Tty": True}),
            headers={"Content-Type": "application/json"},
        )
        if status != 200:
            raise RuntimeError(f"docker exec start for '{container_name}' returned HTTP {status}: {output.strip()}")
        status, inspect_payload = self._request("GET", f"/exec/{exec_id}/json")
        if status != 200:
            raise RuntimeError(
                f"docker exec inspect for '{container_name}' returned HTTP {status}: {inspect_payload.strip()}"
            )
        exit_code = json.loads(inspect_payload).get("ExitCode")
        if not isinstance(exit_code, int):
            raise RuntimeError(f"docker exec for '{container_name}' did not report a valid exit code")
        return exit_code, output


def _coerce_expected_status(value: Any) -> tuple[int, ...]:
    if value is None:
        return (200,)
    if not isinstance(value, list) or not value:
        raise ScenarioLoadError("expected_status must be a non-empty list of integers")
    normalized: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ScenarioLoadError("expected_status entries must be integers")
        normalized.append(item)
    return tuple(normalized)


def _resolve_health_probe(
    *,
    probe_catalog: dict[str, Any],
    probe_id: str,
    check: str,
    name: str | None,
    expect: str,
    body_regex: str | None,
) -> ProbeSpec:
    probe = probe_catalog.get(probe_id)
    if not isinstance(probe, dict):
        raise ScenarioLoadError(f"unknown health probe '{probe_id}'")
    check_payload = probe.get(check)
    if not isinstance(check_payload, dict):
        raise ScenarioLoadError(f"health probe '{probe_id}' does not define '{check}'")
    kind = check_payload.get("kind")
    resolved_name = name or f"{probe_id}:{check}"
    if kind == "http":
        return ProbeSpec(
            name=resolved_name,
            kind="http",
            expect=expect,
            execution_context="worker",
            url=str(check_payload["url"]),
            method=str(check_payload.get("method", "GET")).upper(),
            expected_status=_coerce_expected_status(check_payload.get("expected_status")),
            timeout_seconds=float(check_payload.get("timeout_seconds", 5)),
            validate_tls=bool(check_payload.get("validate_tls", True)),
            body_regex=body_regex,
        )
    if kind == "tcp":
        return ProbeSpec(
            name=resolved_name,
            kind="tcp",
            expect=expect,
            execution_context="worker",
            host=str(check_payload["host"]),
            port=int(check_payload["port"]),
            timeout_seconds=float(check_payload.get("timeout_seconds", 5)),
        )
    raise ScenarioLoadError(f"unsupported health probe kind '{kind}' for '{probe_id}:{check}'")


def _load_probe_spec(raw: dict[str, Any], probe_catalog: dict[str, Any]) -> ProbeSpec:
    kind = str(raw.get("kind", "")).strip()
    expect = str(raw.get("expect", "")).strip()
    execution_context = str(raw.get("execution_context", "worker")).strip() or "worker"
    header_payload = raw.get("headers") or {}
    if header_payload and not isinstance(header_payload, dict):
        raise ScenarioLoadError("probe.headers must be a mapping when provided")
    headers = tuple((str(key), str(value)) for key, value in header_payload.items())
    if expect not in {"reachable", "unreachable"}:
        raise ScenarioLoadError("probe.expect must be 'reachable' or 'unreachable'")
    if kind == "health_probe":
        probe_id = str(raw.get("probe_id", "")).strip()
        check = str(raw.get("check", "")).strip()
        if not probe_id or not check:
            raise ScenarioLoadError("health_probe entries must define probe_id and check")
        probe = _resolve_health_probe(
            probe_catalog=probe_catalog,
            probe_id=probe_id,
            check=check,
            name=raw.get("name"),
            expect=expect,
            body_regex=raw.get("body_regex"),
        )
        return ProbeSpec(
            name=probe.name,
            kind=probe.kind,
            expect=probe.expect,
            execution_context=execution_context,
            url=probe.url,
            method=probe.method,
            expected_status=probe.expected_status,
            timeout_seconds=probe.timeout_seconds,
            validate_tls=bool(raw.get("validate_tls", probe.validate_tls)),
            headers=headers or probe.headers,
            host=probe.host,
            port=probe.port,
            body_regex=probe.body_regex,
        )
    if kind == "http":
        url = str(raw.get("url", "")).strip()
        if not url:
            raise ScenarioLoadError("http probes must define url")
        return ProbeSpec(
            name=str(raw.get("name") or url),
            kind="http",
            expect=expect,
            execution_context=execution_context,
            url=url,
            method=str(raw.get("method", "GET")).upper(),
            expected_status=_coerce_expected_status(raw.get("expected_status")),
            timeout_seconds=float(raw.get("timeout_seconds", 5)),
            validate_tls=bool(raw.get("validate_tls", True)),
            headers=headers,
            body_regex=raw.get("body_regex"),
        )
    if kind == "tcp":
        host = str(raw.get("host", "")).strip()
        if not host:
            raise ScenarioLoadError("tcp probes must define host")
        return ProbeSpec(
            name=str(raw.get("name") or f"{host}:{raw.get('port')}"),
            kind="tcp",
            expect=expect,
            host=host,
            port=int(raw["port"]),
            timeout_seconds=float(raw.get("timeout_seconds", 5)),
        )
    raise ScenarioLoadError(f"unsupported probe kind '{kind}'")


def load_scenario_catalog(path: Path = DEFAULT_SCENARIO_PATH) -> ScenarioCatalog:
    payload = _load_yaml(path)
    suite = payload.get("suite") or {}
    if not isinstance(suite, dict):
        raise ScenarioLoadError("suite must be a mapping")
    probe_catalog_path = REPO_ROOT / "config" / "health-probe-catalog.json"
    probe_catalog_payload = json.loads(probe_catalog_path.read_text(encoding="utf-8"))
    probe_catalog = probe_catalog_payload.get("services")
    if not isinstance(probe_catalog, dict):
        raise ScenarioLoadError("config/health-probe-catalog.json must define services")

    raw_scenarios = payload.get("scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise ScenarioLoadError("fault scenario catalog must define a non-empty scenarios list")

    scenarios: dict[str, FaultScenario] = {}
    for raw in raw_scenarios:
        if not isinstance(raw, dict):
            raise ScenarioLoadError("scenario entries must be mappings")
        name = str(raw.get("name", "")).strip()
        if not name:
            raise ScenarioLoadError("scenario.name is required")
        fault_payload = raw.get("fault")
        if not isinstance(fault_payload, dict):
            raise ScenarioLoadError(f"scenario '{name}' must define a fault mapping")
        docker_payload = fault_payload.get("docker") or {}
        if not isinstance(docker_payload, dict):
            raise ScenarioLoadError(f"scenario '{name}' fault.docker must be a mapping")
        probes_payload = raw.get("probes") or {}
        if not isinstance(probes_payload, dict):
            raise ScenarioLoadError(f"scenario '{name}' probes must be a mapping")

        scenario = FaultScenario(
            name=name,
            description=str(raw.get("description", "")).strip(),
            expected_behaviour=str(raw.get("expected_behaviour", "")).strip(),
            fault=FaultAction(
                kind=str(fault_payload.get("kind", "")).strip(),
                duration_seconds=int(fault_payload.get("duration_seconds", 0)),
                settle_seconds=int(fault_payload.get("settle_seconds", 5)),
                recovery_timeout_seconds=int(fault_payload.get("recovery_timeout_seconds", 180)),
                stop_timeout_seconds=int(fault_payload.get("stop_timeout_seconds", 1)),
                container_name=str(docker_payload.get("container_name", "")).strip() or None,
                compose_project=str(docker_payload.get("compose_project", "")).strip() or None,
                compose_service=str(docker_payload.get("compose_service", "")).strip() or None,
            ),
            before_probes=tuple(
                _load_probe_spec(entry, probe_catalog)
                for entry in probes_payload.get("before", [])
            ),
            during_probes=tuple(
                _load_probe_spec(entry, probe_catalog)
                for entry in probes_payload.get("during", [])
            ),
            after_probes=tuple(
                _load_probe_spec(entry, probe_catalog)
                for entry in probes_payload.get("after", [])
            ),
            tags=tuple(str(item) for item in raw.get("tags", [])),
        )
        if not scenario.description:
            raise ScenarioLoadError(f"scenario '{name}' must define description")
        if not scenario.expected_behaviour:
            raise ScenarioLoadError(f"scenario '{name}' must define expected_behaviour")
        if scenario.fault.kind not in {"service_kill", "service_pause"}:
            raise ScenarioLoadError(f"scenario '{name}' uses unsupported fault kind '{scenario.fault.kind}'")
        if scenario.fault.duration_seconds < 1:
            raise ScenarioLoadError(f"scenario '{name}' fault.duration_seconds must be >= 1")
        if scenario.fault.recovery_timeout_seconds < 1:
            raise ScenarioLoadError(f"scenario '{name}' fault.recovery_timeout_seconds must be >= 1")
        scenarios[name] = scenario

    report_dir = suite.get("report_dir", ".local/fault-injection")
    scheduled_names = tuple(str(item) for item in suite.get("scheduled_scenario_names", []))
    return ScenarioCatalog(
        report_dir=REPO_ROOT / str(report_dir),
        scheduled_scenario_names=scheduled_names,
        scenarios=scenarios,
    )


class FaultInjector:
    def __init__(
        self,
        *,
        docker_client: DockerSocketClient | None = None,
        ledger_writer: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        urlopen: Callable[..., Any] = urllib.request.urlopen,
        socket_connection: Callable[..., Any] = socket.create_connection,
    ) -> None:
        self.docker_client = docker_client or DockerSocketClient()
        self.ledger_writer = ledger_writer
        self.sleep = sleep
        self.urlopen = urlopen
        self.socket_connection = socket_connection
        self.host_network_probe_container = "windmill-openbao-agent"

    def run_suite(self, scenarios: list[FaultScenario]) -> SuiteResult:
        started_at = _utc_now()
        results = tuple(self.run_scenario(scenario) for scenario in scenarios)
        failed = sum(1 for result in results if result.status != "passed")
        completed_at = _utc_now()
        return SuiteResult(
            status="passed" if failed == 0 else "failed",
            started_at=_isoformat(started_at),
            completed_at=_isoformat(completed_at),
            duration_seconds=(completed_at - started_at).total_seconds(),
            scenario_count=len(results),
            passed=len(results) - failed,
            failed=failed,
            results=results,
        )

    def run_scenario(self, scenario: FaultScenario) -> ScenarioResult:
        started_at = _utc_now()
        notes: list[str] = []
        token: FaultToken | None = None
        restored = False

        self._write_event("execution.started", scenario.name, {"phase": "fault_injection"})

        before = self._run_phase(scenario.before_probes)
        if any(not probe.passed for probe in before):
            completed_at = _utc_now()
            result = ScenarioResult(
                name=scenario.name,
                status="failed",
                started_at=_isoformat(started_at),
                completed_at=_isoformat(completed_at),
                duration_seconds=(completed_at - started_at).total_seconds(),
                description=scenario.description,
                expected_behaviour=scenario.expected_behaviour,
                before=before,
                fault_target=None,
                notes=("baseline probes failed before fault injection",),
            )
            self._write_event("execution.failed", scenario.name, {"reason": "baseline_probes_failed"})
            return result

        try:
            token = self._apply_fault(scenario.fault)
            self.sleep(max(float(scenario.fault.settle_seconds), 0.0))
            during = self._run_phase(scenario.during_probes)
            remaining = max(scenario.fault.duration_seconds - scenario.fault.settle_seconds, 0)
            if remaining:
                self.sleep(float(remaining))
            self._remove_fault(token)
            restored = True
            after = self._wait_for_phase(scenario.after_probes, timeout_seconds=scenario.fault.recovery_timeout_seconds)
        except Exception as exc:
            notes.append(str(exc))
            during = ()
            after = ()
            status = "failed"
        else:
            status = "passed"
            if any(not probe.passed for probe in during) or any(not probe.passed for probe in after):
                status = "failed"
        finally:
            if token is not None and not restored:
                try:
                    self._remove_fault(token)
                    notes.append(f"restored {token.target_description} during cleanup")
                    after = self._wait_for_phase(
                        scenario.after_probes,
                        timeout_seconds=scenario.fault.recovery_timeout_seconds,
                    )
                except Exception as exc:  # pragma: no cover - best effort cleanup path
                    notes.append(f"cleanup failed: {exc}")

        completed_at = _utc_now()
        result = ScenarioResult(
            name=scenario.name,
            status=status,
            started_at=_isoformat(started_at),
            completed_at=_isoformat(completed_at),
            duration_seconds=(completed_at - started_at).total_seconds(),
            description=scenario.description,
            expected_behaviour=scenario.expected_behaviour,
            before=before,
            during=tuple(during),
            after=tuple(after),
            fault_target=token.target_description if token else None,
            notes=tuple(notes),
        )
        self._write_event(
            "execution.completed" if status == "passed" else "execution.failed",
            scenario.name,
            {
                "status": status,
                "fault_target": token.target_description if token else None,
                "notes": notes,
            },
        )
        return result

    def _write_event(self, event_type: str, target_id: str, metadata: dict[str, Any]) -> None:
        if self.ledger_writer is None:
            return
        try:
            self.ledger_writer.write(
                event_type=event_type,
                actor="system:fault_injection",
                target_kind="workflow",
                target_id=target_id,
                metadata=metadata,
            )
        except Exception:
            return

    def _apply_fault(self, action: FaultAction) -> FaultToken:
        if action.kind == "service_kill":
            return self.docker_client.stop(action)
        if action.kind == "service_pause":
            return self.docker_client.pause(action)
        raise RuntimeError(f"unsupported fault kind '{action.kind}'")

    def _remove_fault(self, token: FaultToken) -> None:
        if token.restore_action == "start":
            self.docker_client.start(token)
            return
        if token.restore_action == "unpause":
            self.docker_client.unpause(token)
            return
        raise RuntimeError(f"unsupported fault restore action '{token.restore_action}'")

    def _run_phase(self, probes: tuple[ProbeSpec, ...]) -> tuple[ProbeResult, ...]:
        return tuple(self._run_probe(probe) for probe in probes)

    def _wait_for_phase(self, probes: tuple[ProbeSpec, ...], *, timeout_seconds: int) -> tuple[ProbeResult, ...]:
        if not probes:
            return ()
        deadline = time.time() + timeout_seconds
        latest = self._run_phase(probes)
        while any(not result.passed for result in latest):
            if time.time() >= deadline:
                return latest
            self.sleep(2.0)
            latest = self._run_phase(probes)
        return latest

    def _run_probe(self, probe: ProbeSpec) -> ProbeResult:
        if probe.kind == "http":
            if probe.execution_context == "host_network_helper":
                return self._run_host_network_http_probe(probe)
            return self._run_http_probe(probe)
        if probe.kind == "tcp":
            return self._run_tcp_probe(probe)
        raise RuntimeError(f"unsupported probe kind '{probe.kind}'")

    def _run_host_network_http_probe(self, probe: ProbeSpec) -> ProbeResult:
        assert probe.url is not None
        argv = ["wget", "-qO-", "-T", str(int(max(probe.timeout_seconds, 1))), "-t", "1"]
        if not probe.validate_tls:
            argv.append("--no-check-certificate")
        for key, value in probe.headers:
            argv.append(f"--header={key}: {value}")
        argv.append(probe.url)
        started = time.monotonic()
        try:
            exit_code, output = self.docker_client.exec(self.host_network_probe_container, argv)
        except Exception as exc:
            duration = time.monotonic() - started
            passed = probe.expect == "unreachable"
            return ProbeResult(
                name=probe.name,
                kind=probe.kind,
                expect=probe.expect,
                passed=passed,
                observed=type(exc).__name__,
                status_code=None,
                duration_seconds=duration,
            )

        duration = time.monotonic() - started
        body_matches = True
        if probe.body_regex:
            body_matches = bool(re.search(probe.body_regex, output))
        reachable = exit_code == 0 and body_matches
        passed = reachable if probe.expect == "reachable" else not reachable
        return ProbeResult(
            name=probe.name,
            kind=probe.kind,
            expect=probe.expect,
            passed=passed,
            observed="reachable" if reachable else f"wget-exit-{exit_code}",
            status_code=200 if reachable else None,
            duration_seconds=duration,
        )

    def _run_http_probe(self, probe: ProbeSpec) -> ProbeResult:
        assert probe.url is not None
        request = urllib.request.Request(probe.url, method=probe.method)
        context = None
        if not probe.validate_tls:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        started = time.monotonic()
        try:
            with self.urlopen(request, timeout=probe.timeout_seconds, context=context) as response:
                payload = response.read().decode("utf-8", errors="replace")
                duration = time.monotonic() - started
                matches_body = True
                if probe.body_regex:
                    matches_body = bool(re.search(probe.body_regex, payload))
                reachable = response.status in probe.expected_status and matches_body
                passed = reachable if probe.expect == "reachable" else not reachable
                return ProbeResult(
                    name=probe.name,
                    kind=probe.kind,
                    expect=probe.expect,
                    passed=passed,
                    observed=f"HTTP {response.status}",
                    status_code=response.status,
                    duration_seconds=duration,
                )
        except urllib.error.HTTPError as exc:
            duration = time.monotonic() - started
            reachable = exc.code in probe.expected_status
            passed = reachable if probe.expect == "reachable" else not reachable
            return ProbeResult(
                name=probe.name,
                kind=probe.kind,
                expect=probe.expect,
                passed=passed,
                observed=f"HTTP {exc.code}",
                status_code=exc.code,
                duration_seconds=duration,
            )
        except (urllib.error.URLError, ssl.SSLError, TimeoutError, ConnectionError, OSError) as exc:
            duration = time.monotonic() - started
            passed = probe.expect == "unreachable"
            return ProbeResult(
                name=probe.name,
                kind=probe.kind,
                expect=probe.expect,
                passed=passed,
                observed=type(exc).__name__,
                status_code=None,
                duration_seconds=duration,
            )

    def _run_tcp_probe(self, probe: ProbeSpec) -> ProbeResult:
        assert probe.host is not None
        assert probe.port is not None
        started = time.monotonic()
        try:
            with self.socket_connection((probe.host, probe.port), timeout=probe.timeout_seconds):
                duration = time.monotonic() - started
                return ProbeResult(
                    name=probe.name,
                    kind=probe.kind,
                    expect=probe.expect,
                    passed=probe.expect == "reachable",
                    observed="connected",
                    duration_seconds=duration,
                )
        except OSError as exc:
            duration = time.monotonic() - started
            return ProbeResult(
                name=probe.name,
                kind=probe.kind,
                expect=probe.expect,
                passed=probe.expect == "unreachable",
                observed=type(exc).__name__,
                duration_seconds=duration,
            )
