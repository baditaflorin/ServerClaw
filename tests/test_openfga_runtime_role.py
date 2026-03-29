from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "openfga_runtime"
    / "defaults"
    / "main.yml"
)
TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "openfga_runtime"
    / "tasks"
    / "main.yml"
)
VERIFY_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "openfga_runtime"
    / "tasks"
    / "verify.yml"
)
COMPOSE_TEMPLATE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "openfga_runtime"
    / "templates"
    / "docker-compose.yml.j2"
)
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "openfga.yml"


def load_tasks() -> list[dict]:
    return yaml.safe_load(TASKS_PATH.read_text(encoding="utf-8"))


def test_openfga_runtime_defaults_use_private_controller_url() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert defaults["openfga_image"] == "{{ container_image_catalog.images.openfga_runtime.ref }}"
    assert "| urlencode" in defaults["openfga_datastore_uri"]
    assert defaults["openfga_controller_url"].startswith("http://{{ hostvars['proxmox_florin'].management_tailscale_ipv4 }}")
    assert "openfga_host_proxy_port" in defaults["openfga_controller_url"]
    assert defaults["openfga_preshared_key_local_file"].endswith("/.local/openfga/preshared-key.txt")


def test_openfga_runtime_bootstraps_openbao_env_and_migrations() -> None:
    tasks = load_tasks()

    secret_payload_task = next(task for task in tasks if task.get("name") == "Record the OpenFGA runtime secrets")
    openbao_helper = next(task for task in tasks if task.get("name") == "Prepare OpenBao agent runtime secret injection for OpenFGA")
    openbao_agent_up_task = next(task for task in tasks if task.get("name") == "Start the OpenFGA OpenBao agent")
    runtime_env_wait_task = next(task for task in tasks if task.get("name") == "Wait for the OpenFGA runtime env file")
    migrate_task = next(task for task in tasks if task.get("name") == "Run OpenFGA database migrations")
    nat_chain_task = next(
        task
        for task in tasks
        if task.get("name") == "Check whether the Docker nat chain exists before recreating OpenFGA published ports"
    )
    nat_chain_recheck_task = next(
        task for task in tasks if task.get("name") == "Recheck the Docker nat chain before OpenFGA startup"
    )
    docker_info_task = next(task for task in tasks if task.get("name") == "Wait for the Docker daemon to answer after networking recovery")
    port_probe_task = next(task for task in tasks if task.get("name") == "Check whether the OpenFGA HTTP port is already published locally")
    health_probe_task = next(
        task for task in tasks if task.get("name") == "Check whether the current OpenFGA health endpoint is healthy before startup"
    )
    force_recreate_task = next(
        task for task in tasks if task.get("name") == "Force-recreate the OpenFGA runtime stack after Docker networking recovery"
    )
    up_task = next(task for task in tasks if task.get("name") == "Converge the OpenFGA runtime stack")

    runtime_secret_payload = secret_payload_task["ansible.builtin.set_fact"]["openfga_runtime_secret_payload"]
    assert "| urlencode" in runtime_secret_payload["OPENFGA_DATASTORE_URI"]
    assert runtime_secret_payload["OPENFGA_DATASTORE_ENGINE"] == "postgres"
    assert runtime_secret_payload["OPENFGA_AUTHN_METHOD"] == "preshared"
    assert runtime_secret_payload["OPENFGA_AUTHN_PRESHARED_KEYS"] == (
        "{{ lookup('ansible.builtin.file', openfga_preshared_key_local_file) | trim }}"
    )
    assert runtime_secret_payload["OPENFGA_PLAYGROUND_ENABLED"] == "false"
    assert openbao_helper["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert openbao_helper["ansible.builtin.include_role"]["tasks_from"] == "openbao_compose_env"
    assert openbao_agent_up_task["ansible.builtin.command"]["argv"][-3:] == ["up", "-d", "openbao-agent"]
    assert runtime_env_wait_task["ansible.builtin.shell"].startswith("set -euo pipefail")
    assert 'test -s "{{ openfga_env_file }}"' in runtime_env_wait_task["ansible.builtin.shell"]
    assert 'grep -Fqx "OPENFGA_HTTP_ADDR={{ openfga_http_addr }}" "{{ openfga_env_file }}"' in (
        runtime_env_wait_task["ansible.builtin.shell"]
    )
    assert 'grep -Fqx "OPENFGA_GRPC_ADDR={{ openfga_grpc_addr }}" "{{ openfga_env_file }}"' in (
        runtime_env_wait_task["ansible.builtin.shell"]
    )
    assert runtime_env_wait_task["until"] == "openfga_runtime_env_contract.rc == 0"
    assert migrate_task["ansible.builtin.command"]["argv"][:5] == [
        "docker",
        "run",
        "--rm",
        "--network",
        "host",
    ]
    assert migrate_task["ansible.builtin.command"]["argv"][5] == "{{ openfga_image }}"
    assert migrate_task["ansible.builtin.command"]["argv"][-4:] == [
        "--datastore-engine",
        "postgres",
        "--datastore-uri",
        "{{ openfga_datastore_uri }}",
    ]
    assert nat_chain_task["ansible.builtin.command"]["argv"] == ["iptables", "-t", "nat", "-S", "DOCKER"]
    assert nat_chain_recheck_task["retries"] == 10
    assert nat_chain_recheck_task["delay"] == 2
    assert nat_chain_recheck_task["until"] == "openfga_docker_nat_chain_recheck.rc == 0"
    assert docker_info_task["ansible.builtin.command"]["argv"] == [
        "docker",
        "info",
        "--format",
        '{{ "{{.ServerVersion}}" }}',
    ]
    assert port_probe_task["ansible.builtin.wait_for"]["port"] == "{{ openfga_internal_http_port }}"
    assert health_probe_task["ansible.builtin.uri"]["url"] == "{{ openfga_local_url }}/healthz"
    assert force_recreate_task["ansible.builtin.command"]["argv"][-1] == "--force-recreate"
    assert force_recreate_task["retries"] == 3
    assert force_recreate_task["delay"] == 5
    assert force_recreate_task["until"] == "openfga_up.rc == 0"
    assert up_task["ansible.builtin.command"]["argv"][-2:] == ["-d", "--remove-orphans"]
    assert up_task["when"] == "not openfga_force_recreate"


def test_openfga_verify_task_checks_health_and_authenticated_api() -> None:
    tasks = yaml.safe_load(VERIFY_PATH.read_text(encoding="utf-8"))

    health_task = next(task for task in tasks if task.get("name") == "Verify OpenFGA responds on the local health endpoint")
    api_task = next(task for task in tasks if task.get("name") == "Verify the OpenFGA API enforces the repo-managed preshared key")
    assert_task = next(task for task in tasks if task.get("name") == "Assert OpenFGA health and authenticated access are working")

    assert health_task["ansible.builtin.uri"]["url"] == "{{ openfga_local_url }}/healthz"
    assert api_task["ansible.builtin.uri"]["headers"]["Authorization"] == "Bearer {{ openfga_preshared_key }}"
    assert "openfga_verify_health.status == 200" in assert_task["ansible.builtin.assert"]["that"]
    assert any("SERVING" in clause for clause in assert_task["ansible.builtin.assert"]["that"])


def test_openfga_compose_template_uses_openbao_agent_and_runtime_env() -> None:
    template = COMPOSE_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "  openbao-agent:" in template
    assert "    env_file:" in template
    assert "      - {{ openfga_env_file }}" in template
    assert "      - run" in template
    assert "--authn-method=preshared" not in template


def test_openfga_playbook_bootstraps_serverclaw_authz_from_localhost() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text(encoding="utf-8"))

    bootstrap_play = next(play for play in plays if play["name"] == "Bootstrap the ServerClaw delegated authorization graph from the controller")
    task = bootstrap_play["tasks"][0]

    assert task["name"] == "Bootstrap the ServerClaw authorization store, model, and tuples"
    assert task["ansible.builtin.command"]["argv"][0] == "python3"
    assert task["ansible.builtin.command"]["argv"][1] == "{{ openfga_bootstrap_script }}"
    assert "--openfga-preshared-key-file" in task["ansible.builtin.command"]["argv"]
    assert task["retries"] == 5
    assert task["delay"] == 3
    assert task["until"] == (
        "openfga_bootstrap.rc == 0 and (openfga_bootstrap.stdout | length > 0) and "
        "((openfga_bootstrap.stdout | from_json).verification_passed)"
    )
    assert task["changed_when"] == (
        "openfga_bootstrap.rc == 0 and (openfga_bootstrap.stdout | length > 0) and "
        "((openfga_bootstrap.stdout | from_json).changed)"
    )
    assert task["failed_when"] == (
        "openfga_bootstrap.rc != 0 or (openfga_bootstrap.stdout | length == 0) or "
        "(not (openfga_bootstrap.stdout | from_json).verification_passed)"
    )
    assert bootstrap_play["vars"]["openfga_bootstrap_keycloak_host"] == (
        "{{ 'docker-runtime-staging-lv3' if (env | default('production')) == 'staging' else 'docker-runtime-lv3' }}"
    )
    assert bootstrap_play["vars"]["openfga_bootstrap_keycloak_url"] == (
        "http://{{ hostvars[openfga_bootstrap_keycloak_host].ansible_host }}:8091"
    )
