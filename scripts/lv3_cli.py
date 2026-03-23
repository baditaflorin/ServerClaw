#!/usr/bin/env python3

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shlex
import socket
import ssl
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_VERSION = "0.1.0"
DEFAULT_STATUS_TIMEOUT_SECONDS = 3.0
DEFAULT_LOG_LINES = 20
DEFAULT_LOG_SINCE = "1h"
ACTIVE_BINDING_STATES = {"active", "planned"}
COMPLETION_SENTINEL = "# >>> lv3 completion >>>"
NO_COLOR = bool(os.environ.get("NO_COLOR"))
SERVICE_ALIASES = {
    "ops": "ops_portal",
    "changelog": "changelog_portal",
    "proxmox": "proxmox_ui",
}


@dataclass(frozen=True)
class CommandPlan:
    label: str
    route: str
    command: list[str]
    receipt_hint: str | None = None


@dataclass(frozen=True)
class ProbeResult:
    service_id: str
    url: str
    healthy: bool
    health_text: str
    latency_seconds: float | None


def repo_path(*parts: str) -> Path:
    return REPO_ROOT.joinpath(*parts)


def load_json(path: Path, *, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text())


def load_service_catalog() -> list[dict[str, Any]]:
    payload = load_json(repo_path("config", "service-capability-catalog.json"))
    services = payload.get("services")
    if not isinstance(services, list):
        raise ValueError("config/service-capability-catalog.json must define a services list")
    return services


def load_service_map() -> dict[str, dict[str, Any]]:
    return {service["id"]: service for service in load_service_catalog()}


def load_health_probe_catalog() -> dict[str, Any]:
    payload = load_json(repo_path("config", "health-probe-catalog.json"))
    services = payload.get("services")
    if not isinstance(services, dict):
        raise ValueError("config/health-probe-catalog.json must define a services object")
    return services


def load_workflow_catalog() -> dict[str, dict[str, Any]]:
    payload = load_json(repo_path("config", "workflow-catalog.json"))
    workflows = payload.get("workflows")
    if not isinstance(workflows, dict):
        raise ValueError("config/workflow-catalog.json must define a workflows object")
    return workflows


def load_secret_manifest() -> dict[str, Any]:
    payload = load_json(repo_path("config", "controller-local-secrets.json"))
    secrets = payload.get("secrets")
    if not isinstance(secrets, dict):
        raise ValueError("config/controller-local-secrets.json must define a secrets object")
    return secrets


def parse_make_targets() -> set[str]:
    makefile = repo_path("Makefile")
    targets: set[str] = set()
    for line in makefile.read_text().splitlines():
        if not line or line.startswith("\t"):
            continue
        if ":=" in line or "?=" in line:
            continue
        if ":" not in line:
            continue
        target = line.split(":", 1)[0].strip()
        if target and target != ".PHONY" and " " not in target and "=" not in target:
            targets.add(target)
    return targets


def primary_service_url(service: dict[str, Any], environment: str = "production") -> str | None:
    environments = service.get("environments", {})
    if isinstance(environments, dict):
        binding = environments.get(environment)
        if isinstance(binding, dict) and binding.get("status") in ACTIVE_BINDING_STATES:
            url = binding.get("url")
            if isinstance(url, str) and url.strip():
                return url
    for field in ("public_url", "internal_url"):
        value = service.get(field)
        if isinstance(value, str) and value.strip():
            return value
    return None


def service_identifier_candidates(service: dict[str, Any]) -> list[str]:
    candidates = [service["id"], service.get("name", ""), service.get("vm", "")]
    public_url = service.get("public_url")
    if isinstance(public_url, str):
        candidates.append(public_url)
    return [candidate for candidate in candidates if candidate]


def get_service_or_exit(service_map: dict[str, dict[str, Any]], service_id: str) -> dict[str, Any]:
    service_id = SERVICE_ALIASES.get(service_id, service_id)
    service = service_map.get(service_id)
    if service is None:
        raise SystemExit(f"Unknown service '{service_id}'.")
    return service


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remainder = divmod(int(round(seconds)), 60)
    return f"{minutes}m {remainder:02d}s"


def strip_ansi(text: str) -> str:
    return text


def colorize(text: str, code: str, *, enabled: bool) -> str:
    if not enabled:
        return text
    return f"\033[{code}m{text}\033[0m"


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def command_string(command: Iterable[str]) -> str:
    return shlex.join(list(command))


def print_plan(plan: CommandPlan, *, no_color: bool) -> None:
    enabled = not no_color and not NO_COLOR
    print(colorize(f"lv3 {plan.label}", "1;36", enabled=enabled))
    print(f"Route:   {plan.route}")
    print(f"Command: {command_string(plan.command)}")


def run_plan(plan: CommandPlan, *, dry_run: bool, explain: bool, no_color: bool) -> int:
    print_plan(plan, no_color=no_color)
    if dry_run or explain:
        return 0

    started = time.monotonic()
    completed = subprocess.run(plan.command, cwd=REPO_ROOT, text=True, check=False)
    elapsed = time.monotonic() - started
    print(f"Exit:    {completed.returncode}")
    print(f"Total:   {format_duration(elapsed)}")
    if completed.returncode == 0 and plan.receipt_hint:
        receipt = find_latest_receipt(plan.receipt_hint)
        if receipt is not None:
            print(f"Receipt: {receipt.relative_to(REPO_ROOT)}")
    return completed.returncode


def resolve_deploy_command(service_id: str, environment: str) -> CommandPlan:
    remote_command = f"make live-apply-service service={shlex.quote(service_id)} env={shlex.quote(environment)}"
    return CommandPlan(
        label=f"deploy {service_id} --env {environment}",
        route="controller -> build server -> target service playbook",
        command=["make", "remote-exec", f"COMMAND={remote_command}"],
        receipt_hint=service_id,
    )


def resolve_lint_command(local: bool) -> CommandPlan:
    if local:
        return CommandPlan(
            label="lint --local",
            route="controller local validation path",
            command=["./scripts/validate_repo.sh", "yaml", "ansible-lint"],
        )
    return CommandPlan(
        label="lint",
        route="controller -> build server check runner",
        command=["make", "remote-lint"],
    )


def resolve_validate_command(strict: bool) -> CommandPlan:
    if strict:
        return CommandPlan(
            label="validate --strict",
            route="controller -> build server full pre-push gate",
            command=["make", "remote-pre-push"],
        )
    return CommandPlan(
        label="validate",
        route="controller -> build server validation gate",
        command=["make", "remote-validate"],
    )


def remote_tofu_shell(environment: str, action: str, *, target: str | None = None) -> str:
    env_dir = f"tofu/environments/{environment}"
    checks = [
        f"test -d {shlex.quote(env_dir)} || {{ echo 'Missing OpenTofu environment: {env_dir}' >&2; exit 1; }}",
        "command -v tofu >/dev/null 2>&1 || { echo 'Missing opentofu (tofu) on execution host' >&2; exit 1; }",
    ]
    base = f"cd {shlex.quote(env_dir)}"
    if action == "plan":
        command = "tofu plan"
    elif action == "apply":
        command = "tofu apply -auto-approve"
    elif action == "drift":
        command = "tofu plan -detailed-exitcode"
    elif action == "destroy":
        if not target:
            raise ValueError("destroy requires a tofu target")
        command = f"tofu destroy -target={shlex.quote(target)} -auto-approve"
    elif action == "list":
        command = "tofu state list || true"
    else:
        raise ValueError(f"Unsupported tofu action '{action}'")
    return " && ".join([*checks, base, command])


def resolve_diff_command(environment: str) -> CommandPlan:
    if "drift-report" in parse_make_targets():
        return CommandPlan(
            label=f"diff --env {environment}",
            route="controller local full-platform drift check",
            command=["make", "drift-report", f"ENV={environment}"],
        )
    if "tofu-drift" in parse_make_targets():
        return CommandPlan(
            label=f"diff --env {environment}",
            route="controller -> build server OpenTofu drift check",
            command=["make", "tofu-drift", f"ENV={environment}"],
        )
    return CommandPlan(
        label=f"diff --env {environment}",
            route="controller -> build server OpenTofu drift check",
            command=["make", "remote-exec", f"COMMAND={remote_tofu_shell(environment, 'drift')}"],
    )


def resolve_vm_command(
    action: str,
    environment: str,
    *,
    vm_name: str | None = None,
    force: bool = False,
) -> CommandPlan:
    if action == "create":
        label = f"vm create {vm_name or ''}".strip()
        if "remote-tofu-apply" in parse_make_targets():
            return CommandPlan(
                label=label,
                route="controller -> build server -> Proxmox API apply",
                command=["make", "remote-tofu-apply", f"ENV={environment}"],
            )
        return CommandPlan(
            label=label,
            route="controller -> build server -> Proxmox API apply",
            command=["make", "remote-exec", f"COMMAND={remote_tofu_shell(environment, 'apply')}"],
        )
    if action == "destroy":
        if not vm_name:
            raise SystemExit("lv3 vm destroy requires a VM name.")
        if not force:
            raise SystemExit("lv3 vm destroy requires --force.")
        target = f"module.{vm_name}"
        return CommandPlan(
            label=f"vm destroy {vm_name} --env {environment}",
            route="controller -> build server -> Proxmox API destroy",
            command=["make", "remote-exec", f"COMMAND={remote_tofu_shell(environment, 'destroy', target=target)}"],
        )
    if action == "resize":
        env_main = repo_path("tofu", "environments", environment, "main.tf")
        editor = os.environ.get("EDITOR")
        if not editor:
            raise SystemExit("Set $EDITOR before using lv3 vm resize.")
        return CommandPlan(
            label=f"vm resize {vm_name or ''} --env {environment}".strip(),
            route="controller local editor -> repository IaC",
            command=shlex.split(editor) + [str(env_main)],
        )
    raise SystemExit(f"Unsupported vm action '{action}'.")


def secret_get_command(secret_path: str) -> CommandPlan:
    return CommandPlan(
        label=f"secret get {secret_path}",
        route="controller -> OpenBao CLI",
        command=["openbao", "kv", "get", "-format=json", secret_path],
    )


def secret_rotate_command(secret_id: str) -> CommandPlan:
    return CommandPlan(
        label=f"secret rotate {secret_id}",
        route="controller -> repo-managed rotation workflow",
        command=["make", "rotate-secret", f"SECRET_ID={secret_id}"],
    )


def fixture_command(
    action: str,
    fixture_name: str | None = None,
    *,
    purpose: str | None = None,
    owner: str | None = None,
    lifetime_hours: float | None = None,
    policy: str | None = None,
    extend: bool = False,
    vmid: int | None = None,
    receipt_id: str | None = None,
) -> CommandPlan:
    action_map = {
        "create": "up",
        "up": "up",
        "destroy": "down",
        "down": "down",
        "list": "list",
    }
    target = f"fixture-{action_map[action]}"
    command = ["make", target]
    if fixture_name:
        command.append(f"FIXTURE={fixture_name}")
    if purpose:
        command.append(f"PURPOSE={purpose}")
    if owner:
        command.append(f"OWNER={owner}")
    if lifetime_hours is not None:
        command.append(f"LIFETIME_HOURS={lifetime_hours}")
    if policy:
        command.append(f"EPHEMERAL_POLICY={policy}")
    if extend:
        command.append("ALLOW_EXTEND=1")
    if vmid is not None:
        command.append(f"VMID={vmid}")
    if receipt_id:
        command.append(f"RECEIPT_ID={receipt_id}")
    return CommandPlan(
        label=f"fixture {action} {fixture_name or ''}".strip(),
        route="controller -> repo-managed ephemeral VM lifecycle helper",
        command=command,
    )


def operator_inventory_command(operator_id: str, *, offline: bool) -> CommandPlan:
    command = ["uvx", "--from", "pyyaml", "python", "scripts/operator_access_inventory.py", "--id", operator_id]
    if offline:
        command.append("--offline")
    return CommandPlan(
        label=f"operator inventory {operator_id}",
        route="controller local operator access inventory",
        command=command,
    )


def scaffold_command(service_name: str) -> CommandPlan:
    return CommandPlan(
        label=f"scaffold {service_name}",
        route="controller local service scaffold generator",
        command=["make", "scaffold-service", f"NAME={service_name}"],
    )


def promote_command(branch: str, service: str, staging_receipt: str, dry_run: bool) -> CommandPlan:
    command = [
        "make",
        "promote",
        f"SERVICE={service}",
        f"STAGING_RECEIPT={staging_receipt}",
        f"BRANCH={branch}",
    ]
    if dry_run:
        command.append("DRY_RUN=true")
    return CommandPlan(
        label=f"promote {branch}",
        route="controller -> promotion pipeline",
        command=command,
    )


def windmill_url(service_map: dict[str, dict[str, Any]]) -> str:
    service = get_service_or_exit(service_map, "windmill")
    url = primary_service_url(service)
    if not url:
        raise SystemExit("Windmill URL is not defined in the service catalog.")
    return url.rstrip("/")


def load_secret_file(secret_id: str) -> str:
    manifest = load_secret_manifest()
    entry = manifest.get(secret_id)
    if not isinstance(entry, dict):
        raise SystemExit(f"Unknown controller-local secret '{secret_id}'.")
    path = entry.get("path")
    if not isinstance(path, str):
        raise SystemExit(f"Secret '{secret_id}' does not define a file path.")
    secret_path = Path(path)
    if not secret_path.exists():
        raise SystemExit(f"Secret file not found: {secret_path}")
    return secret_path.read_text(encoding="utf-8").strip()


def parse_kv_pairs(pairs: list[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"Expected key=value, got '{pair}'.")
        key, value = pair.split("=", 1)
        payload[key] = value
    return payload


def run_windmill_workflow(workflow_name: str, args: list[str], *, dry_run: bool, explain: bool, no_color: bool) -> int:
    service_map = load_service_map()
    base_url = windmill_url(service_map)
    token = load_secret_file("windmill_superadmin_secret")
    script_path = workflow_name if "/" in workflow_name else f"f/lv3/{workflow_name}"
    encoded_path = urllib.parse.quote(script_path, safe="")
    url = f"{base_url}/api/w/lv3/jobs/run_wait_result/p/{encoded_path}"
    payload = json.dumps(parse_kv_pairs(args)).encode("utf-8")
    plan = CommandPlan(
        label=f"run {workflow_name}",
        route="controller -> Windmill API",
        command=[
            "curl",
            "-X",
            "POST",
            "-H",
            "Authorization: Bearer <redacted>",
            "-H",
            "Content-Type: application/json",
            url,
            "--data-binary",
            payload.decode("utf-8"),
        ],
    )
    print_plan(plan, no_color=no_color)
    if dry_run or explain:
        return 0

    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        print(f"Windmill API error: {exc}", file=sys.stderr)
        return 1

    if body.strip():
        print(body)
    return 0


def open_service_url(service_id: str, environment: str, *, dry_run: bool, explain: bool, no_color: bool) -> int:
    service = get_service_or_exit(load_service_map(), service_id)
    url = primary_service_url(service, environment)
    if not url:
        raise SystemExit(f"Service '{service_id}' does not define a browsable URL.")
    plan = CommandPlan(
        label=f"open {service_id}",
        route="controller local browser",
        command=["python3", "-m", "webbrowser", url],
    )
    print_plan(plan, no_color=no_color)
    if dry_run or explain:
        return 0
    return 0 if webbrowser.open(url) else 1


def http_probe(url: str, *, timeout: float, validate_tls: bool) -> ProbeResult:
    started = time.monotonic()
    request = urllib.request.Request(url, headers={"User-Agent": "lv3-cli/0.1.0"})
    context = None
    if url.startswith("https://") and not validate_tls:
        context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            status = response.status
        elapsed = time.monotonic() - started
        healthy = 200 <= status < 400
        return ProbeResult(
            service_id="",
            url=url,
            healthy=healthy,
            health_text=f"{'OK' if healthy else 'BAD'} {status}",
            latency_seconds=elapsed,
        )
    except urllib.error.URLError as exc:
        return ProbeResult(service_id="", url=url, healthy=False, health_text=str(exc.reason), latency_seconds=None)


def tcp_probe(host: str, port: int, *, timeout: float) -> ProbeResult:
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            elapsed = time.monotonic() - started
            return ProbeResult(service_id="", url=f"tcp://{host}:{port}", healthy=True, health_text="OK tcp", latency_seconds=elapsed)
    except OSError as exc:
        return ProbeResult(service_id="", url=f"tcp://{host}:{port}", healthy=False, health_text=str(exc), latency_seconds=None)


def probe_one_service(
    service: dict[str, Any],
    health_probes: dict[str, Any],
    *,
    environment: str,
    timeout: float,
) -> ProbeResult:
    url = primary_service_url(service, environment) or "-"
    parsed = urllib.parse.urlparse(url) if url != "-" else None

    if parsed and parsed.scheme in {"http", "https"}:
        probe = health_probes.get(service.get("health_probe_id"), {})
        validate_tls = True
        if isinstance(probe, dict):
            readiness = probe.get("readiness")
            if isinstance(readiness, dict) and isinstance(readiness.get("validate_tls"), bool):
                validate_tls = readiness["validate_tls"]
        result = http_probe(url, timeout=timeout, validate_tls=validate_tls)
    elif parsed and parsed.scheme == "ssh":
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 22
        result = tcp_probe(host, port, timeout=timeout)
    else:
        probe = health_probes.get(service.get("health_probe_id"), {})
        readiness = probe.get("readiness") if isinstance(probe, dict) else None
        if isinstance(readiness, dict) and readiness.get("kind") == "tcp":
            result = tcp_probe(str(readiness.get("host")), int(readiness.get("port")), timeout=timeout)
            url = f"tcp://{readiness.get('host')}:{readiness.get('port')}"
        else:
            result = ProbeResult(service_id="", url=url, healthy=False, health_text="no reachable probe", latency_seconds=None)

    return ProbeResult(
        service_id=service["id"],
        url=url,
        healthy=result.healthy,
        health_text=result.health_text,
        latency_seconds=result.latency_seconds,
    )


def print_status_table(results: list[tuple[dict[str, Any], ProbeResult]], *, no_color: bool) -> None:
    enabled = not no_color and not NO_COLOR
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    print(f"PLATFORM STATUS (lv3)  {now}")
    print("-" * 92)
    print(f"{'SERVICE':<20} {'VM':<20} {'URL':<34} {'HEALTH':<10} {'LATENCY':>7}")
    overall_ok = True
    for service, result in results:
        if not result.healthy:
            overall_ok = False
        plain_status = result.health_text[:10]
        status_label = colorize(
            plain_status,
            "32" if result.healthy else "31",
            enabled=enabled,
        )
        latency = "-" if result.latency_seconds is None else f"{result.latency_seconds:.2f}s"
        status_cell = plain_status if not enabled else status_label
        print(
            f"{service['id']:<20} "
            f"{str(service.get('vm', '-')):<20} "
            f"{result.url[:34]:<34} "
            f"{status_cell:<10} "
            f"{latency:>7}"
        )
    latest = find_latest_receipt(None)
    if latest is not None:
        print()
        print(f"Last deploy: {latest.stem}")
    if not overall_ok:
        raise SystemExit(1)


def status_command(service_id: str | None, environment: str, *, timeout: float, no_color: bool) -> int:
    service_map = load_service_map()
    health_probes = load_health_probe_catalog()
    if service_id:
        services = [get_service_or_exit(service_map, service_id)]
    else:
        services = sorted(
            [service for service in service_map.values() if service.get("lifecycle_status") == "active"],
            key=lambda item: item["id"],
        )
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(services) or 1)) as executor:
        futures = {
            executor.submit(
                probe_one_service,
                service,
                health_probes,
                environment=environment,
                timeout=timeout,
            ): service
            for service in services
        }
        results = [(service, future.result()) for future, service in futures.items()]
    results.sort(key=lambda item: item[0]["id"])
    print_status_table(results, no_color=no_color)
    return 0


def find_latest_receipt(service_hint: str | None) -> Path | None:
    receipts_dir = repo_path("receipts", "live-applies")
    receipts = sorted(receipts_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not receipts:
        return None
    if not service_hint:
        return receipts[0]
    service_hint = service_hint.replace("-", "_")
    for receipt in receipts:
        try:
            payload = json.loads(receipt.read_text())
        except json.JSONDecodeError:
            continue
        haystacks = [
            receipt.stem,
            str(payload.get("summary", "")),
            str(payload.get("workflow_id", "")),
            " ".join(str(target.get("name", "")) for target in payload.get("targets", [])),
        ]
        normalized = " ".join(haystacks).replace("-", "_")
        if service_hint in normalized:
            return receipt
    return receipts[0]


def resolve_vm_inventory() -> list[tuple[str, str | None, str]]:
    inventory_path = repo_path("inventory", "hosts.yml")
    current_host: str | None = None
    host_ip: dict[str, str] = {}
    for raw_line in inventory_path.read_text().splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line.startswith("        ") and stripped.endswith(":") and not stripped.startswith("ansible_"):
            current_host = stripped[:-1]
            host_ip.setdefault(current_host, "")
            continue
        if "ansible_host:" in stripped and current_host:
            host_ip[current_host] = stripped.split(":", 1)[1].strip()
    result = []
    service_map = load_service_map()
    seen_hosts: set[str] = set()
    for service in service_map.values():
        vm = service.get("vm")
        if isinstance(vm, str) and vm not in seen_hosts:
            seen_hosts.add(vm)
            result.append((vm, host_ip.get(vm) or None, service["id"]))
    return sorted(result)


def vm_list_command(environment: str) -> int:
    print(f"VM INVENTORY ({environment})")
    print("-" * 72)
    print(f"{'VM':<24} {'ADDRESS':<18} {'SERVICE'}")
    for vm_name, address, service_id in resolve_vm_inventory():
        print(f"{vm_name:<24} {str(address or '-'):18} {service_id}")
    return 0


def ssh_command(vm_name: str, *, dry_run: bool, explain: bool, no_color: bool) -> int:
    address = None
    for candidate, addr, _service in resolve_vm_inventory():
        if candidate == vm_name:
            address = addr
            break
    if vm_name == "proxmox_florin" and address is None:
        address = "100.118.189.95"
    if not address:
        raise SystemExit(f"Unknown VM '{vm_name}'.")
    plan = CommandPlan(
        label=f"ssh {vm_name}",
        route="controller -> VM SSH session",
        command=["ssh", f"ops@{address}"],
    )
    print_plan(plan, no_color=no_color)
    if dry_run or explain:
        return 0
    os.execvp(plan.command[0], plan.command)
    return 0


def parse_since(value: str) -> datetime:
    unit = value[-1:]
    number = value[:-1]
    if unit not in {"m", "h", "d"} or not number.isdigit():
        raise SystemExit("Use --since with one of <Nm|Nh|Nd>, for example 10m or 2h.")
    count = int(number)
    delta = {"m": timedelta(minutes=count), "h": timedelta(hours=count), "d": timedelta(days=count)}[unit]
    return datetime.now(UTC) - delta


def loki_query_url(service_map: dict[str, dict[str, Any]]) -> str:
    if os.environ.get("LV3_LOKI_URL"):
        return os.environ["LV3_LOKI_URL"]
    grafana_service = get_service_or_exit(service_map, "grafana")
    monitoring_vm = grafana_service.get("vm")
    for vm_name, address, _service in resolve_vm_inventory():
        if vm_name == monitoring_vm and address:
            return f"http://{address}:3100/loki/api/v1/query_range"
    return "http://10.10.10.40:3100/loki/api/v1/query_range"


def logs_command(service_id: str, *, tail: int, since: str, dry_run: bool, explain: bool, no_color: bool) -> int:
    service_map = load_service_map()
    url = loki_query_url(service_map)
    start = parse_since(since)
    params = {
        "query": f'{{service="{service_id}"}}',
        "limit": str(tail),
        "direction": "backward",
        "start": str(int(start.timestamp() * 1_000_000_000)),
    }
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    plan = CommandPlan(
        label=f"logs {service_id}",
        route="controller -> Loki query API",
        command=["curl", full_url],
    )
    print_plan(plan, no_color=no_color)
    if dry_run or explain:
        return 0

    request = urllib.request.Request(full_url, headers={"User-Agent": "lv3-cli/0.1.0"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"Loki query failed: {exc}", file=sys.stderr)
        return 1

    results = payload.get("data", {}).get("result", [])
    if not results:
        print("No log lines found.")
        return 0
    lines: list[tuple[int, str]] = []
    for stream in results:
        stream_labels = stream.get("stream", {})
        label_text = ",".join(f"{key}={value}" for key, value in sorted(stream_labels.items()))
        for ts, line in stream.get("values", []):
            lines.append((int(ts), f"[{label_text}] {line.rstrip()}"))
    for _ts, line in sorted(lines, key=lambda item: item[0])[-tail:]:
        print(line)
    return 0


def generate_completion_script(shell_name: str) -> str:
    function_name = "_lv3_completion"
    if shell_name == "bash":
        return textwrap.dedent(
            f"""
            {COMPLETION_SENTINEL}
            {function_name}() {{
              local cur="${{COMP_WORDS[COMP_CWORD]}}"
              COMPREPLY=($(COMP_WORDS="${{COMP_WORDS[*]}}" COMP_CWORD=$COMP_CWORD lv3 __complete "$cur"))
            }}
            complete -F {function_name} lv3
            # <<< lv3 completion <<<
            """
        ).strip() + "\n"
    if shell_name == "zsh":
        return textwrap.dedent(
            f"""
            {COMPLETION_SENTINEL}
            {function_name}() {{
              local -a reply
              reply=("${{(@f)$(COMP_WORDS="$words" COMP_CWORD=$CURRENT lv3 __complete "$words[CURRENT]")}}")
              _describe 'values' reply
            }}
            compdef {function_name} lv3
            # <<< lv3 completion <<<
            """
        ).strip() + "\n"
    raise SystemExit("Completion shell must be one of: bash, zsh.")


def install_completion(shell_name: str) -> int:
    rc_map = {"bash": Path.home() / ".bashrc", "zsh": Path.home() / ".zshrc"}
    rc_path = rc_map[shell_name]
    block = generate_completion_script(shell_name)
    if rc_path.exists() and COMPLETION_SENTINEL in rc_path.read_text():
        print(f"Completion already installed in {rc_path}.")
        return 0
    with rc_path.open("a", encoding="utf-8") as handle:
        if rc_path.stat().st_size:
            handle.write("\n")
        handle.write(block)
    print(f"Installed lv3 completion into {rc_path}.")
    return 0


def completion_candidates(words: list[str], current: str) -> list[str]:
    top_level = [
        "deploy",
        "lint",
        "validate",
        "status",
        "vm",
        "secret",
        "fixture",
        "scaffold",
        "diff",
        "promote",
        "run",
        "release",
        "logs",
        "ssh",
        "open",
        "operator",
    ]
    if len(words) <= 1:
        return [candidate for candidate in top_level if candidate.startswith(current)]
    if words[1] in {"deploy", "status", "logs", "open"}:
        candidates = sorted(set(load_service_map()) | set(SERVICE_ALIASES))
        return [service_id for service_id in candidates if service_id.startswith(current)]
    if words[1] == "run":
        return [workflow_id for workflow_id in sorted(load_workflow_catalog()) if workflow_id.startswith(current)]
    if words[1] == "ssh":
        return [vm_name for vm_name, _address, _service in resolve_vm_inventory() if vm_name.startswith(current)]
    if words[1] == "vm" and len(words) == 3:
        return [action for action in ["create", "destroy", "resize", "list"] if action.startswith(current)]
    if words[1] == "fixture" and len(words) == 3:
        return [action for action in ["create", "destroy", "list", "up", "down"] if action.startswith(current)]
    if words[1] == "fixture" and len(words) == 4 and words[2] in {"up", "down", "create", "destroy"}:
        fixtures_dir = repo_path("tests", "fixtures")
        candidates = []
        if fixtures_dir.exists():
            for path in sorted(fixtures_dir.glob("*-fixture.yml")):
                candidates.append(path.name.removesuffix("-fixture.yml"))
        return [fixture_id for fixture_id in sorted(dict.fromkeys(candidates)) if fixture_id.startswith(current)]
    if words[1] == "secret" and len(words) == 3:
        return [action for action in ["get", "rotate"] if action.startswith(current)]
    if words[1] == "operator" and len(words) == 3:
        return [action for action in ["add", "remove", "inventory"] if action.startswith(current)]
    if words[1] == "release" and len(words) == 3:
        return [action for action in ["status"] if action.startswith(current)]
    return []


def handle_completion(current: str) -> int:
    words = os.environ.get("COMP_WORDS", "").split()
    if not words:
        words = sys.argv[1:]
    for candidate in completion_candidates(words, current):
        print(candidate)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified operator CLI for the LV3 platform.")
    parser.add_argument("--version", action="store_true", help="Print the lv3 CLI version.")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors.")
    parser.add_argument("--install-completion", choices=["bash", "zsh"], help="Install shell completion into the default rc file.")

    subparsers = parser.add_subparsers(dest="command")

    deploy = subparsers.add_parser("deploy", help="Deploy one service.")
    deploy.add_argument("service")
    deploy.add_argument("--env", default="production", choices=["production", "staging"])
    deploy.add_argument("--dry-run", action="store_true")
    deploy.add_argument("--explain", action="store_true")

    lint = subparsers.add_parser("lint", help="Run repository lint checks.")
    lint.add_argument("--local", action="store_true")
    lint.add_argument("--dry-run", action="store_true")
    lint.add_argument("--explain", action="store_true")

    validate = subparsers.add_parser("validate", help="Run repository validation.")
    validate.add_argument("--strict", action="store_true")
    validate.add_argument("--dry-run", action="store_true")
    validate.add_argument("--explain", action="store_true")

    status = subparsers.add_parser("status", help="Show service health status.")
    status.add_argument("service", nargs="?")
    status.add_argument("--env", default="production", choices=["production", "staging"])
    status.add_argument("--timeout", type=float, default=DEFAULT_STATUS_TIMEOUT_SECONDS)

    vm = subparsers.add_parser("vm", help="Operate on VM lifecycle routes.")
    vm_subparsers = vm.add_subparsers(dest="vm_action", required=True)
    vm_create = vm_subparsers.add_parser("create", help="Apply the VM environment.")
    vm_create.add_argument("name", nargs="?")
    vm_create.add_argument("--env", default="production", choices=["production", "staging"])
    vm_create.add_argument("--dry-run", action="store_true")
    vm_create.add_argument("--explain", action="store_true")
    vm_destroy = vm_subparsers.add_parser("destroy", help="Destroy one VM target.")
    vm_destroy.add_argument("name")
    vm_destroy.add_argument("--env", default="production", choices=["production", "staging"])
    vm_destroy.add_argument("--force", action="store_true")
    vm_destroy.add_argument("--dry-run", action="store_true")
    vm_destroy.add_argument("--explain", action="store_true")
    vm_resize = vm_subparsers.add_parser("resize", help="Open the VM IaC file in $EDITOR.")
    vm_resize.add_argument("name", nargs="?")
    vm_resize.add_argument("--env", default="production", choices=["production", "staging"])
    vm_resize.add_argument("--dry-run", action="store_true")
    vm_resize.add_argument("--explain", action="store_true")
    vm_list = vm_subparsers.add_parser("list", help="List known VMs.")
    vm_list.add_argument("--env", default="production", choices=["production", "staging"])

    secret = subparsers.add_parser("secret", help="Access managed secrets.")
    secret_subparsers = secret.add_subparsers(dest="secret_action", required=True)
    secret_get = secret_subparsers.add_parser("get", help="Read a secret through OpenBao.")
    secret_get.add_argument("path")
    secret_get.add_argument("--dry-run", action="store_true")
    secret_get.add_argument("--explain", action="store_true")
    secret_rotate = secret_subparsers.add_parser("rotate", help="Rotate one managed secret.")
    secret_rotate.add_argument("secret_id")
    secret_rotate.add_argument("--dry-run", action="store_true")
    secret_rotate.add_argument("--explain", action="store_true")

    fixture = subparsers.add_parser("fixture", help="Manage ephemeral fixtures.")
    fixture_subparsers = fixture.add_subparsers(dest="fixture_action", required=True)
    fixture_create = fixture_subparsers.add_parser("create", aliases=["up"], help="Create one ephemeral fixture VM.")
    fixture_create.add_argument("name", nargs="?")
    fixture_create.add_argument("--purpose")
    fixture_create.add_argument("--owner")
    fixture_create.add_argument("--lifetime-hours", type=float)
    fixture_create.add_argument(
        "--policy",
        default="adr-development",
        choices=["adr-development", "extended-fixture", "integration-test", "restore-verification"],
    )
    fixture_create.add_argument("--extend", action="store_true")
    fixture_create.add_argument("--dry-run", action="store_true")
    fixture_create.add_argument("--explain", action="store_true")
    fixture_destroy = fixture_subparsers.add_parser("destroy", aliases=["down"], help="Destroy one ephemeral fixture VM.")
    fixture_destroy.add_argument("name", nargs="?")
    fixture_destroy.add_argument("--vmid", type=int)
    fixture_destroy.add_argument("--receipt-id")
    fixture_destroy.add_argument("--dry-run", action="store_true")
    fixture_destroy.add_argument("--explain", action="store_true")
    fixture_list = fixture_subparsers.add_parser("list", help="List active fixtures.")
    fixture_list.add_argument("--dry-run", action="store_true")
    fixture_list.add_argument("--explain", action="store_true")

    scaffold = subparsers.add_parser("scaffold", help="Scaffold a new service.")
    scaffold.add_argument("name")
    scaffold.add_argument("--dry-run", action="store_true")
    scaffold.add_argument("--explain", action="store_true")

    diff = subparsers.add_parser("diff", help="Show infrastructure drift.")
    diff.add_argument("--env", default="production", choices=["production", "staging"])
    diff.add_argument("--dry-run", action="store_true")
    diff.add_argument("--explain", action="store_true")

    promote = subparsers.add_parser("promote", help="Run the promotion pipeline.")
    promote.add_argument("branch")
    promote.add_argument("--service", required=True)
    promote.add_argument("--staging-receipt", required=True)
    promote.add_argument("--to", choices=["staging", "production"], default="production")
    promote.add_argument("--dry-run", action="store_true")
    promote.add_argument("--explain", action="store_true")

    run = subparsers.add_parser("run", help="Trigger one Windmill workflow.")
    run.add_argument("workflow")
    run.add_argument("--args", nargs="*", default=[])
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--explain", action="store_true")

    release = subparsers.add_parser("release", help="Show release-readiness information.")
    release_subparsers = release.add_subparsers(dest="release_action", required=True)
    release_subparsers.add_parser("status", help="Show current 1.0.0 readiness criteria.")

    logs = subparsers.add_parser("logs", help="Query service logs from Loki.")
    logs.add_argument("service")
    logs.add_argument("--tail", type=int, default=DEFAULT_LOG_LINES)
    logs.add_argument("--since", default=DEFAULT_LOG_SINCE)
    logs.add_argument("--dry-run", action="store_true")
    logs.add_argument("--explain", action="store_true")

    ssh = subparsers.add_parser("ssh", help="Open an SSH session to one VM.")
    ssh.add_argument("vm_name")
    ssh.add_argument("--dry-run", action="store_true")
    ssh.add_argument("--explain", action="store_true")

    open_parser = subparsers.add_parser("open", help="Open one service URL.")
    open_parser.add_argument("service")
    open_parser.add_argument("--env", default="production", choices=["production", "staging"])
    open_parser.add_argument("--dry-run", action="store_true")
    open_parser.add_argument("--explain", action="store_true")

    operator = subparsers.add_parser("operator", help="Manage human operator access.")
    operator_subparsers = operator.add_subparsers(dest="operator_action", required=True)
    operator_add = operator_subparsers.add_parser("add", help="Run the operator onboarding workflow.")
    operator_add.add_argument("--name", required=True)
    operator_add.add_argument("--email", required=True)
    operator_add.add_argument("--role", required=True, choices=["admin", "operator", "viewer"])
    operator_add.add_argument("--ssh-key", default="")
    operator_add.add_argument("--id")
    operator_add.add_argument("--keycloak-username")
    operator_add.add_argument("--tailscale-login-email")
    operator_add.add_argument("--tailscale-device-name")
    operator_add.add_argument("--dry-run", action="store_true")
    operator_add.add_argument("--explain", action="store_true")

    operator_remove = operator_subparsers.add_parser("remove", help="Run the operator offboarding workflow.")
    operator_remove.add_argument("--id", required=True)
    operator_remove.add_argument("--reason")
    operator_remove.add_argument("--dry-run", action="store_true")
    operator_remove.add_argument("--explain", action="store_true")

    operator_inventory = operator_subparsers.add_parser("inventory", help="Show one operator access inventory.")
    operator_inventory.add_argument("--id", required=True)
    operator_inventory.add_argument("--offline", action="store_true")
    operator_inventory.add_argument("--dry-run", action="store_true")
    operator_inventory.add_argument("--explain", action="store_true")

    completion = subparsers.add_parser("__complete")
    completion.add_argument("current", nargs="?", default="")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2
    no_color = bool(getattr(args, "no_color", False))

    if args.version:
        print(CLI_VERSION)
        return 0
    if args.install_completion:
        return install_completion(args.install_completion)
    if args.command == "__complete":
        return handle_completion(args.current)
    if not args.command:
        parser.print_help()
        return 0

    if args.command == "deploy":
        return run_plan(resolve_deploy_command(args.service, args.env), dry_run=args.dry_run, explain=args.explain, no_color=no_color)
    if args.command == "lint":
        return run_plan(resolve_lint_command(args.local), dry_run=args.dry_run, explain=args.explain, no_color=no_color)
    if args.command == "validate":
        return run_plan(resolve_validate_command(args.strict), dry_run=args.dry_run, explain=args.explain, no_color=no_color)
    if args.command == "status":
        return status_command(args.service, args.env, timeout=args.timeout, no_color=no_color)
    if args.command == "vm":
        if args.vm_action == "list":
            return vm_list_command(args.env)
        plan = resolve_vm_command(args.vm_action, args.env, vm_name=getattr(args, "name", None), force=getattr(args, "force", False))
        return run_plan(plan, dry_run=getattr(args, "dry_run", False), explain=getattr(args, "explain", False), no_color=no_color)
    if args.command == "secret":
        if args.secret_action == "get":
            return run_plan(secret_get_command(args.path), dry_run=args.dry_run, explain=args.explain, no_color=no_color)
        return run_plan(secret_rotate_command(args.secret_id), dry_run=args.dry_run, explain=args.explain, no_color=no_color)
    if args.command == "fixture":
        return run_plan(
            fixture_command(
                args.fixture_action,
                getattr(args, "name", None),
                purpose=getattr(args, "purpose", None),
                owner=getattr(args, "owner", None),
                lifetime_hours=getattr(args, "lifetime_hours", None),
                policy=getattr(args, "policy", None),
                extend=getattr(args, "extend", False),
                vmid=getattr(args, "vmid", None),
                receipt_id=getattr(args, "receipt_id", None),
            ),
            dry_run=args.dry_run,
            explain=args.explain,
            no_color=no_color,
        )
    if args.command == "scaffold":
        return run_plan(scaffold_command(args.name), dry_run=args.dry_run, explain=args.explain, no_color=no_color)
    if args.command == "diff":
        return run_plan(resolve_diff_command(args.env), dry_run=args.dry_run, explain=args.explain, no_color=no_color)
    if args.command == "promote":
        return run_plan(
            promote_command(args.branch, args.service, args.staging_receipt, args.dry_run),
            dry_run=args.dry_run,
            explain=args.explain,
            no_color=no_color,
        )
    if args.command == "run":
        return run_windmill_workflow(args.workflow, args.args, dry_run=args.dry_run, explain=args.explain, no_color=no_color)
    if args.command == "release":
        if args.release_action == "status":
            from generate_dr_report import build_dr_report, render_release_status

            print(render_release_status(build_dr_report()))
            return 0
    if args.command == "logs":
        return logs_command(args.service, tail=args.tail, since=args.since, dry_run=args.dry_run, explain=args.explain, no_color=no_color)
    if args.command == "ssh":
        return ssh_command(args.vm_name, dry_run=args.dry_run, explain=args.explain, no_color=no_color)
    if args.command == "open":
        return open_service_url(args.service, args.env, dry_run=args.dry_run, explain=args.explain, no_color=no_color)
    if args.command == "operator":
        if args.operator_action == "add":
            workflow_args = [
                f"name={args.name}",
                f"email={args.email}",
                f"role={args.role}",
                f"ssh_key={args.ssh_key}",
            ]
            if args.id:
                workflow_args.append(f"operator_id={args.id}")
            if args.keycloak_username:
                workflow_args.append(f"keycloak_username={args.keycloak_username}")
            if args.tailscale_login_email:
                workflow_args.append(f"tailscale_login_email={args.tailscale_login_email}")
            if args.tailscale_device_name:
                workflow_args.append(f"tailscale_device_name={args.tailscale_device_name}")
            return run_windmill_workflow(
                "operator-onboard",
                workflow_args,
                dry_run=args.dry_run,
                explain=args.explain,
                no_color=no_color,
            )
        if args.operator_action == "remove":
            workflow_args = [f"operator_id={args.id}"]
            if args.reason:
                workflow_args.append(f"reason={args.reason}")
            return run_windmill_workflow(
                "operator-offboard",
                workflow_args,
                dry_run=args.dry_run,
                explain=args.explain,
                no_color=no_color,
            )
        return run_plan(
            operator_inventory_command(args.id, offline=args.offline),
            dry_run=args.dry_run,
            explain=args.explain,
            no_color=no_color,
        )

    raise SystemExit(f"Unhandled command '{args.command}'.")


if __name__ == "__main__":
    sys.exit(main())
