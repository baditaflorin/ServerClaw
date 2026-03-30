#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit

from script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path(__file__)

from platform.retry import MaxRetriesExceeded, PlatformRetryError, RetryClass, RetryPolicy, with_retry


LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}
DOCKER_ASSURANCE_DEFAULT_PATH = "/usr/local/bin/lv3-docker-publication-assurance"


@dataclass
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    cwd: str | None = None

    @property
    def command(self) -> str:
        return " ".join(self.argv)


CommandRunner = Callable[[list[str], str | None], CommandResult]
ListenerChecker = Callable[[str, int, float], bool]


def run_command(argv: list[str], cwd: str | None = None) -> CommandResult:
    completed = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, check=False)
    return CommandResult(
        argv=list(argv),
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
        cwd=cwd,
    )


def check_listener(host: str, port: int, timeout: float) -> bool:
    with socket.create_connection((host, port), timeout=timeout):
        return True


def _decode_base64_json(value: str, label: str) -> dict[str, Any]:
    try:
        raw = base64.b64decode(value.encode("utf-8"), validate=True).decode("utf-8")
        payload = json.loads(raw)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"{label} must be valid base64-encoded JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must decode to a JSON object")
    return payload


def _is_private_or_loopback_host(host: str, local_ipv4s: set[str]) -> bool:
    if host in LOOPBACK_HOSTS or host in local_ipv4s:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback


def detect_local_ipv4_addresses(command_runner: CommandRunner = run_command) -> set[str]:
    local_ipv4s = {"127.0.0.1"}
    hostname_result = command_runner(["hostname", "-I"], None)
    if hostname_result.returncode == 0:
        for candidate in hostname_result.stdout.split():
            try:
                address = ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if isinstance(address, ipaddress.IPv4Address):
                local_ipv4s.add(str(address))
    return local_ipv4s


def _normalize_binding_host(host: str) -> str:
    return "127.0.0.1" if host == "localhost" else host


def _default_port_for_url(url: str) -> int:
    parsed = urlsplit(url)
    if parsed.port:
        return int(parsed.port)
    if parsed.scheme == "https":
        return 443
    return 80


def _iter_probe_definitions(service_probe: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for phase in ("startup", "liveness", "readiness"):
        probe = service_probe.get(phase)
        if isinstance(probe, dict):
            yield phase, probe


def dedupe_bindings(bindings: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, int]] = set()
    unique: list[dict[str, Any]] = []
    for binding in bindings:
        host = str(binding["host"])
        port = int(binding["port"])
        key = (host, port)
        if key in seen:
            continue
        seen.add(key)
        unique.append({"host": host, "port": port, "source_phase": binding.get("source_phase")})
    return unique


def derive_expected_bindings(service_probe: dict[str, Any], local_ipv4s: set[str]) -> list[dict[str, Any]]:
    discovered: list[dict[str, Any]] = []
    docker_publication = service_probe.get("readiness", {}).get("docker_publication", {})
    if not isinstance(docker_publication, dict):
        docker_publication = {}

    if docker_publication.get("derive_bindings_from_probes", True):
        for phase, probe in _iter_probe_definitions(service_probe):
            kind = str(probe.get("kind", ""))
            if kind == "http":
                url = str(probe.get("url", ""))
                if not url:
                    continue
                parsed = urlsplit(url)
                host = parsed.hostname or ""
                if not _is_private_or_loopback_host(host, local_ipv4s):
                    continue
                discovered.append(
                    {
                        "host": _normalize_binding_host(host),
                        "port": _default_port_for_url(url),
                        "source_phase": phase,
                    }
                )
            elif kind == "tcp":
                host = str(probe.get("host", ""))
                port = probe.get("port")
                if not host or not isinstance(port, int):
                    continue
                if not _is_private_or_loopback_host(host, local_ipv4s):
                    continue
                discovered.append(
                    {
                        "host": _normalize_binding_host(host),
                        "port": int(port),
                        "source_phase": phase,
                    }
                )

    for binding in docker_publication.get("bindings", []):
        if not isinstance(binding, dict):
            continue
        host = str(binding.get("host", ""))
        port = binding.get("port")
        if host and isinstance(port, int):
            discovered.append({"host": _normalize_binding_host(host), "port": int(port), "source_phase": "contract"})
    return dedupe_bindings(discovered)


def _flatten_binding_map(port_map: dict[str, Any]) -> list[dict[str, str]]:
    flattened: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    if not isinstance(port_map, dict):
        return flattened
    for bindings in port_map.values():
        if not isinstance(bindings, list):
            continue
        for binding in bindings:
            if not isinstance(binding, dict):
                continue
            host_ip = str(binding.get("HostIp", ""))
            host_port = str(binding.get("HostPort", ""))
            key = (host_ip, host_port)
            if key in seen:
                continue
            seen.add(key)
            flattened.append({"host_ip": host_ip, "host_port": host_port})
    return flattened


def flatten_published_bindings(port_map: dict[str, Any]) -> list[dict[str, str]]:
    return _flatten_binding_map(port_map)


def flatten_configured_bindings(port_map: dict[str, Any]) -> list[dict[str, str]]:
    return _flatten_binding_map(port_map)


def _binding_matches(expected_host: str, expected_port: int, actual_binding: dict[str, str]) -> bool:
    actual_port = str(actual_binding.get("host_port", ""))
    actual_host = str(actual_binding.get("host_ip", ""))
    if actual_port != str(expected_port):
        return False
    if expected_host in LOOPBACK_HOSTS:
        return actual_host in LOOPBACK_HOSTS or actual_host in {"0.0.0.0", ""}
    return actual_host in {"0.0.0.0", expected_host, ""}


def _required_networks(contract: dict[str, Any]) -> list[str]:
    networks = contract.get("required_networks", [])
    if not isinstance(networks, list):
        return []
    result: list[str] = []
    for network in networks:
        if isinstance(network, str) and network.strip():
            result.append(network.strip())
    return result


def _inspect_container(container_name: str, command_runner: CommandRunner) -> tuple[dict[str, Any] | None, CommandResult]:
    result = command_runner(["docker", "inspect", container_name], None)
    if result.returncode != 0:
        return None, result
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"docker inspect for {container_name} did not return JSON") from exc
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise ValueError(f"docker inspect for {container_name} returned an unexpected payload")
    return payload[0], result


def _check_chain(
    argv: list[str],
    *,
    label: str,
    command_runner: CommandRunner,
) -> tuple[bool, CommandResult]:
    result = command_runner(argv, None)
    missing = result.returncode != 0
    if result.returncode not in {0, 1}:
        raise RuntimeError(f"{label} check failed unexpectedly: {result.stderr or result.stdout}")
    return missing, result


def _wait_for_docker_chain_state(
    *,
    require_nat_chain: bool,
    require_forward_chain: bool,
    command_runner: CommandRunner,
    attempts: int = 10,
    delay_seconds: float = 2.0,
) -> dict[str, Any]:
    latest: dict[str, Any] = {
        "missing_nat_chain": False,
        "missing_forward_chain": False,
        "docker_info_ready": False,
        "commands": [],
    }

    attempts_used = 0

    def _probe_chain_state() -> dict[str, Any]:
        nonlocal latest, attempts_used
        attempts_used += 1
        latest = {
            "missing_nat_chain": False,
            "missing_forward_chain": False,
            "docker_info_ready": False,
            "commands": [],
        }
        info_result = command_runner(["docker", "info", "--format", "{{.ServerVersion}}"], None)
        latest["commands"].append(_command_record(info_result))
        latest["docker_info_ready"] = info_result.returncode == 0 and bool(info_result.stdout.strip())
        if require_nat_chain:
            missing_nat_chain, nat_result = _check_chain(
                ["iptables", "-t", "nat", "-S", "DOCKER"],
                label="nat chain",
                command_runner=command_runner,
            )
            latest["commands"].append(_command_record(nat_result))
            latest["missing_nat_chain"] = missing_nat_chain
        else:
            latest["missing_nat_chain"] = False
        if require_forward_chain:
            missing_forward_chain, forward_result = _check_chain(
                ["iptables", "-t", "filter", "-S", "DOCKER-FORWARD"],
                label="forward chain",
                command_runner=command_runner,
            )
            latest["commands"].append(_command_record(forward_result))
            latest["missing_forward_chain"] = missing_forward_chain
        else:
            latest["missing_forward_chain"] = False
        if latest["docker_info_ready"] and not latest["missing_nat_chain"] and not latest["missing_forward_chain"]:
            return latest
        if attempts_used >= attempts:
            return latest
        raise PlatformRetryError(
            "docker chain state not ready yet",
            retry_class=RetryClass.BACKOFF,
            retry_after=delay_seconds,
        )

    return with_retry(
        _probe_chain_state,
        policy=RetryPolicy(
            max_attempts=attempts,
            base_delay_s=delay_seconds,
            max_delay_s=delay_seconds,
            multiplier=1.0,
            jitter=False,
            transient_max=0,
        ),
        error_context="docker chain state readiness",
    )


def _extract_compose_context(container_inspect: dict[str, Any], contract: dict[str, Any]) -> tuple[str | None, list[str]]:
    labels = container_inspect.get("Config", {}).get("Labels", {})
    if not isinstance(labels, dict):
        labels = {}
    working_directory = contract.get("working_directory") or labels.get("com.docker.compose.project.working_dir")
    compose_files_raw = contract.get("compose_files")
    if not compose_files_raw:
        compose_files_raw = labels.get("com.docker.compose.project.config_files", "")
    if isinstance(compose_files_raw, str):
        compose_files = [entry.strip() for entry in compose_files_raw.split(",") if entry.strip()]
    elif isinstance(compose_files_raw, list):
        compose_files = [str(entry).strip() for entry in compose_files_raw if str(entry).strip()]
    else:
        compose_files = []
    return (str(working_directory).strip() if working_directory else None), compose_files


def _command_record(result: CommandResult) -> dict[str, Any]:
    return {
        "argv": result.argv,
        "cwd": result.cwd,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _run_checks(
    *,
    service_id: str,
    service_probe: dict[str, Any],
    contract: dict[str, Any],
    local_ipv4s: set[str],
    command_runner: CommandRunner,
    listener_checker: ListenerChecker,
    listener_timeout: float,
) -> dict[str, Any]:
    container_name = str(contract.get("container_name", "")).strip()
    if not container_name:
        raise ValueError("docker publication contract requires container_name")

    expected_bindings = derive_expected_bindings(service_probe, local_ipv4s)
    required_networks = _required_networks(contract)
    command_log: list[dict[str, Any]] = []

    container_inspect, inspect_result = _inspect_container(container_name, command_runner)
    command_log.append(_command_record(inspect_result))
    if container_inspect is None:
        return {
            "service_id": service_id,
            "container_name": container_name,
            "expected_bindings": expected_bindings,
            "required_networks": required_networks,
            "container_present": False,
            "network_mode": None,
            "compose_project": None,
            "compose_working_directory": None,
            "compose_files": [],
            "actual_networks": [],
            "published_bindings": [],
            "configured_bindings": [],
            "issues": {
                "container_missing": True,
                "missing_nat_chain": False,
                "missing_forward_chain": False,
                "missing_networks": required_networks,
                "missing_port_bindings": expected_bindings,
                "missing_listeners": expected_bindings,
            },
            "commands": command_log,
        }

    host_config = container_inspect.get("HostConfig", {})
    network_mode = str(host_config.get("NetworkMode", ""))
    port_map = container_inspect.get("NetworkSettings", {}).get("Ports", {})
    if not isinstance(port_map, dict):
        port_map = {}
    fallback_port_map = host_config.get("PortBindings", {})
    if not isinstance(fallback_port_map, dict):
        fallback_port_map = {}
    networks = container_inspect.get("NetworkSettings", {}).get("Networks", {})
    if not isinstance(networks, dict):
        networks = {}
    labels = container_inspect.get("Config", {}).get("Labels", {})
    if not isinstance(labels, dict):
        labels = {}

    require_nat_chain = bool(contract.get("require_nat_chain", network_mode != "host"))
    require_forward_chain = bool(contract.get("require_forward_chain", network_mode != "host"))
    missing_nat_chain = False
    missing_forward_chain = False
    if network_mode != "host":
        if require_nat_chain:
            missing_nat_chain, nat_result = _check_chain(
                ["iptables", "-t", "nat", "-S", "DOCKER"],
                label="nat chain",
                command_runner=command_runner,
            )
            command_log.append(_command_record(nat_result))
        if require_forward_chain:
            missing_forward_chain, forward_result = _check_chain(
                ["iptables", "-t", "filter", "-S", "DOCKER-FORWARD"],
                label="forward chain",
                command_runner=command_runner,
            )
            command_log.append(_command_record(forward_result))

    missing_networks: list[str] = []
    for network_name in required_networks:
        if network_name not in networks:
            missing_networks.append(network_name)
            inspect_network = command_runner(["docker", "network", "inspect", network_name], None)
            command_log.append(_command_record(inspect_network))

    published_bindings = flatten_published_bindings(port_map)
    configured_bindings = flatten_configured_bindings(fallback_port_map)
    missing_port_bindings: list[dict[str, Any]] = []
    if network_mode != "host":
        for binding in expected_bindings:
            if not any(_binding_matches(str(binding["host"]), int(binding["port"]), item) for item in published_bindings):
                missing_port_bindings.append(binding)

    missing_listeners: list[dict[str, Any]] = []
    for binding in expected_bindings:
        try:
            listener_ok = listener_checker(str(binding["host"]), int(binding["port"]), listener_timeout)
        except OSError:
            listener_ok = False
        if not listener_ok:
            missing_listeners.append(binding)

    compose_working_directory, compose_files = _extract_compose_context(container_inspect, contract)
    return {
        "service_id": service_id,
        "container_name": container_name,
        "expected_bindings": expected_bindings,
        "required_networks": required_networks,
        "container_present": True,
        "network_mode": network_mode,
        "compose_project": labels.get("com.docker.compose.project"),
        "compose_working_directory": compose_working_directory,
        "compose_files": compose_files,
        "actual_networks": sorted(networks.keys()),
        "published_bindings": published_bindings,
        "configured_bindings": configured_bindings,
        "issues": {
            "container_missing": False,
            "missing_nat_chain": missing_nat_chain,
            "missing_forward_chain": missing_forward_chain,
            "missing_networks": missing_networks,
            "missing_port_bindings": missing_port_bindings,
            "missing_listeners": missing_listeners,
        },
        "commands": command_log,
    }


def _has_blocking_issues(report: dict[str, Any], *, strict_listeners: bool) -> bool:
    issues = report["issues"]
    if issues["container_missing"]:
        return True
    if issues["missing_nat_chain"] or issues["missing_forward_chain"]:
        return True
    if issues["missing_networks"] or issues["missing_port_bindings"]:
        return True
    if strict_listeners and issues["missing_listeners"]:
        return True
    return False


def _restart_docker(command_runner: CommandRunner) -> CommandResult:
    return command_runner(["systemctl", "restart", "docker"], None)


def _record_docker_restart_and_wait(
    *,
    report: dict[str, Any],
    contract: dict[str, Any],
    actions: list[dict[str, Any]],
    command_runner: CommandRunner,
) -> bool:
    restart_result = _restart_docker(command_runner)
    actions.append({"action": "restart_docker", "result": _command_record(restart_result)})
    waited = _wait_for_docker_chain_state(
        require_nat_chain=bool(contract.get("require_nat_chain", report["network_mode"] != "host")),
        require_forward_chain=bool(contract.get("require_forward_chain", report["network_mode"] != "host")),
        command_runner=command_runner,
    )
    actions.append({"action": "wait_for_docker", "result": waited})
    return restart_result.returncode == 0


def _recreate_compose_project(
    *,
    compose_working_directory: str | None,
    compose_files: list[str],
    command_runner: CommandRunner,
) -> CommandResult:
    if not compose_files:
        raise RuntimeError("compose recreation requested but no compose files were available from the service labels")
    argv = ["docker", "compose"]
    for compose_file in compose_files:
        argv.extend(["--file", compose_file])
    argv.extend(["up", "-d", "--force-recreate", "--remove-orphans"])
    return command_runner(argv, compose_working_directory)


def _compose_down_project(
    *,
    compose_working_directory: str | None,
    compose_files: list[str],
    command_runner: CommandRunner,
) -> CommandResult:
    if not compose_files:
        raise RuntimeError("compose reset requested but no compose files were available from the service labels")
    argv = ["docker", "compose"]
    for compose_file in compose_files:
        argv.extend(["--file", compose_file])
    argv.extend(["down", "--remove-orphans"])
    return command_runner(argv, compose_working_directory)


def _remove_compose_networks(
    *,
    network_names: Iterable[str],
    command_runner: CommandRunner,
) -> list[CommandResult]:
    results: list[CommandResult] = []
    seen: set[str] = set()
    for network_name in network_names:
        network = str(network_name).strip()
        if not network or network in seen:
            continue
        seen.add(network)
        results.append(command_runner(["docker", "network", "rm", network], None))
    return results


def _compose_recreate_needs_network_reset(result: CommandResult) -> bool:
    message = "\n".join(part for part in (result.stdout, result.stderr) if part).lower()
    return result.returncode != 0 and (
        ("network" in message and "does not exist" in message)
        or "failed programming external connectivity" in message
        or "unable to enable dnat rule" in message
        or "no chain/target/match by that name" in message
    )


def _compose_recreate_needs_project_reset(result: CommandResult) -> bool:
    message = "\n".join(part for part in (result.stdout, result.stderr) if part).lower()
    return result.returncode != 0 and any(
        marker in message
        for marker in (
            "cannot stop container",
            "cannot remove container",
            "container is restarting",
            "is zombie",
            "error when allocating new name",
            "is already in use by container",
            "name conflict",
        )
    )


def _compose_recreate_had_transport_error(result: CommandResult) -> bool:
    message = "\n".join(part for part in (result.stdout, result.stderr) if part).lower()
    return result.returncode != 0 and "error during connect" in message and "eof" in message


def _force_remove_compose_project_containers(
    *,
    compose_project: str | None,
    command_runner: CommandRunner,
) -> dict[str, Any]:
    if not compose_project:
        return {
            "compose_project": None,
            "container_ids": [],
            "listed": None,
            "removed": None,
            "restart_docker": None,
            "wait_for_docker": None,
            "retry_listed": None,
            "retry_removed": None,
        }

    label_filter = f"label=com.docker.compose.project={compose_project}"
    list_result = command_runner(["docker", "ps", "-aq", "--filter", label_filter], None)
    container_ids = [entry.strip() for entry in list_result.stdout.split() if entry.strip()]
    removal_result: dict[str, Any] = {
        "compose_project": compose_project,
        "container_ids": container_ids,
        "listed": _command_record(list_result),
        "removed": None,
        "restart_docker": None,
        "wait_for_docker": None,
        "retry_listed": None,
        "retry_removed": None,
    }
    if list_result.returncode != 0 or not container_ids:
        return removal_result

    remove_result = command_runner(["docker", "rm", "-f", *container_ids], None)
    removal_result["removed"] = _command_record(remove_result)
    if remove_result.returncode == 0:
        return removal_result

    restart_result = _restart_docker(command_runner)
    removal_result["restart_docker"] = _command_record(restart_result)
    removal_result["wait_for_docker"] = _wait_for_docker_chain_state(
        require_nat_chain=False,
        require_forward_chain=False,
        command_runner=command_runner,
    )
    retry_list_result = command_runner(["docker", "ps", "-aq", "--filter", label_filter], None)
    removal_result["retry_listed"] = _command_record(retry_list_result)
    retry_container_ids = [entry.strip() for entry in retry_list_result.stdout.split() if entry.strip()]
    if retry_list_result.returncode != 0 or not retry_container_ids:
        return removal_result

    retry_remove_result = command_runner(["docker", "rm", "-f", *retry_container_ids], None)
    removal_result["retry_removed"] = _command_record(retry_remove_result)
    return removal_result


def _reset_compose_project(
    *,
    report: dict[str, Any],
    actions: list[dict[str, Any]],
    command_runner: CommandRunner,
    remove_project_containers: bool,
) -> CommandResult:
    down_result = _compose_down_project(
        compose_working_directory=report["compose_working_directory"],
        compose_files=report["compose_files"],
        command_runner=command_runner,
    )
    actions.append({"action": "compose_reset_down", "result": _command_record(down_result)})
    if remove_project_containers:
        actions.append(
            {
                "action": "remove_compose_project_containers",
                "result": _force_remove_compose_project_containers(
                    compose_project=report["compose_project"],
                    command_runner=command_runner,
                ),
            }
        )
    network_results = _remove_compose_networks(
        network_names=report["required_networks"] + report["actual_networks"],
        command_runner=command_runner,
    )
    for network_result in network_results:
        actions.append({"action": "remove_compose_network", "result": _command_record(network_result)})
    recreate_result = _recreate_compose_project(
        compose_working_directory=report["compose_working_directory"],
        compose_files=report["compose_files"],
        command_runner=command_runner,
    )
    actions.append({"action": "compose_force_recreate", "result": _command_record(recreate_result)})
    return recreate_result


def _wait_for_publication_recovery(
    *,
    service_id: str,
    service_probe: dict[str, Any],
    contract: dict[str, Any],
    local_ipv4s: set[str],
    command_runner: CommandRunner,
    listener_checker: ListenerChecker,
    listener_timeout: float,
    strict_listeners: bool,
    attempts: int = 12,
    delay_seconds: float = 2.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    latest: dict[str, Any] = {}
    attempts_used = 0

    def _probe_publication_recovery() -> dict[str, Any]:
        nonlocal latest, attempts_used

        attempts_used += 1
        latest = _run_checks(
            service_id=service_id,
            service_probe=service_probe,
            contract=contract,
            local_ipv4s=local_ipv4s,
            command_runner=command_runner,
            listener_checker=listener_checker,
            listener_timeout=listener_timeout,
        )
        if _has_blocking_issues(latest, strict_listeners=strict_listeners):
            raise PlatformRetryError(
                "docker publication has not settled yet",
                retry_class=RetryClass.BACKOFF,
                retry_after=delay_seconds,
            )
        return latest

    try:
        settled = with_retry(
            _probe_publication_recovery,
            policy=RetryPolicy(
                max_attempts=attempts,
                base_delay_s=delay_seconds,
                max_delay_s=delay_seconds,
                multiplier=1.0,
                jitter=False,
                transient_max=0,
            ),
            error_context="docker publication recovery",
        )
        return settled, {"settled": True, "attempts": attempts_used, "report": settled}
    except MaxRetriesExceeded:
        return latest, {"settled": False, "attempts": attempts_used, "report": latest}


def assure_docker_publication(
    *,
    service_id: str,
    service_probe: dict[str, Any],
    contract: dict[str, Any],
    heal: bool,
    allow_listener_warmup_after_heal: bool,
    listener_timeout: float = 1.0,
    command_runner: CommandRunner = run_command,
    listener_checker: ListenerChecker = check_listener,
) -> dict[str, Any]:
    local_ipv4s = detect_local_ipv4_addresses(command_runner)
    before = _run_checks(
        service_id=service_id,
        service_probe=service_probe,
        contract=contract,
        local_ipv4s=local_ipv4s,
        command_runner=command_runner,
        listener_checker=listener_checker,
        listener_timeout=listener_timeout,
    )
    actions: list[dict[str, Any]] = []
    after = before
    healed = False
    compose_recreated = False
    compose_recreate_attempted = False

    if heal and _has_blocking_issues(before, strict_listeners=True):
        latest_compose_recreate_returncode: int | None = None
        compose_recreate_needs_project_reset = False
        compose_recreate_had_transport_error = False
        if before["container_present"] and (before["issues"]["missing_nat_chain"] or before["issues"]["missing_forward_chain"]):
            healed = _record_docker_restart_and_wait(
                report=before,
                contract=contract,
                actions=actions,
                command_runner=command_runner,
            ) or healed

        intermediate = _run_checks(
            service_id=service_id,
            service_probe=service_probe,
            contract=contract,
            local_ipv4s=local_ipv4s,
            command_runner=command_runner,
            listener_checker=listener_checker,
            listener_timeout=listener_timeout,
        )

        if intermediate["container_present"] and _has_blocking_issues(intermediate, strict_listeners=True):
            compose_recreate_attempted = True
            recreate_result = _recreate_compose_project(
                compose_working_directory=intermediate["compose_working_directory"],
                compose_files=intermediate["compose_files"],
                command_runner=command_runner,
            )
            actions.append({"action": "compose_force_recreate", "result": _command_record(recreate_result)})
            compose_recreate_needs_project_reset = _compose_recreate_needs_project_reset(recreate_result)
            compose_recreate_had_transport_error = _compose_recreate_had_transport_error(recreate_result)
            if _compose_recreate_needs_network_reset(recreate_result):
                recreate_result = _reset_compose_project(
                    report=intermediate,
                    actions=actions,
                    command_runner=command_runner,
                    remove_project_containers=False,
                )
            latest_compose_recreate_returncode = recreate_result.returncode
            compose_recreated = recreate_result.returncode == 0
            healed = compose_recreated or healed

        after = _run_checks(
            service_id=service_id,
            service_probe=service_probe,
            contract=contract,
            local_ipv4s=local_ipv4s,
            command_runner=command_runner,
            listener_checker=listener_checker,
            listener_timeout=listener_timeout,
        )

        compose_recreate_failed_with_publication_still_broken = (
            compose_recreate_attempted
            and latest_compose_recreate_returncode not in {None, 0}
            and (
                after["issues"]["container_missing"]
                or after["issues"]["missing_networks"]
                or after["issues"]["missing_port_bindings"]
            )
        )
        if compose_recreate_attempted and after["container_present"] and (
            after["issues"]["missing_nat_chain"]
            or after["issues"]["missing_forward_chain"]
            or compose_recreate_failed_with_publication_still_broken
        ):
            healed = _record_docker_restart_and_wait(
                report=after,
                contract=contract,
                actions=actions,
                command_runner=command_runner,
            ) or healed

            recovery = _run_checks(
                service_id=service_id,
                service_probe=service_probe,
                contract=contract,
                local_ipv4s=local_ipv4s,
                command_runner=command_runner,
                listener_checker=listener_checker,
                listener_timeout=listener_timeout,
            )

            if recovery["container_present"] and _has_blocking_issues(recovery, strict_listeners=True):
                if compose_recreate_needs_project_reset:
                    recreate_result = _reset_compose_project(
                        report=recovery,
                        actions=actions,
                        command_runner=command_runner,
                        remove_project_containers=True,
                    )
                else:
                    recreate_result = _recreate_compose_project(
                        compose_working_directory=recovery["compose_working_directory"],
                        compose_files=recovery["compose_files"],
                        command_runner=command_runner,
                    )
                    actions.append({"action": "compose_force_recreate", "result": _command_record(recreate_result)})
                    if _compose_recreate_needs_network_reset(recreate_result):
                        recreate_result = _reset_compose_project(
                            report=recovery,
                            actions=actions,
                            command_runner=command_runner,
                            remove_project_containers=False,
                        )
                latest_compose_recreate_returncode = recreate_result.returncode
                compose_recreated = recreate_result.returncode == 0 or compose_recreated
                healed = recreate_result.returncode == 0 or healed
                recovery = _run_checks(
                    service_id=service_id,
                    service_probe=service_probe,
                    contract=contract,
                    local_ipv4s=local_ipv4s,
                    command_runner=command_runner,
                    listener_checker=listener_checker,
                    listener_timeout=listener_timeout,
                )

            if (
                compose_recreate_had_transport_error
                and recovery["container_present"]
                and recovery["configured_bindings"]
                and recovery["issues"]["missing_port_bindings"]
            ):
                recreate_result = _reset_compose_project(
                    report=recovery,
                    actions=actions,
                    command_runner=command_runner,
                    remove_project_containers=True,
                )
                latest_compose_recreate_returncode = recreate_result.returncode
                compose_recreated = recreate_result.returncode == 0 or compose_recreated
                healed = recreate_result.returncode == 0 or healed
                recovery = _run_checks(
                    service_id=service_id,
                    service_probe=service_probe,
                    contract=contract,
                    local_ipv4s=local_ipv4s,
                    command_runner=command_runner,
                    listener_checker=listener_checker,
                    listener_timeout=listener_timeout,
                )

            after = recovery

    strict_listeners_after = not (
        heal and allow_listener_warmup_after_heal and (compose_recreated or compose_recreate_attempted)
    )
    if (
        (compose_recreated or compose_recreate_attempted)
        and after["container_present"]
        and after["configured_bindings"]
        and after["issues"]["missing_port_bindings"]
    ):
        after, wait_result = _wait_for_publication_recovery(
            service_id=service_id,
            service_probe=service_probe,
            contract=contract,
            local_ipv4s=local_ipv4s,
            command_runner=command_runner,
            listener_checker=listener_checker,
            listener_timeout=listener_timeout,
            strict_listeners=strict_listeners_after,
        )
        actions.append({"action": "wait_for_publication_recovery", "result": wait_result})
    ok = not _has_blocking_issues(after, strict_listeners=strict_listeners_after)
    summary_bits: list[str] = []
    if after["issues"]["container_missing"]:
        summary_bits.append("container missing")
    if after["issues"]["missing_nat_chain"]:
        summary_bits.append("nat chain missing")
    if after["issues"]["missing_forward_chain"]:
        summary_bits.append("forward chain missing")
    if after["issues"]["missing_networks"]:
        summary_bits.append("bridge networks missing")
    if after["issues"]["missing_port_bindings"]:
        summary_bits.append("port bindings missing")
    if after["issues"]["missing_listeners"]:
        if heal and not strict_listeners_after and not summary_bits:
            summary = "docker publication primitives recovered; listener warm-up deferred to readiness verification"
        else:
            summary_bits.append("listeners missing")
    if after["issues"]["missing_listeners"] and heal and not strict_listeners_after and not summary_bits:
        summary = "docker publication primitives recovered; listener warm-up deferred to readiness verification"
    elif not summary_bits:
        summary = "docker publication contract is satisfied"
    else:
        summary = ", ".join(summary_bits)

    return {
        "service_id": service_id,
        "ok": ok,
        "summary": summary,
        "healed": healed,
        "compose_recreated": compose_recreated,
        "allow_listener_warmup_after_heal": allow_listener_warmup_after_heal,
        "local_ipv4s": sorted(local_ipv4s),
        "before": before,
        "after": after,
        "actions": actions,
    }


def build_remote_command(*, service_id: str, service_probe: dict[str, Any], contract: dict[str, Any], heal: bool) -> list[str]:
    argv = [
        DOCKER_ASSURANCE_DEFAULT_PATH,
        "--service-id",
        service_id,
        "--service-probe-base64",
        base64.b64encode(json.dumps(service_probe).encode("utf-8")).decode("ascii"),
        "--contract-base64",
        base64.b64encode(json.dumps(contract).encode("utf-8")).decode("ascii"),
    ]
    if heal:
        argv.append("--heal")
    return argv


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify and optionally heal Docker publication contracts.")
    parser.add_argument("--service-id", required=True, help="Logical service identifier for reporting.")
    parser.add_argument("--service-probe-base64", required=True, help="Base64-encoded JSON service probe contract.")
    parser.add_argument("--contract-base64", required=True, help="Base64-encoded JSON Docker publication contract.")
    parser.add_argument("--heal", action="store_true", help="Repair missing Docker publication primitives before failing.")
    parser.add_argument(
        "--allow-listener-warmup-after-heal",
        action="store_true",
        help="Treat post-recreate listener warm-up as non-fatal so the caller can run the normal readiness probe next.",
    )
    parser.add_argument(
        "--listener-timeout",
        type=float,
        default=1.0,
        help="Timeout in seconds for direct listener checks.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        service_probe = _decode_base64_json(args.service_probe_base64, "service probe")
        contract = _decode_base64_json(args.contract_base64, "docker publication contract")
        result = assure_docker_publication(
            service_id=args.service_id,
            service_probe=service_probe,
            contract=contract,
            heal=args.heal,
            allow_listener_warmup_after_heal=args.allow_listener_warmup_after_heal,
            listener_timeout=args.listener_timeout,
        )
    except Exception as exc:  # noqa: BLE001 - CLI should never leak a traceback to operators
        error_payload = {"service_id": args.service_id, "ok": False, "summary": str(exc)}
        print(json.dumps(error_payload, indent=2, sort_keys=True))
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
