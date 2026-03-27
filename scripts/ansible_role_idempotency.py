#!/usr/bin/env python3

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import subprocess
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLES_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"
CONFIG_PATH = REPO_ROOT / "config" / "ansible-role-idempotency.yml"
DEFAULT_INVENTORY_PATH = REPO_ROOT / "tests" / "idempotency" / "localhost.ini"
TRACKED_POLICY = "tracked"
EXEMPT_POLICY = "exempt"
ENFORCED_POLICY = "enforced"
ALLOWED_POLICIES = {TRACKED_POLICY, EXEMPT_POLICY, ENFORCED_POLICY}
TASK_PATTERN = re.compile(r"^TASK \[(?P<label>.+?)\]\s+\*+$")
HOST_RESULT_PATTERN = re.compile(r"^(?P<kind>changed|fatal): \[(?P<host>[^\]]+)\]")


@dataclass(frozen=True)
class RoleResult:
    role: str
    status: str
    detail: str


def role_names() -> list[str]:
    return sorted(path.name for path in ROLES_ROOT.iterdir() if path.is_dir())


def load_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a mapping")
    if payload.get("schema_version") != "1.0.0":
        raise ValueError(f"{path} must declare schema_version: 1.0.0")
    roles = payload.get("roles")
    if not isinstance(roles, dict):
        raise ValueError(f"{path} must define a roles mapping")
    return payload


def validate_config(config: dict[str, Any], *, path: Path) -> tuple[list[str], list[str], list[str]]:
    configured_roles = sorted(config["roles"].keys())
    actual_roles = role_names()
    if configured_roles != actual_roles:
        missing = sorted(set(actual_roles) - set(configured_roles))
        extra = sorted(set(configured_roles) - set(actual_roles))
        details: list[str] = []
        if missing:
            details.append(f"missing roles: {', '.join(missing)}")
        if extra:
            details.append(f"unknown roles: {', '.join(extra)}")
        raise ValueError(f"{path} does not match the role tree: {'; '.join(details)}")

    enforced: list[str] = []
    tracked: list[str] = []
    exempt: list[str] = []

    for role, entry in sorted(config["roles"].items()):
        if not isinstance(entry, dict):
            raise ValueError(f"{path} role '{role}' must map to a policy definition")
        policy = entry.get("policy")
        if policy not in ALLOWED_POLICIES:
            raise ValueError(f"{path} role '{role}' has unsupported policy '{policy}'")
        reason = str(entry.get("reason") or "").strip()
        if not reason:
            raise ValueError(f"{path} role '{role}' must define a non-empty reason")
        if policy == ENFORCED_POLICY:
            scenario = entry.get("scenario")
            if not isinstance(scenario, dict):
                raise ValueError(f"{path} role '{role}' must define a scenario mapping")
            playbook = scenario.get("playbook")
            if not isinstance(playbook, str) or not playbook.strip():
                raise ValueError(f"{path} role '{role}' must define scenario.playbook")
            playbook_path = REPO_ROOT / playbook
            if not playbook_path.is_file():
                raise ValueError(f"{path} role '{role}' references missing playbook {playbook}")
            enforced.append(role)
            continue
        if policy == TRACKED_POLICY:
            tracked.append(role)
            continue
        exempt.append(role)

    return enforced, tracked, exempt


def ansible_playbook_command() -> list[str]:
    override = os.environ.get("ANSIBLE_PLAYBOOK_BIN")
    if override:
        return [override]
    return ["uvx", "--from", "ansible-core", "ansible-playbook"]


def format_changed_task(record: dict[str, Any]) -> str:
    host = str(record.get("host") or "unknown")
    role = str(record.get("role") or "").strip()
    task = str(record.get("task") or "unknown task").strip()
    label = f"{role} : {task}" if role else task
    return f"{host}: {label}"


def parse_changed_records(payload: str) -> list[dict[str, Any]]:
    text = payload.strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return parse_changed_records_from_text(text)
    if not isinstance(parsed, dict):
        return []
    return parse_changed_records_from_json(parsed)


def parse_changed_records_from_json(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for play in parsed.get("plays", []):
        if not isinstance(play, dict):
            continue
        for task_entry in play.get("tasks", []):
            if not isinstance(task_entry, dict):
                continue
            task_meta = task_entry.get("task", {})
            label = str(task_meta.get("name", "")).strip()
            hosts = task_entry.get("hosts", {})
            if not isinstance(hosts, dict):
                continue
            for host, result in hosts.items():
                if not isinstance(result, dict) or not result.get("changed"):
                    continue
                role = None
                task = label or "unknown task"
                if " : " in task:
                    role, task = (part.strip() for part in task.split(" : ", 1))
                records.append({"host": host, "role": role, "task": task})
    return records


def parse_changed_records_from_text(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    current_role: str | None = None
    current_task = "unknown task"
    for line in text.splitlines():
        task_match = TASK_PATTERN.match(line.rstrip())
        if task_match:
            label = task_match.group("label").strip()
            if " : " in label:
                current_role, current_task = (part.strip() for part in label.split(" : ", 1))
            else:
                current_role = None
                current_task = label
            continue
        host_match = HOST_RESULT_PATTERN.match(line.rstrip())
        if host_match and host_match.group("kind") == "changed":
            records.append({"host": host_match.group("host"), "role": current_role, "task": current_task})
    return records


class FixtureHandler(BaseHTTPRequestHandler):
    routes: dict[str, dict[str, Any]] = {}

    def do_GET(self) -> None:  # noqa: N802
        route = self.routes.get(self.path)
        if route is None:
            self.send_response(404)
            self.end_headers()
            return
        status = int(route.get("status", 200))
        payload = route.get("json")
        body = route.get("body")
        headers = route.get("headers", {})
        if isinstance(body, str):
            response_body = body.encode("utf-8")
        else:
            response_body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(str(key), str(value))
        if payload is not None and "Content-Type" not in headers:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        del fmt, args


@contextlib.contextmanager
def http_fixture_server(fixture: dict[str, Any] | None) -> Any:
    if not fixture:
        yield None
        return
    responses = fixture.get("responses")
    if not isinstance(responses, dict) or not responses:
        raise ValueError("http_fixture.responses must be a non-empty mapping")
    handler = type("ConfiguredFixtureHandler", (FixtureHandler,), {"routes": responses})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def run_ansible_playbook(playbook: Path, *, inventory: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    command = [*ansible_playbook_command(), "-i", str(inventory), str(playbook)]
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def run_enforced_role(role: str, entry: dict[str, Any]) -> RoleResult:
    scenario = entry["scenario"]
    playbook = REPO_ROOT / scenario["playbook"]
    inventory = REPO_ROOT / str(scenario.get("inventory") or DEFAULT_INVENTORY_PATH.relative_to(REPO_ROOT))

    environment = os.environ.copy()
    environment["ANSIBLE_CONFIG"] = str(REPO_ROOT / "ansible.cfg")
    environment["ANSIBLE_COLLECTIONS_PATH"] = str(REPO_ROOT / "collections")
    environment["ANSIBLE_NOCOLOR"] = "1"
    for key, value in (scenario.get("environment") or {}).items():
        environment[str(key)] = str(value)

    with http_fixture_server(scenario.get("http_fixture")) as base_url:
        if base_url:
            environment["IDEMPOTENCY_FIXTURE_URL"] = base_url

        first_run = run_ansible_playbook(playbook, inventory=inventory, env=environment)
        if first_run.returncode != 0:
            detail = first_run.stderr.strip() or first_run.stdout.strip() or "first converge run failed"
            return RoleResult(role=role, status="failed", detail=detail)

        second_run = run_ansible_playbook(playbook, inventory=inventory, env=environment)
        if second_run.returncode != 0:
            detail = second_run.stderr.strip() or second_run.stdout.strip() or "second idempotency run failed"
            return RoleResult(role=role, status="failed", detail=detail)

    changed_records = parse_changed_records(second_run.stdout)
    if changed_records:
        changed_tasks = ", ".join(sorted(format_changed_task(record) for record in changed_records))
        return RoleResult(role=role, status="failed", detail=f"changed on second run: {changed_tasks}")

    return RoleResult(role=role, status="passed", detail="zero changes on second run")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate repo-managed Ansible role idempotency coverage.")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--role", action="append", dest="roles", default=[], help="Restrict runtime checks to one or more enforced roles.")
    parser.add_argument("--manifest-only", action="store_true", help="Validate policy coverage without running enforced scenarios.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    enforced, tracked, exempt = validate_config(config, path=args.config)

    requested_roles = sorted(set(args.roles))
    if requested_roles:
        unknown_roles = sorted(set(requested_roles) - set(enforced))
        if unknown_roles:
            raise SystemExit(
                f"--role only supports enforced roles. Unsupported selection: {', '.join(unknown_roles)}"
            )
        enforced = [role for role in enforced if role in requested_roles]

    print(
        "Validated Ansible role idempotency policy: "
        f"{len(enforced)} enforced, {len(tracked)} tracked, {len(exempt)} exempt."
    )
    if tracked:
        print("Tracked roles remain on the migration inventory until they gain a CI-safe scenario.")

    if args.manifest_only:
        return 0

    failures: list[RoleResult] = []
    for role in enforced:
        result = run_enforced_role(role, config["roles"][role])
        print(f"{result.status.upper():7} {role}: {result.detail}")
        if result.status != "passed":
            failures.append(result)

    if failures:
        print("\nIdempotency failures:")
        for result in failures:
            print(f"- {result.role}: {result.detail}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
