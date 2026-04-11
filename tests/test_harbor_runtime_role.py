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
    oidc_readiness_block = task_by_name["Verify the Harbor admin configuration API is reachable before OIDC bootstrap"]
    config_probe_task = oidc_readiness_block["block"][0]
    rescue_tasks = {task["name"]: task for task in oidc_readiness_block["rescue"]}
    recovery_down_task = rescue_tasks[
        "Force one Harbor recycle when the published admin configuration API is unavailable"
    ]
    recovery_container_cleanup_task = rescue_tasks["Remove stale Harbor containers after the OIDC readiness recycle"]
    recovery_network_cleanup_task = rescue_tasks["Remove stale Harbor networks after the OIDC readiness recycle"]
    recovery_up_task = rescue_tasks[
        "Force one Harbor recreate when the published admin configuration API is unavailable"
    ]
    recovery_port_probe_task = rescue_tasks["Read the Harbor published port bindings after the OIDC readiness recycle"]
    recovery_assert_task = rescue_tasks[
        "Assert the OIDC readiness recycle restored Harbor compose membership and published port bindings"
    ]
    recovery_ping_task = rescue_tasks["Wait for Harbor ping locally after the OIDC readiness recycle"]
    re_probe_task = rescue_tasks["Re-probe the Harbor admin configuration API after the OIDC readiness recycle"]
    oidc_task = task_by_name["Configure Harbor OIDC defaults"]

    assert readiness_task["retries"] == 24
    assert readiness_task["delay"] == 5
    assert readiness_task["until"] == "harbor_keycloak_admin_ready.status == 200"
    assert token_task["retries"] == 12
    assert token_task["delay"] == 5
    assert token_task["until"] == "harbor_keycloak_admin_token_response.status == 200"
    assert config_probe_task["retries"] == 12
    assert config_probe_task["delay"] == 5
    assert config_probe_task["until"] == "harbor_config_query_before_oidc.status == 200"
    assert "Removing" in recovery_down_task["changed_when"]
    assert "ensure_docker_socket()" in recovery_container_cleanup_task["ansible.builtin.shell"]
    assert "docker network ls -q" in recovery_network_cleanup_task["ansible.builtin.shell"]
    assert recovery_up_task["retries"] == 6
    assert recovery_up_task["delay"] == 10
    assert recovery_up_task["until"] == "harbor_compose_oidc_recovery_up.rc == 0"
    assert ".NetworkSettings.Ports" in recovery_port_probe_task["ansible.builtin.command"]["argv"][-1]
    assert (
        "harbor_oidc_recovery_registry_port_binding_present | bool"
        in recovery_assert_task["ansible.builtin.assert"]["that"]
    )
    assert recovery_ping_task["retries"] == 30
    assert recovery_ping_task["delay"] == 10
    assert recovery_ping_task["until"] == "harbor_ping_after_oidc_recovery.status == 200"
    assert re_probe_task["retries"] == 24
    assert re_probe_task["delay"] == 5
    assert re_probe_task["until"] == "harbor_config_query_before_oidc.status == 200"
    assert oidc_task["retries"] == 24
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
    stale_cleanup_script = task_by_name["Remove stale Harbor containers after the compose reset"][
        "ansible.builtin.shell"
    ]

    assert (
        reset_task["when"]
        == "(harbor_compose_assets_changed | bool) or not (harbor_runtime_healthy_before_reconcile | bool)"
    )
    assert recycle_task["when"] == "harbor_compose_needs_recovery | bool"
    assert recreate_task["when"] == "harbor_compose_needs_recovery | bool"
    assert "ensure_docker_socket()" in stale_cleanup_script
    assert "docker info >/dev/null 2>&1" in stale_cleanup_script
    assert "systemctl restart docker" in stale_cleanup_script
    assert (
        ".NetworkSettings.Ports"
        in task_by_name["Read the Harbor published port bindings after reconciliation"]["ansible.builtin.command"][
            "argv"
        ][-1]
    )
    assert (
        "harbor_proxy_port_bindings_raw.stdout"
        in port_binding_state_task["ansible.builtin.set_fact"]["harbor_proxy_port_bindings"]
    )
    assert (
        "selectattr('HostPort', 'equalto', harbor_http_port | string)"
        in port_binding_task["ansible.builtin.set_fact"]["harbor_registry_port_binding_present"]
    )
    assert "or not (harbor_registry_port_binding_present | bool)" in recovery_fact


def test_role_only_runs_harbor_prepare_when_compose_assets_need_regeneration() -> None:
    tasks = load_yaml(ROLE_TASKS)
    task_by_name = {task["name"]: task for task in tasks}

    compose_stat_task = task_by_name["Check whether the Harbor generated compose file already exists"]
    prepare_needed_task = task_by_name["Record whether Harbor prepare needs to regenerate compose assets"]
    prepare_task = task_by_name["Prepare Harbor compose assets"]
    compose_assets_changed_task = task_by_name["Record whether Harbor compose assets changed"]

    prepare_needed_fact = prepare_needed_task["ansible.builtin.set_fact"]["harbor_prepare_needed"]
    compose_assets_changed_fact = compose_assets_changed_task["ansible.builtin.set_fact"][
        "harbor_compose_assets_changed"
    ]

    assert compose_stat_task["ansible.builtin.stat"]["path"] == "{{ harbor_generated_compose_file }}"
    assert "harbor_installer_download.changed" in prepare_needed_fact
    assert "harbor_installer_unarchive.changed" in prepare_needed_fact
    assert "harbor_config_template.changed" in prepare_needed_fact
    assert "not harbor_generated_compose_file_stat.stat.exists" in prepare_needed_fact
    assert prepare_task["ansible.builtin.command"]["argv"] == (
        "{{ ['./prepare'] + (['--with-trivy'] if harbor_prepare_with_trivy else []) }}"
    )
    assert prepare_task["when"] == "harbor_prepare_needed | bool"
    assert prepare_task["changed_when"] == "harbor_prepare_needed | bool"
    assert "or harbor_prepare_needed | bool" in compose_assets_changed_fact


def test_role_recovers_retention_policy_id_from_create_location_and_persists_metadata() -> None:
    tasks = load_yaml(ROLE_TASKS)
    task_by_name = {task["name"]: task for task in tasks}

    create_task = task_by_name["Create the check-runner Harbor retention policy when missing"]
    created_fact_task = task_by_name["Record the check-runner Harbor retention policy ID advertised after creation"]
    retention_id_task = task_by_name["Record the check-runner Harbor retention policy ID"]
    sync_task = task_by_name[
        "Persist the check-runner Harbor retention policy ID in project metadata when Harbor omits it"
    ]
    synced_query_task = task_by_name[
        "Re-query the check-runner Harbor project metadata after retention ID synchronization"
    ]
    synced_assert_task = task_by_name[
        "Assert Harbor persisted the check-runner retention policy ID for future reconciliations"
    ]

    assert create_task["register"] == "harbor_check_runner_retention_create"
    assert create_task["when"] == "harbor_check_runner_retention_id_before == 0"

    created_facts = created_fact_task["ansible.builtin.set_fact"]
    assert (
        "harbor_check_runner_retention_create.location"
        in created_facts["harbor_check_runner_retention_create_location"]
    )
    assert "regex_findall('[0-9]+$')" in created_facts["harbor_check_runner_retention_id_created"]
    assert created_fact_task["when"] == "harbor_check_runner_retention_id_before == 0"

    retention_id_fact = retention_id_task["ansible.builtin.set_fact"]["harbor_check_runner_retention_id"]
    assert "after_id" in retention_id_fact
    assert "before_id" in retention_id_fact
    assert "created_id" in retention_id_fact

    assert sync_task["ansible.builtin.uri"]["method"] == "POST"
    assert sync_task["ansible.builtin.uri"]["body"]["retention_id"] == "{{ harbor_check_runner_retention_id | string }}"
    assert sync_task["when"] == [
        "harbor_check_runner_retention_id | int > 0",
        "harbor_check_runner_project_metadata_after.json.retention_id | default('0') | int == 0",
    ]

    assert synced_query_task["register"] == "harbor_check_runner_project_metadata_synced"
    assert synced_query_task["when"] == [
        "harbor_check_runner_retention_id | int > 0",
        "harbor_check_runner_project_metadata_after.json.retention_id | default('0') | int == 0",
    ]
    assert (
        synced_assert_task["ansible.builtin.assert"]["that"][0]
        == "harbor_check_runner_project_metadata_synced.json.retention_id | default('0') | int == harbor_check_runner_retention_id | int"
    )


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
    runtime_control_rules = host_vars["network_policy"]["guests"]["runtime-control-lv3"]["allowed_inbound"]
    harbor_rule = next(
        rule for rule in runtime_control_rules if rule["source"] == "nginx-lv3" and 8095 in rule["ports"]
    )

    assert "edge access" in harbor_rule["description"].lower()
    assert "harbor" in harbor_rule["description"].lower()
