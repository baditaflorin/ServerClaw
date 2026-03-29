from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "harbor_runtime"
    / "tasks"
    / "main.yml"
)
VERIFY_TASKS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "harbor_runtime"
    / "tasks"
    / "verify.yml"
)
HOST_VARS = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text())


def test_role_tracks_robot_reconcile_state_before_refreshing_secret() -> None:
    tasks = load_yaml(ROLE_TASKS)
    task_names = [task["name"] for task in tasks]

    assert "Record whether the check-runner Harbor robot account needs reconciliation" in task_names
    assert "Refresh the check-runner Harbor robot secret when local state is missing" in task_names
    assert "Read the desired Harbor registry credential password" in task_names
    assert "Record whether Harbor registry credential containers need recreation" in task_names
    assert "Record whether the Harbor admin password needs reconciliation" in task_names
    assert "Reset the Harbor admin password seed in the Harbor database when credentials drift" in task_names


def test_role_waits_for_keycloak_before_bootstrap_token_request() -> None:
    tasks = load_yaml(ROLE_TASKS)
    task_by_name = {task["name"]: task for task in tasks}

    readiness_task = task_by_name["Wait for the local Keycloak admin endpoint to recover after Docker reconciliation"]
    token_task = task_by_name["Request a Keycloak admin token for Harbor bootstrap"]
    oidc_task = task_by_name["Configure Harbor OIDC defaults"]

    assert readiness_task["retries"] == 24
    assert readiness_task["delay"] == 5
    assert readiness_task["until"] == "harbor_keycloak_admin_ready.status == 200"
    assert token_task["retries"] == 12
    assert token_task["delay"] == 5
    assert token_task["until"] == "harbor_keycloak_admin_token_response.status == 200"
    assert oidc_task["retries"] == 12
    assert oidc_task["delay"] == 5
    assert oidc_task["until"] == "harbor_oidc_configuration.status in [200, 201]"


def test_role_gates_network_recovery_on_boolean_fact() -> None:
    tasks = load_yaml(ROLE_TASKS)
    task_by_name = {task["name"]: task for task in tasks}

    reset_task = task_by_name["Reset the Harbor compose stack before a controlled reapply"]
    port_binding_state_task = task_by_name["Record the Harbor published port binding state"]
    port_binding_task = task_by_name["Record whether Harbor's published registry port binding is present"]
    recycle_task = task_by_name["Force one Harbor recycle when compose network membership is incomplete"]
    recreate_task = task_by_name["Force one Harbor recreate when compose network membership is incomplete"]
    recovery_fact = task_by_name["Record whether Harbor needs one forced network recovery recycle"][
        "ansible.builtin.set_fact"
    ]["harbor_compose_needs_recovery"]

    assert reset_task["when"] == "(harbor_compose_assets_changed | bool) or not (harbor_runtime_healthy_before_reconcile | bool)"
    assert recycle_task["when"] == "harbor_compose_needs_recovery | bool"
    assert recreate_task["when"] == "harbor_compose_needs_recovery | bool"
    assert "systemctl restart docker" in task_by_name["Remove stale Harbor containers after the compose reset"]["ansible.builtin.shell"]
    assert ".NetworkSettings.Ports" in task_by_name["Read the Harbor published port bindings after reconciliation"][
        "ansible.builtin.command"
    ]["argv"][-1]
    assert "harbor_proxy_port_bindings_raw.stdout" in port_binding_state_task["ansible.builtin.set_fact"][
        "harbor_proxy_port_bindings"
    ]
    assert "selectattr('HostPort', 'equalto', harbor_http_port | string)" in port_binding_task["ansible.builtin.set_fact"][
        "harbor_registry_port_binding_present"
    ]
    assert "or not (harbor_registry_port_binding_present | bool)" in recovery_fact


def test_verify_accepts_running_services_after_ping() -> None:
    tasks = load_yaml(VERIFY_TASKS)
    task_by_name = {task["name"]: task for task in tasks}

    verify_task = task_by_name["Assert Harbor runtime services include the expected core components"]
    verify_running_task = task_by_name["Verify Harbor core containers are running"]
    verify_checks = verify_task["ansible.builtin.assert"]["that"]

    assert "'harbor-core running ' in harbor_verify_services.stdout" in verify_checks
    assert "'nginx running ' in harbor_verify_services.stdout" in verify_checks
    assert "running\\ starting)" in verify_running_task["ansible.builtin.shell"]
    assert verify_task["ansible.builtin.assert"]["fail_msg"] == (
        "Harbor answered the ping endpoint but one or more core services are not running."
    )


def test_host_network_policy_allows_nginx_edge_access_to_harbor() -> None:
    host_vars = load_yaml(HOST_VARS)
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime-lv3"]["allowed_inbound"]
    harbor_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "nginx-lv3" and 8095 in rule["ports"])

    assert harbor_rule["description"].lower().startswith("edge access")
