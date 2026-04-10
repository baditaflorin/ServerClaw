import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "docker_runtime"
    / "tasks"
    / "main.yml"
)
ROLE_DEFAULTS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "docker_runtime"
    / "defaults"
    / "main.yml"
)
ROLE_VERIFY = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "docker_runtime"
    / "tasks"
    / "verify.yml"
)
COMMON_DOCKER_BRIDGE_CHAINS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "common"
    / "tasks"
    / "docker_bridge_chains.yml"
)
FIREWALL_TEMPLATE = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "linux_guest_firewall"
    / "templates"
    / "nftables.conf.j2"
)


def load_tasks() -> list[dict]:
    return yaml.safe_load(ROLE_TASKS.read_text())


def load_defaults() -> dict:
    return yaml.safe_load(ROLE_DEFAULTS.read_text())


def load_verify() -> list[dict]:
    return yaml.safe_load(ROLE_VERIFY.read_text())


def load_common_docker_bridge_chains() -> list[dict]:
    return yaml.safe_load(COMMON_DOCKER_BRIDGE_CHAINS.read_text())


def test_docker_runtime_patches_nftables_before_starting_docker() -> None:
    tasks = load_tasks()
    task_names = [task["name"] for task in tasks]
    assert task_names.index("Inspect Docker repository prerequisite package status") < task_names.index(
        "Record missing Docker repository prerequisites"
    )
    assert task_names.index("Record missing Docker repository prerequisites") < task_names.index(
        "Install Docker repository prerequisites"
    )
    assert task_names.index("Inspect conflicting Docker package status") < task_names.index(
        "Record conflicting Docker packages that are currently installed"
    )
    assert task_names.index("Record conflicting Docker packages that are currently installed") < task_names.index(
        "Remove conflicting Docker packages"
    )
    assert task_names.index("Inspect Docker runtime package status") < task_names.index(
        "Record missing Docker runtime packages"
    )
    assert task_names.index("Record missing Docker runtime packages") < task_names.index(
        "Install Docker runtime packages"
    )
    assert task_names.index("Apply Docker bridge forward-compat rules live without reloading nftables") < task_names.index(
        "Persist required Docker kernel modules across reboot"
    )
    assert task_names.index("Persist required Docker kernel modules across reboot") < task_names.index(
        "Load required Docker kernel modules before starting Docker"
    )
    assert task_names.index("Load required Docker kernel modules before starting Docker") < task_names.index(
        "Ensure Docker socket activation is enabled and listening"
    )
    assert task_names.index("Ensure Docker socket activation is enabled and listening") < task_names.index(
        "Ensure Docker service is enabled and running"
    )

    defaults = load_defaults()
    persist_modules = next(task for task in tasks if task["name"] == "Persist required Docker kernel modules across reboot")
    load_modules = next(task for task in tasks if task["name"] == "Load required Docker kernel modules before starting Docker")
    ensure_docker_socket = next(task for task in tasks if task["name"] == "Ensure Docker socket activation is enabled and listening")
    assert defaults["docker_runtime_kernel_modules"] == ["iptable_nat"]
    assert defaults["docker_runtime_kernel_modules_file"] == "/etc/modules-load.d/lv3-docker-runtime.conf"
    assert persist_modules["ansible.builtin.copy"]["dest"] == "{{ docker_runtime_kernel_modules_file }}"
    assert persist_modules["when"] == "docker_runtime_kernel_modules | length > 0"
    assert load_modules["ansible.builtin.command"]["argv"] == ["modprobe", "{{ item }}"]
    assert load_modules["loop"] == "{{ docker_runtime_kernel_modules }}"
    assert load_modules["changed_when"] is False
    assert ensure_docker_socket["ansible.builtin.systemd_service"] == {
        "name": "docker.socket",
        "enabled": True,
        "state": "started",
    }


def test_docker_runtime_rechecks_nat_and_forward_chains() -> None:
    tasks = load_tasks()
    defaults = load_defaults()
    task_names = {task["name"] for task in tasks}
    assert "Record container ids that are running before Docker restarts" in task_names
    assert "Inspect running containers before Docker restarts" in task_names
    assert "Record containers that were running before Docker restarts" in task_names
    assert "Flush Docker handlers before chain health checks" in task_names
    assert "Reset Docker failed state before nat-chain recovery restart" in task_names
    assert "Ensure Docker bridge networking chains are present" in task_names
    assert "Re-inspect pre-restart containers after Docker restarts" in task_names
    assert "Record pre-restart containers that remained stopped after Docker restarts" in task_names
    assert "Record whether Docker recovery needs the local OpenBao API unsealed" in task_names
    assert "Flag OpenBao-backed compose services before Docker container recovery" in task_names
    assert "Load the OpenBao init payload before Docker container recovery touches OpenBao-backed services" in task_names
    assert "Ensure the local OpenBao API is unsealed before Docker container recovery touches OpenBao-backed services" in task_names
    assert "Recover pre-restart containers that remained stopped after Docker restarts" in task_names
    assert "Confirm pre-restart containers recovered after Docker restarts" in task_names
    inspect_pre_restart = next(task for task in tasks if task["name"] == "Inspect running containers before Docker restarts")
    record_containers = next(task for task in tasks if task["name"] == "Record containers that were running before Docker restarts")
    ensure_task = next(task for task in tasks if task["name"] == "Ensure Docker bridge networking chains are present")
    recheck_pre_restart = next(task for task in tasks if task["name"] == "Re-inspect pre-restart containers after Docker restarts")
    record_stopped = next(
        task for task in tasks if task["name"] == "Record pre-restart containers that remained stopped after Docker restarts"
    )
    record_openbao_requirement = next(
        task for task in tasks if task["name"] == "Record whether Docker recovery needs the local OpenBao API unsealed"
    )
    flag_openbao_requirement = next(
        task for task in tasks if task["name"] == "Flag OpenBao-backed compose services before Docker container recovery"
    )
    load_openbao_init = next(
        task for task in tasks if task["name"] == "Load the OpenBao init payload before Docker container recovery touches OpenBao-backed services"
    )
    ensure_openbao_unsealed = next(
        task
        for task in tasks
        if task["name"] == "Ensure the local OpenBao API is unsealed before Docker container recovery touches OpenBao-backed services"
    )
    recover_containers = next(task for task in tasks if task["name"] == "Recover pre-restart containers that remained stopped after Docker restarts")
    confirm_recovery = next(task for task in tasks if task["name"] == "Confirm pre-restart containers recovered after Docker restarts")
    include_role = ensure_task["ansible.builtin.include_role"]
    assert include_role["name"] == "lv3.platform.common"
    assert include_role["tasks_from"] == "docker_bridge_chains"
    assert ensure_task["vars"]["common_docker_bridge_chains_service_name"] == "docker"
    assert ensure_task["vars"]["common_docker_bridge_chains_require_nat_chain"] == "{{ docker_runtime_require_nat_chain }}"
    assert defaults["docker_runtime_chain_recheck_retries"] == 30
    assert defaults["docker_runtime_chain_recheck_delay_seconds"] == 2
    assert defaults["docker_runtime_container_recovery_retries"] == 30
    assert defaults["docker_runtime_container_recovery_delay_seconds"] == 5
    assert defaults["docker_runtime_openbao_recovery_timeout_seconds"] == 180
    assert defaults["docker_runtime_openbao_recovery_delay_seconds"] == 5
    assert defaults["docker_runtime_nonpersistent_restart_policies"] == ["", "no"]
    assert ensure_task["vars"]["common_docker_bridge_chains_retries"] == "{{ docker_runtime_chain_recheck_retries }}"
    assert ensure_task["vars"]["common_docker_bridge_chains_delay"] == "{{ docker_runtime_chain_recheck_delay_seconds }}"
    reset_task = next(task for task in tasks if task["name"] == "Reset Docker failed state before nat-chain recovery restart")
    assert reset_task["ansible.builtin.command"] == "systemctl reset-failed docker.service"
    assert reset_task["changed_when"] is False
    assert inspect_pre_restart["ansible.builtin.command"]["argv"][:2] == ["python3", "-c"]
    assert inspect_pre_restart["ansible.builtin.command"]["stdin"] == "{{ docker_runtime_pre_restart_container_ids.stdout_lines | to_json }}"
    assert '["docker", "inspect", container_id]' in inspect_pre_restart["ansible.builtin.command"]["argv"][2]
    assert '"no such object" in stderr' in inspect_pre_restart["ansible.builtin.command"]["argv"][2]
    assert "docker_runtime_pre_restart_container_details" in record_containers["ansible.builtin.set_fact"]
    assert "RestartPolicy" not in record_containers["ansible.builtin.set_fact"]["docker_runtime_pre_restart_container_names"]
    assert recheck_pre_restart["ansible.builtin.command"]["argv"][:2] == ["python3", "-c"]
    assert recheck_pre_restart["ansible.builtin.command"]["stdin"] == (
        "{{ docker_runtime_pre_restart_container_names | default([]) | to_json }}"
    )
    assert '["docker", "inspect", container_name]' in recheck_pre_restart["ansible.builtin.command"]["argv"][2]
    assert "docker_runtime_stopped_pre_restart_container_details" in record_stopped["ansible.builtin.set_fact"]
    assert record_openbao_requirement["ansible.builtin.set_fact"] == {
        "docker_runtime_recovery_requires_openbao_unseal": False
    }
    assert flag_openbao_requirement["loop"] == "{{ docker_runtime_stopped_pre_restart_container_details | default([]) }}"
    assert any(
        "item.Config.Labels['com.docker.compose.service']" in condition
        for condition in flag_openbao_requirement["when"]
    )
    assert load_openbao_init["ansible.builtin.set_fact"] == {
        "docker_runtime_openbao_init_payload": "{{ lookup('ansible.builtin.file', openbao_init_local_file) | from_json }}"
    }
    assert load_openbao_init["when"] == "docker_runtime_recovery_requires_openbao_unseal | bool"
    assert load_openbao_init["no_log"] is True
    assert ensure_openbao_unsealed["ansible.builtin.include_role"] == {
        "name": "lv3.platform.openbao_runtime",
        "tasks_from": "ensure_unsealed",
    }
    assert ensure_openbao_unsealed["vars"]["openbao_unseal_context"] == "Docker container recovery after Docker restarts"
    assert ensure_openbao_unsealed["vars"]["openbao_unseal_init_payload"] == "{{ docker_runtime_openbao_init_payload }}"
    assert ensure_openbao_unsealed["when"] == "docker_runtime_recovery_requires_openbao_unseal | bool"
    assert ensure_openbao_unsealed["no_log"] is True
    assert recover_containers["ansible.builtin.command"]["argv"][:2] == ["python3", "-c"]
    assert "".join(recover_containers["ansible.builtin.command"]["stdin"].split()) == (
        "{{(docker_runtime_stopped_pre_restart_container_details|default([]))|to_json}}"
    )
    assert "TRANSIENT_DOCKER_NETWORK_ERRORS" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "TRANSIENT_DOCKER_NETWORK_RETRY_ATTEMPTS = 12" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "TRANSIENT_DOCKER_NETWORK_RETRY_DELAY_SECONDS = 5" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "STALE_COMPOSE_ENDPOINT_ERRORS" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "retry_on_any_error=False" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "def combined_output(stdout, stderr):" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "def exception_output(exc):" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert 'DOCKER_NAT_CHAIN_COMMAND = ["iptables", "-t", "nat", "-S", "DOCKER"]' in (
        recover_containers["ansible.builtin.command"]["argv"][2]
    )
    assert 'DOCKER_SERVICE_ACTIVE_COMMAND = ["systemctl", "is-active", "docker"]' in (
        recover_containers["ansible.builtin.command"]["argv"][2]
    )
    assert "OPENBAO_HEALTH_URL" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "OPENBAO_SEAL_STATUS_URL" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "OPENBAO_UNSEAL_URL" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "OPENBAO_UNSEAL_KEYS" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "OPENBAO_RECOVERY_TIMEOUT_SECONDS" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "OPENBAO_RECOVERY_DELAY_SECONDS" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "read_openbao_json" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "submit_local_openbao_unseal_key" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "ensure_local_openbao_unsealed" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "wait_for_local_openbao" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "services_need_local_openbao" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "services_provide_local_openbao" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert '"http://127.0.0.1:8201/v1/sys/health"' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert '"http://127.0.0.1:8201/v1/sys/seal-status"' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert '"http://127.0.0.1:8201/v1/sys/unseal"' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "OPENBAO_READY_STATUS_CODES = {200, 429, 472, 473, 501, 503}" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "def wait_for_docker_nat_chain(retries=12, delay_seconds=2):" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "def docker_service_is_active():" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "def restart_docker_service_for_recovery():" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "def ensure_docker_service_ready():" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "def compose_group_sort_key(item):" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "NONPERSISTENT_RESTART_POLICIES" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert '["systemctl", "reset-failed", "docker.service"]' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert '["systemctl", "restart", "docker.service"]' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert 'compose_depends_on = labels.get("com.docker.compose.depends_on") or ""' in (
        recover_containers["ansible.builtin.command"]["argv"][2]
    )
    assert 'compose_group["services"].update(dependency_services)' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "No chain/target/match by that name" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "failed to create endpoint" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "ensure_docker_service_ready()" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "retry_on_any_error=True" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert 'attempts=5,' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert 'delay_seconds=5,' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "run_with_retry(" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "cwd=working_dir or None" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "wait_for_docker_nat_chain()" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "def is_local_openbao_group(" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert 'normalized_working_dir == "/opt/openbao"' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert '"lv3-openbao" in container_names' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "restart_policy_name not in NONPERSISTENT_RESTART_POLICIES" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert 'service == "openbao-agent" or service.endswith("-openbao-agent")' in (
        recover_containers["ansible.builtin.command"]["argv"][2]
    )
    assert 'service == "openbao"' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "if services_provide_local_openbao(services):" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "elif services_need_local_openbao(services):" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "def compose_group_recovery_sort_key(item):" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "return compose_group_sort_key(item)" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "if services_need_local_openbao(services) and not local_openbao_group:" in (
        recover_containers["ansible.builtin.command"]["argv"][2]
    )
    assert "key=compose_group_recovery_sort_key" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert 'remove_command = ["docker", "rm", "-f", *container_names]' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert 'recovery_command.extend(["up", "-d", "--force-recreate", *services])' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert 'down_command.extend(["down", "--remove-orphans"])' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert 'final_up_command.extend(["up", "-d", *services])' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "docker_compose_down_remove_orphans" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "docker_compose_up_after_down" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "docker_skip_missing_direct_start" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "com.docker.compose.project.working_dir" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "docker_compose_up" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert 'command.extend(["up", "-d", "--force-recreate", *services])' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert recover_containers["failed_when"] is False
    assert 'stopped = [container for container in containers if not container.get("State", {}).get("Running")]' not in (
        recover_containers["ansible.builtin.command"]["argv"][2]
    )
    assert "for container in containers:" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert confirm_recovery["ansible.builtin.command"]["argv"][:2] == ["python3", "-c"]
    assert confirm_recovery["ansible.builtin.command"]["stdin"] == (
        "{{ docker_runtime_pre_restart_container_details | default([]) | to_json }}"
    )
    assert '["docker", "inspect", name]' in confirm_recovery["ansible.builtin.command"]["argv"][2]
    assert "NONPERSISTENT_RESTART_POLICIES" in confirm_recovery["ansible.builtin.command"]["argv"][2]
    assert "SUCCESSFUL_EXIT_RESTART_POLICIES" in confirm_recovery["ansible.builtin.command"]["argv"][2]
    assert "def inspect_container(name):" in confirm_recovery["ansible.builtin.command"]["argv"][2]
    assert "def inspect_compose_replacement(container):" in confirm_recovery["ansible.builtin.command"]["argv"][2]
    assert 'f"label=com.docker.compose.project={compose_project}"' in confirm_recovery["ansible.builtin.command"]["argv"][2]
    assert 'f"label=com.docker.compose.service={compose_service}"' in confirm_recovery["ansible.builtin.command"]["argv"][2]
    assert "restart_policy_name" in confirm_recovery["ansible.builtin.command"]["argv"][2]
    assert (
        'SUCCESSFUL_EXIT_RESTART_POLICIES = NONPERSISTENT_RESTART_POLICIES | {"on-failure"}'
        in confirm_recovery["ansible.builtin.command"]["argv"][2]
    )
    assert "require_running = restart_policy_name not in SUCCESSFUL_EXIT_RESTART_POLICIES" in (
        confirm_recovery["ansible.builtin.command"]["argv"][2]
    )
    assert "restart_policy_name in SUCCESSFUL_EXIT_RESTART_POLICIES" in confirm_recovery["ansible.builtin.command"]["argv"][2]
    assert 'and status == "exited"' in confirm_recovery["ansible.builtin.command"]["argv"][2]
    assert '"healthy": healthy' in confirm_recovery["ansible.builtin.command"]["argv"][2]
    assert "sys.exit(0 if all_running else 1)" in confirm_recovery["ansible.builtin.command"]["argv"][2]
    assert confirm_recovery["retries"] == "{{ docker_runtime_container_recovery_retries }}"
    assert confirm_recovery["delay"] == "{{ docker_runtime_container_recovery_delay_seconds }}"
    assert confirm_recovery["until"] == "docker_runtime_recovered_container_inspect.rc == 0"


def test_docker_runtime_accepts_clean_on_failure_exit_after_restart(tmp_path: Path) -> None:
    tasks = load_tasks()
    confirm_recovery = next(task for task in tasks if task["name"] == "Confirm pre-restart containers recovered after Docker restarts")
    script = confirm_recovery["ansible.builtin.command"]["argv"][2]
    script = script.replace(
        "{{ docker_runtime_nonpersistent_restart_policies | to_json }}",
        json.dumps(load_defaults()["docker_runtime_nonpersistent_restart_policies"]),
    )
    fake_docker = tmp_path / "docker"
    fake_docker.write_text(
        """#!/bin/sh
if [ "$1" = "inspect" ] && [ "$2" = "plane-migrator" ]; then
  cat <<'JSON'
[{"Name":"/plane-migrator","State":{"Running":false,"Status":"exited","ExitCode":0}}]
JSON
  exit 0
fi
echo "unexpected command: $*" >&2
exit 1
"""
    )
    fake_docker.chmod(0o755)

    result = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps(
            [
                {
                    "Name": "/plane-migrator",
                    "HostConfig": {"RestartPolicy": {"Name": "on-failure"}},
                }
            ]
        ),
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
        },
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    statuses = json.loads(result.stdout)
    assert statuses == [
        {
            "requested_name": "plane-migrator",
            "full_name": "/plane-migrator",
            "exists": True,
            "restart_policy_name": "on-failure",
            "require_running": False,
            "running": False,
            "status": "exited",
            "exit_code": 0,
            "healthy": True,
        }
    ]


def test_docker_runtime_accepts_compose_managed_replacement_container_after_restart(tmp_path: Path) -> None:
    tasks = load_tasks()
    confirm_recovery = next(task for task in tasks if task["name"] == "Confirm pre-restart containers recovered after Docker restarts")
    script = confirm_recovery["ansible.builtin.command"]["argv"][2]
    script = script.replace(
        "{{ docker_runtime_nonpersistent_restart_policies | to_json }}",
        json.dumps(load_defaults()["docker_runtime_nonpersistent_restart_policies"]),
    )
    fake_docker = tmp_path / "docker"
    fake_docker.write_text(
        """#!/bin/sh
if [ "$1" = "inspect" ] && [ "$2" = "59540cf44274_nginx" ]; then
  echo 'Error: No such object: 59540cf44274_nginx' >&2
  exit 1
fi
if [ "$1" = "ps" ] && [ "$2" = "-aq" ]; then
  printf '%s\\n' replacement-nginx-id
  exit 0
fi
if [ "$1" = "inspect" ] && [ "$2" = "replacement-nginx-id" ]; then
  cat <<'JSON'
[{"Name":"/nginx","State":{"Running":true,"Status":"running","ExitCode":0}}]
JSON
  exit 0
fi
echo "unexpected command: $*" >&2
exit 1
"""
    )
    fake_docker.chmod(0o755)

    result = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps(
            [
                {
                    "Name": "/59540cf44274_nginx",
                    "HostConfig": {"RestartPolicy": {"Name": "always"}},
                    "Config": {
                        "Labels": {
                            "com.docker.compose.project": "59540cf44274",
                            "com.docker.compose.service": "nginx",
                        }
                    },
                }
            ]
        ),
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
        },
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    statuses = json.loads(result.stdout)
    assert statuses == [
        {
            "requested_name": "59540cf44274_nginx",
            "full_name": "/nginx",
            "exists": True,
            "restart_policy_name": "always",
            "require_running": True,
            "running": True,
            "status": "running",
            "exit_code": 0,
            "healthy": True,
        }
    ]


def test_docker_runtime_unseals_openbao_before_recovering_openbao_agent(tmp_path: Path) -> None:
    tasks = load_tasks()
    recover_containers = next(
        task for task in tasks if task["name"] == "Recover pre-restart containers that remained stopped after Docker restarts"
    )
    script = recover_containers["ansible.builtin.command"]["argv"][2]
    script = script.replace(
        "{{ docker_runtime_nonpersistent_restart_policies | to_json }}",
        json.dumps(load_defaults()["docker_runtime_nonpersistent_restart_policies"]),
    )
    script = script.replace("{{ docker_runtime_openbao_recovery_timeout_seconds | int }}", "5")
    script = script.replace("{{ docker_runtime_openbao_recovery_delay_seconds | int }}", "0")
    script = re.sub(
        r"OPENBAO_UNSEAL_KEYS = \{\{.*?\n\s*OPENBAO_RECOVERY_TIMEOUT_SECONDS =",
        'OPENBAO_UNSEAL_KEYS = ["key-1", "key-2", "key-3"]\nOPENBAO_RECOVERY_TIMEOUT_SECONDS =',
        script,
        flags=re.DOTALL,
    )

    class OpenBaoState:
        sealed = True
        unseal_attempts = 0

    class Handler(BaseHTTPRequestHandler):
        def _write_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/v1/sys/seal-status":
                self._write_json(200, {"sealed": OpenBaoState.sealed})
                return
            if self.path == "/v1/sys/health":
                if OpenBaoState.sealed:
                    self._write_json(503, {"sealed": True})
                    return
                self._write_json(200, {"sealed": False})
                return
            self._write_json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path == "/v1/sys/unseal":
                OpenBaoState.unseal_attempts += 1
                if OpenBaoState.unseal_attempts >= 2:
                    OpenBaoState.sealed = False
                self._write_json(200, {"sealed": OpenBaoState.sealed})
                return
            self._write_json(404, {"error": "not found"})

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    script = script.replace(
        'OPENBAO_HEALTH_URL = "http://127.0.0.1:8201/v1/sys/health"',
        f'OPENBAO_HEALTH_URL = "{base_url}/v1/sys/health"',
    )
    script = script.replace(
        'OPENBAO_SEAL_STATUS_URL = "http://127.0.0.1:8201/v1/sys/seal-status"',
        f'OPENBAO_SEAL_STATUS_URL = "{base_url}/v1/sys/seal-status"',
    )
    script = script.replace(
        'OPENBAO_UNSEAL_URL = "http://127.0.0.1:8201/v1/sys/unseal"',
        f'OPENBAO_UNSEAL_URL = "{base_url}/v1/sys/unseal"',
    )

    fake_docker = tmp_path / "docker"
    fake_docker.write_text(
        """#!/bin/sh
if [ "$1" = "compose" ]; then
  exit 0
fi
echo "unexpected command: $*" >&2
exit 1
"""
    )
    fake_docker.chmod(0o755)

    fake_iptables = tmp_path / "iptables"
    fake_iptables.write_text(
        """#!/bin/sh
if [ "$1" = "-t" ] && [ "$2" = "nat" ] && [ "$3" = "-S" ] && [ "$4" = "DOCKER" ]; then
  exit 0
fi
echo "unexpected iptables command: $*" >&2
exit 1
"""
    )
    fake_iptables.chmod(0o755)

    fake_systemctl = tmp_path / "systemctl"
    fake_systemctl.write_text(
        """#!/bin/sh
if [ "$1" = "is-active" ] && [ "$2" = "docker" ]; then
  echo active
  exit 0
fi
if [ "$1" = "reset-failed" ] && [ "$2" = "docker.service" ]; then
  exit 0
fi
if [ "$1" = "restart" ] && [ "$2" = "docker.service" ]; then
  exit 0
fi
echo "unexpected systemctl command: $*" >&2
exit 1
"""
    )
    fake_systemctl.chmod(0o755)

    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n")

    result = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps(
            [
                {
                    "Name": "/typesense-openbao-agent-1",
                    "Config": {
                        "Labels": {
                            "com.docker.compose.project.working_dir": str(tmp_path),
                            "com.docker.compose.project.config_files": str(compose_file),
                            "com.docker.compose.service": "openbao-agent",
                        }
                    },
                }
            ]
        ),
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
        },
        check=False,
    )

    server.shutdown()
    server.server_close()
    thread.join(timeout=2)

    assert result.returncode == 0, result.stderr or result.stdout
    assert OpenBaoState.unseal_attempts == 2
    assert OpenBaoState.sealed is False


def test_docker_runtime_retries_compose_recovery_long_enough_for_transient_nat_chain_errors(tmp_path: Path) -> None:
    tasks = load_tasks()
    recover_containers = next(
        task for task in tasks if task["name"] == "Recover pre-restart containers that remained stopped after Docker restarts"
    )
    script = recover_containers["ansible.builtin.command"]["argv"][2]
    script = script.replace(
        "{{ docker_runtime_nonpersistent_restart_policies | to_json }}",
        json.dumps(load_defaults()["docker_runtime_nonpersistent_restart_policies"]),
    )
    script = re.sub(
        r"OPENBAO_UNSEAL_KEYS = \{\{.*?\n\s*OPENBAO_RECOVERY_TIMEOUT_SECONDS =",
        'OPENBAO_UNSEAL_KEYS = []\nOPENBAO_RECOVERY_TIMEOUT_SECONDS =',
        script,
        flags=re.DOTALL,
    )
    script = script.replace("{{ docker_runtime_openbao_recovery_timeout_seconds | int }}", "5")
    script = script.replace("{{ docker_runtime_openbao_recovery_delay_seconds | int }}", "0")

    fake_docker = tmp_path / "docker"
    fake_docker.write_text(
        """#!/bin/sh
STATE_FILE="$TMPDIR/compose-attempts.txt"
ATTEMPTS=0
if [ -f "$STATE_FILE" ]; then
  ATTEMPTS="$(cat "$STATE_FILE")"
fi
if [ "$1" = "compose" ]; then
  ATTEMPTS=$((ATTEMPTS + 1))
  printf '%s' "$ATTEMPTS" > "$STATE_FILE"
  if [ "$ATTEMPTS" -lt 5 ]; then
    echo "driver failed programming external connectivity" >&2
    echo "No chain/target/match by that name" >&2
    exit 1
  fi
  exit 0
fi
echo "unexpected command: $*" >&2
exit 1
"""
    )
    fake_docker.chmod(0o755)

    fake_iptables = tmp_path / "iptables"
    fake_iptables.write_text(
        """#!/bin/sh
if [ "$1" = "-t" ] && [ "$2" = "nat" ] && [ "$3" = "-S" ] && [ "$4" = "DOCKER" ]; then
  exit 0
fi
echo "unexpected iptables command: $*" >&2
exit 1
"""
    )
    fake_iptables.chmod(0o755)

    fake_systemctl = tmp_path / "systemctl"
    fake_systemctl.write_text(
        """#!/bin/sh
if [ "$1" = "is-active" ] && [ "$2" = "docker" ]; then
  echo active
  exit 0
fi
if [ "$1" = "reset-failed" ] && [ "$2" = "docker.service" ]; then
  exit 0
fi
if [ "$1" = "restart" ] && [ "$2" = "docker.service" ]; then
  exit 0
fi
echo "unexpected systemctl command: $*" >&2
exit 1
"""
    )
    fake_systemctl.chmod(0o755)

    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n")

    result = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps(
            [
                {
                    "Name": "/test-service",
                    "Config": {
                        "Labels": {
                            "com.docker.compose.project.working_dir": str(tmp_path),
                            "com.docker.compose.project.config_files": str(compose_file),
                            "com.docker.compose.service": "test-service",
                        }
                    },
                }
            ]
        ),
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "TMPDIR": str(tmp_path),
        },
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    attempts = int((tmp_path / "compose-attempts.txt").read_text())
    assert attempts == 5


def test_docker_runtime_restarts_docker_when_daemon_is_not_active(tmp_path: Path) -> None:
    tasks = load_tasks()
    recover_containers = next(
        task for task in tasks if task["name"] == "Recover pre-restart containers that remained stopped after Docker restarts"
    )
    script = recover_containers["ansible.builtin.command"]["argv"][2]
    script = script.replace(
        "{{ docker_runtime_nonpersistent_restart_policies | to_json }}",
        json.dumps(load_defaults()["docker_runtime_nonpersistent_restart_policies"]),
    )
    script = re.sub(
        r"OPENBAO_UNSEAL_KEYS = \{\{.*?\n\s*OPENBAO_RECOVERY_TIMEOUT_SECONDS =",
        'OPENBAO_UNSEAL_KEYS = []\nOPENBAO_RECOVERY_TIMEOUT_SECONDS =',
        script,
        flags=re.DOTALL,
    )
    script = script.replace("{{ docker_runtime_openbao_recovery_timeout_seconds | int }}", "5")
    script = script.replace("{{ docker_runtime_openbao_recovery_delay_seconds | int }}", "0")

    fake_docker = tmp_path / "docker"
    fake_docker.write_text(
        """#!/bin/sh
if [ "$1" = "compose" ]; then
  printf '%s\n' "$*" >> "$TMPDIR/compose-commands.txt"
  exit 0
fi
echo "unexpected command: $*" >&2
exit 1
"""
    )
    fake_docker.chmod(0o755)

    fake_iptables = tmp_path / "iptables"
    fake_iptables.write_text(
        """#!/bin/sh
if [ "$1" = "-t" ] && [ "$2" = "nat" ] && [ "$3" = "-S" ] && [ "$4" = "DOCKER" ]; then
  if [ -f "$TMPDIR/docker-restarted.flag" ]; then
    exit 0
  fi
  exit 1
fi
echo "unexpected iptables command: $*" >&2
exit 1
"""
    )
    fake_iptables.chmod(0o755)

    fake_systemctl = tmp_path / "systemctl"
    fake_systemctl.write_text(
        """#!/bin/sh
if [ "$1" = "is-active" ] && [ "$2" = "docker" ]; then
  if [ -f "$TMPDIR/docker-restarted.flag" ]; then
    echo active
    exit 0
  fi
  echo deactivating
  exit 3
fi
if [ "$1" = "reset-failed" ] && [ "$2" = "docker.service" ]; then
  printf '%s\n' "$*" >> "$TMPDIR/systemctl-commands.txt"
  exit 0
fi
if [ "$1" = "restart" ] && [ "$2" = "docker.service" ]; then
  : > "$TMPDIR/docker-restarted.flag"
  printf '%s\n' "$*" >> "$TMPDIR/systemctl-commands.txt"
  exit 0
fi
echo "unexpected systemctl command: $*" >&2
exit 1
"""
    )
    fake_systemctl.chmod(0o755)

    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n")

    result = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps(
            [
                {
                    "Name": "/ntfy",
                    "Config": {
                        "Labels": {
                            "com.docker.compose.project.working_dir": str(tmp_path),
                            "com.docker.compose.project.config_files": str(compose_file),
                            "com.docker.compose.service": "ntfy",
                        }
                    },
                }
            ]
        ),
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "TMPDIR": str(tmp_path),
        },
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    systemctl_commands = (tmp_path / "systemctl-commands.txt").read_text()
    assert "reset-failed docker.service" in systemctl_commands
    assert "restart docker.service" in systemctl_commands
    compose_commands = (tmp_path / "compose-commands.txt").read_text()
    assert "--force-recreate ntfy" in compose_commands


def test_docker_runtime_recovery_includes_compose_dependencies(tmp_path: Path) -> None:
    tasks = load_tasks()
    recover_containers = next(
        task for task in tasks if task["name"] == "Recover pre-restart containers that remained stopped after Docker restarts"
    )
    script = recover_containers["ansible.builtin.command"]["argv"][2]
    script = script.replace(
        "{{ docker_runtime_nonpersistent_restart_policies | to_json }}",
        json.dumps(load_defaults()["docker_runtime_nonpersistent_restart_policies"]),
    )
    script = re.sub(
        r"OPENBAO_UNSEAL_KEYS = \{\{.*?\n\s*OPENBAO_RECOVERY_TIMEOUT_SECONDS =",
        'OPENBAO_UNSEAL_KEYS = []\nOPENBAO_RECOVERY_TIMEOUT_SECONDS =',
        script,
        flags=re.DOTALL,
    )
    script = script.replace("{{ docker_runtime_openbao_recovery_timeout_seconds | int }}", "5")
    script = script.replace("{{ docker_runtime_openbao_recovery_delay_seconds | int }}", "0")
    script = script.replace("wait_for_local_openbao()", "None")

    fake_docker = tmp_path / "docker"
    fake_docker.write_text(
        """#!/bin/sh
if [ "$1" = "compose" ]; then
  printf '%s\n' "$*" >> "$TMPDIR/compose-commands.txt"
  exit 0
fi
echo "unexpected command: $*" >&2
exit 1
"""
    )
    fake_docker.chmod(0o755)

    fake_iptables = tmp_path / "iptables"
    fake_iptables.write_text(
        """#!/bin/sh
if [ "$1" = "-t" ] && [ "$2" = "nat" ] && [ "$3" = "-S" ] && [ "$4" = "DOCKER" ]; then
  exit 0
fi
echo "unexpected iptables command: $*" >&2
exit 1
"""
    )
    fake_iptables.chmod(0o755)

    fake_systemctl = tmp_path / "systemctl"
    fake_systemctl.write_text(
        """#!/bin/sh
if [ "$1" = "is-active" ] && [ "$2" = "docker" ]; then
  echo active
  exit 0
fi
if [ "$1" = "reset-failed" ] && [ "$2" = "docker.service" ]; then
  exit 0
fi
if [ "$1" = "restart" ] && [ "$2" = "docker.service" ]; then
  exit 0
fi
echo "unexpected systemctl command: $*" >&2
exit 1
"""
    )
    fake_systemctl.chmod(0o755)

    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n")

    result = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps(
            [
                {
                    "Name": "/glitchtip",
                    "Config": {
                        "Labels": {
                            "com.docker.compose.project.working_dir": str(tmp_path),
                            "com.docker.compose.project.config_files": str(compose_file),
                            "com.docker.compose.service": "glitchtip",
                            "com.docker.compose.depends_on": "openbao-agent:service_healthy:false,valkey:service_healthy:false",
                        }
                    },
                }
            ]
        ),
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "TMPDIR": str(tmp_path),
        },
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    compose_commands = (tmp_path / "compose-commands.txt").read_text()
    assert "--force-recreate glitchtip openbao-agent valkey" in compose_commands


def test_common_docker_bridge_chains_warms_control_socket_before_failing_safe() -> None:
    tasks = load_common_docker_bridge_chains()
    task_names = {task["name"] for task in tasks}
    assert "Warm the Docker control socket before chain health checks" in task_names
    assert "Reset SSH connection before Docker bridge-chain recovery checks" in task_names
    assert "Wait for SSH before Docker bridge-chain recovery checks" in task_names
    assert "Wait briefly for Docker bridge chains to recover after daemon activation" in task_names
    assert "Restart Docker when required bridge chains are missing" not in task_names
    assert "Restart Docker when required bridge chains are still missing after the retry loop" not in task_names
    info_ready = next(task for task in tasks if task["name"] == "Warm the Docker control socket before chain health checks")
    wait_for_ssh = next(task for task in tasks if task["name"] == "Wait for SSH before Docker bridge-chain recovery checks")
    chain_wait = next(
        task for task in tasks if task["name"] == "Wait briefly for Docker bridge chains to recover after daemon activation"
    )
    nat_recheck = next(task for task in tasks if task["name"] == "Recheck Docker nat chain after health evaluation")
    forward_recheck = next(task for task in tasks if task["name"] == "Recheck Docker forward chain after health evaluation")
    nat_verify = next(task for task in tasks if task["name"] == "Verify Docker nat chain after retry loop")
    forward_verify = next(task for task in tasks if task["name"] == "Verify Docker forward chain after retry loop")
    nat_final = next(task for task in tasks if task["name"] == "Capture final Docker nat chain state after retry loop")
    forward_final = next(task for task in tasks if task["name"] == "Capture final Docker forward chain state after retry loop")
    nat_assert = next(task for task in tasks if task["name"] == "Assert Docker nat chain is present after health evaluation")
    forward_assert = next(
        task for task in tasks if task["name"] == "Assert Docker forward chain is present after health evaluation"
    )

    assert info_ready["ansible.builtin.command"]["argv"] == [
        "docker",
        "info",
        "--format",
        "{{ '{{.ServerVersion}}' }}",
    ]
    assert info_ready["retries"] == "{{ common_docker_bridge_chains_retries }}"
    assert info_ready["delay"] == "{{ common_docker_bridge_chains_delay }}"
    assert info_ready["until"] == "common_docker_bridge_chains_info_ready.rc == 0"
    assert wait_for_ssh["ansible.builtin.wait_for_connection"]["timeout"] == (
        "{{ ((common_docker_bridge_chains_retries | int) * (common_docker_bridge_chains_delay | int)) + 60 }}"
    )
    assert wait_for_ssh["ansible.builtin.wait_for_connection"]["connect_timeout"] == 5
    assert wait_for_ssh["ansible.builtin.wait_for_connection"]["sleep"] == (
        "{{ [common_docker_bridge_chains_delay | int, 1] | max }}"
    )
    assert "iptables -t nat -S DOCKER" in chain_wait["ansible.builtin.shell"]
    assert "iptables -t filter -S DOCKER-FORWARD" in chain_wait["ansible.builtin.shell"]
    assert "iptables -t filter -S DOCKER >/dev/null 2>&1" in chain_wait["ansible.builtin.shell"]
    assert "iptables -t filter -S FORWARD" in chain_wait["ansible.builtin.shell"]
    assert "sleep {{ common_docker_bridge_chains_delay }}" in chain_wait["ansible.builtin.shell"]
    assert chain_wait["failed_when"] is False
    assert "iptables -t filter -S FORWARD" in forward_recheck["ansible.builtin.shell"]
    assert nat_recheck["retries"] == "{{ common_docker_bridge_chains_retries }}"
    assert nat_recheck["delay"] == "{{ common_docker_bridge_chains_delay }}"
    assert nat_recheck["until"] == "common_docker_bridge_chains_nat_recheck.rc == 0"
    assert "iptables -t filter -S DOCKER-FORWARD" in forward_recheck["ansible.builtin.shell"]
    assert "iptables -t filter -S DOCKER >/dev/null 2>&1" in forward_recheck["ansible.builtin.shell"]
    assert "iptables -t filter -S FORWARD" in forward_recheck["ansible.builtin.shell"]
    assert forward_recheck["retries"] == "{{ common_docker_bridge_chains_retries }}"
    assert forward_recheck["delay"] == "{{ common_docker_bridge_chains_delay }}"
    assert forward_recheck["until"] == "common_docker_bridge_chains_forward_recheck.rc == 0"
    assert nat_verify["retries"] == "{{ common_docker_bridge_chains_retries }}"
    assert nat_verify["delay"] == "{{ common_docker_bridge_chains_delay }}"
    assert nat_verify["until"] == "common_docker_bridge_chains_nat_verify.rc == 0"
    assert "iptables -t filter -S DOCKER-FORWARD" in forward_verify["ansible.builtin.shell"]
    assert "iptables -t filter -S DOCKER >/dev/null 2>&1" in forward_verify["ansible.builtin.shell"]
    assert "iptables -t filter -S FORWARD" in forward_verify["ansible.builtin.shell"]
    assert forward_verify["retries"] == "{{ common_docker_bridge_chains_retries }}"
    assert forward_verify["delay"] == "{{ common_docker_bridge_chains_delay }}"
    assert forward_verify["until"] == "common_docker_bridge_chains_forward_verify.rc == 0"
    assert nat_final["ansible.builtin.set_fact"]["common_docker_bridge_chains_nat_final"] == (
        "{{ common_docker_bridge_chains_nat_verify }}"
    )
    assert forward_final["ansible.builtin.set_fact"]["common_docker_bridge_chains_forward_final"] == (
        "{{ common_docker_bridge_chains_forward_verify }}"
    )
    assert nat_assert["ansible.builtin.assert"]["that"] == ["common_docker_bridge_chains_nat_final.rc == 0"]
    assert forward_assert["ansible.builtin.assert"]["that"] == ["common_docker_bridge_chains_forward_final.rc == 0"]
    assert "equivalent Docker-managed FORWARD bridge rules" in forward_assert["ansible.builtin.assert"]["fail_msg"]
    assert "legacy filter DOCKER chain" in forward_assert["ansible.builtin.assert"]["fail_msg"]


def test_docker_runtime_patches_nftables_rule_block_once() -> None:
    tasks = load_tasks()
    daemon_stat = next(task for task in tasks if task["name"] == "Check whether the current Docker daemon config exists")
    daemon_slurp = next(task for task in tasks if task["name"] == "Read the current Docker daemon config")
    daemon_fact = next(task for task in tasks if task["name"] == "Record whether Docker currently has live-restore enabled")
    daemon_render = next(task for task in tasks if task["name"] == "Render Docker daemon configuration")
    build_rules = next(task for task in tasks if task["name"] == "Build the Docker bridge forward-compat rule block")
    patch_rules = next(task for task in tasks if task["name"] == "Patch nftables forward policy for Docker bridge egress")
    assert_rules = next(task for task in tasks if task["name"] == "Assert the Docker bridge forward-compat rule is present")
    live_rules = next(
        task for task in tasks if task["name"] == "Apply Docker bridge forward-compat rules live without reloading nftables"
    )

    assert "docker_runtime_container_forward_rule_lines" in build_rules["ansible.builtin.set_fact"]
    assert daemon_stat["ansible.builtin.stat"]["path"] == "/etc/docker/daemon.json"
    assert daemon_slurp["when"] == "docker_runtime_daemon_config_stat.stat.exists"
    assert "docker_runtime_previous_live_restore_enabled" in daemon_fact["ansible.builtin.set_fact"]
    assert daemon_render["register"] == "docker_runtime_daemon_config_render"
    assert "docker_runtime_container_forward_rule_lines" in build_rules["ansible.builtin.set_fact"]
    assert "docker_runtime_container_forward_rule_block" in build_rules["ansible.builtin.set_fact"]
    assert patch_rules["ansible.builtin.lineinfile"]["line"] == "    ip saddr {{ item }} accept"
    assert patch_rules["ansible.builtin.lineinfile"]["insertafter"] == (
        r"^\s*ct state (established,related|related,established) accept$"
    )
    assert patch_rules["loop"] == "{{ docker_runtime_container_forward_source_cidrs | reverse | list }}"
    assert assert_rules["loop"] == "{{ docker_runtime_container_forward_source_cidrs }}"
    assert live_rules["loop"] == "{{ docker_runtime_container_forward_source_cidrs }}"
    assert live_rules["ansible.builtin.command"]["argv"][:6] == ["nft", "add", "rule", "inet", "filter", "forward"]


def test_linux_guest_firewall_template_includes_all_docker_forward_compat_cidrs() -> None:
    template = FIREWALL_TEMPLATE.read_text()
    assert "docker_runtime_container_forward_source_cidrs" in template
    assert "linux_guest_firewall_container_forward_source_cidrs" in template


def test_docker_runtime_pins_public_edge_hostnames_and_address_pools() -> None:
    tasks = load_tasks()
    pin_hosts = next(task for task in tasks if task["name"] == "Pin public edge hostnames to the internal edge for Docker guests")

    config = pin_hosts["ansible.builtin.blockinfile"]
    assert config["path"] == "/etc/hosts"
    assert config["marker"] == "# {mark} ANSIBLE MANAGED BLOCK: lv3 docker public edge aliases"
    assert "{% for alias in docker_runtime_public_edge_host_aliases | default([]) if alias | length > 0 %}" in config["block"]
    assert "{{ docker_runtime_public_edge_ipv4 }} {{ alias }}" in config["block"]
    assert pin_hosts["when"] == [
        "docker_runtime_public_edge_ipv4 | default('') | length > 0",
        "docker_runtime_public_edge_host_aliases | default([]) | reject('equalto', '') | list | length > 0",
    ]


def test_docker_runtime_defaults_pin_governed_resolvers_and_registry_mirror() -> None:
    defaults = load_defaults()
    daemon_config = defaults["docker_runtime_daemon_config"]
    controller_repo_root = defaults["docker_runtime_controller_repo_root"]

    assert defaults["docker_runtime_registry_mirrors"] == ["https://mirror.gcr.io"]
    assert "ansible.builtin.pipe" in controller_repo_root
    assert "git -C " in controller_repo_root
    assert "rev-parse --show-toplevel" in controller_repo_root
    assert defaults["docker_runtime_publication_assurance_helper_local_path"] == (
        "{{ docker_runtime_controller_repo_root }}/scripts/docker_publication_assurance.py"
    )
    assert defaults["docker_runtime_repo_root"] == "{{ inventory_dir | dirname }}"
    assert (
        defaults["docker_runtime_publication_assurance_script_src"]
        == "{{ docker_runtime_repo_root }}/scripts/docker_publication_assurance.py"
    )
    assert defaults["docker_runtime_publication_assurance_script_path"] == "/usr/local/bin/lv3-docker-publication-assurance"
    assert defaults["docker_runtime_publication_assurance_helper_source"] == (
        "{{ inventory_dir ~ '/../scripts/docker_publication_assurance.py' }}"
    )
    assert defaults["docker_runtime_insecure_registries"] == []
    assert daemon_config["live-restore"] is False
    assert daemon_config["dns"] == ["1.1.1.1", "8.8.8.8"]
    assert daemon_config["registry-mirrors"] == "{{ docker_runtime_registry_mirrors }}"
    assert daemon_config["insecure-registries"] == "{{ docker_runtime_insecure_registries }}"
    assert daemon_config["default-address-pools"] == [
        {"base": "172.16.0.0/12", "size": 24},
        {"base": "192.168.0.0/16", "size": 24},
        {"base": "10.200.0.0/16", "size": 24},
    ]


def test_docker_runtime_installs_publication_assurance_helper_before_chain_checks() -> None:
    tasks = load_tasks()
    install_task = next(task for task in tasks if task["name"] == "Install the Docker publication assurance helper")
    nftables_check_task = next(task for task in tasks if task["name"] == "Check whether nftables config exists")

    assert install_task["ansible.builtin.copy"]["dest"] == "{{ docker_runtime_publication_assurance_script_path }}"
    assert install_task["ansible.builtin.copy"]["content"] == (
        "{{ lookup('ansible.builtin.file', docker_runtime_publication_assurance_script_src) }}"
    )
    assert tasks.index(install_task) < tasks.index(nftables_check_task)


def test_docker_runtime_waits_out_background_apt_maintenance() -> None:
    tasks = load_tasks()
    defaults = load_defaults()
    prereq_task = next(task for task in tasks if task["name"] == "Install Docker repository prerequisites")
    remove_conflicts_task = next(task for task in tasks if task["name"] == "Remove conflicting Docker packages")
    install_runtime_task = next(task for task in tasks if task["name"] == "Install Docker runtime packages")

    prereq_apt = prereq_task["ansible.builtin.apt"]
    remove_conflicts_apt = remove_conflicts_task["ansible.builtin.apt"]
    install_runtime_apt = install_runtime_task["ansible.builtin.apt"]

    assert defaults["docker_runtime_apt_lock_timeout"] == 1200

    assert prereq_apt["name"] == "{{ docker_runtime_missing_prereq_packages }}"
    assert prereq_apt["state"] == "present"
    assert prereq_apt["update_cache"] is True
    assert prereq_apt["cache_valid_time"] == 3600
    assert prereq_apt["lock_timeout"] == "{{ docker_runtime_apt_lock_timeout }}"
    assert prereq_apt["force_apt_get"] is True

    assert remove_conflicts_apt["name"] == "{{ docker_runtime_installed_conflicting_packages }}"
    assert remove_conflicts_apt["state"] == "absent"
    assert remove_conflicts_apt["lock_timeout"] == "{{ docker_runtime_apt_lock_timeout }}"

    assert install_runtime_apt["name"] == "{{ docker_runtime_missing_engine_packages }}"
    assert install_runtime_apt["state"] == "present"
    assert install_runtime_apt["update_cache"] is True
    assert install_runtime_apt["cache_valid_time"] == 3600
    assert install_runtime_apt["lock_timeout"] == "{{ docker_runtime_apt_lock_timeout }}"
    assert install_runtime_apt["force_apt_get"] is True


def test_docker_runtime_verify_checks_publication_assurance_helper_is_executable() -> None:
    verify_tasks = load_verify()
    verify_task = next(
        task for task in verify_tasks if task["name"] == "Verify the Docker publication assurance helper is installed"
    )

    assert verify_task["ansible.builtin.command"]["argv"] == [
        "test",
        "-x",
        "{{ docker_runtime_publication_assurance_script_path }}",
    ]
    assert verify_task["changed_when"] is False
