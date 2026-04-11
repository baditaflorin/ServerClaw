from pathlib import Path

import generate_platform_vars
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "openbao_runtime"
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
    / "openbao_runtime"
    / "tasks"
    / "main.yml"
)
SEEDED_SECRET_TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "openbao_runtime"
    / "tasks"
    / "seeded_secrets_and_verification.yml"
)
ENSURE_UNSEALED_TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "openbao_runtime"
    / "tasks"
    / "ensure_unsealed.yml"
)
UNSEAL_KEY_TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "openbao_runtime"
    / "tasks"
    / "unseal_key.yml"
)
OPENBAO_POSTGRES_BACKEND_TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "openbao_postgres_backend"
    / "tasks"
    / "main.yml"
)
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "openbao.yml"
PLAYBOOK_REFRESH_APPROLE_TASKS_PATH = REPO_ROOT / "playbooks" / "tasks" / "openbao-refresh-approle-artifact.yml"
PLAYBOOK_SEED_ROTATION_METADATA_TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "openbao_runtime"
    / "tasks"
    / "seed_rotation_metadata.yml"
)
GROUP_VARS_PATH = REPO_ROOT / "inventory" / "group_vars" / "all.yml"


def load_openbao_runtime_tasks() -> list[dict]:
    raw_tasks = yaml.safe_load(TASKS_PATH.read_text())
    flattened: list[dict] = []

    def visit(task_list: list[dict]) -> None:
        for task in task_list:
            flattened.append(task)
            for nested_key in ("block", "rescue", "always"):
                nested_tasks = task.get(nested_key)
                if nested_tasks:
                    visit(nested_tasks)

    visit(raw_tasks)
    return flattened


def read_openbao_runtime_tasks_text() -> str:
    return TASKS_PATH.read_text(encoding="utf-8") + "\n" + SEEDED_SECRET_TASKS_PATH.read_text(encoding="utf-8")


def load_seeded_secret_tasks() -> list[dict]:
    return yaml.safe_load(SEEDED_SECRET_TASKS_PATH.read_text(encoding="utf-8"))


def test_openbao_runtime_defaults_use_postgres_primary_address() -> None:
    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")

    assert "openbao_postgres_host:" in defaults
    assert "openbao_controller_url | urlsplit('hostname')" in defaults
    assert "postgres_ha.initial_primary" in defaults
    assert "ansible_host" in defaults
    assert "@{{ openbao_postgres_host }}:5432/postgres?sslmode=disable" in defaults
    assert "creation_statements: !unsafe |-" in defaults
    assert "CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}';" in defaults
    assert 'GRANT lv3_openbao_connect_all TO "{{name}}";' in defaults
    assert 'GRANT pg_read_all_data TO "{{name}}";' in defaults
    assert 'GRANT pg_use_reserved_connections TO "{{name}}";' in defaults
    assert "revocation_statements: !unsafe |-" in defaults
    assert 'DROP ROLE IF EXISTS "{{name}}";' in defaults
    assert "{{ name }}" not in defaults
    assert "{{ password }}" not in defaults
    assert "{{ expiration }}" not in defaults
    assert "openbao_http_extra_bind_addresses: []" in defaults
    assert 'openbao_atlas_approle_local_file: "{{ openbao_local_artifact_dir }}/atlas-approle.json"' in defaults
    assert 'path "database/creds/postgres-atlas-readonly"' in (
        REPO_ROOT
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "openbao_runtime"
        / "templates"
        / "policy-lv3-agent-atlas.hcl.j2"
    ).read_text(encoding="utf-8")
    assert "  - name: postgres-atlas-readonly\n" in defaults
    assert "  - postgres-atlas-readonly" in defaults


def test_generated_platform_vars_pin_openbao_to_postgres_primary_ip() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    host_vars = generate_platform_vars.load_yaml(generate_platform_vars.HOST_VARS_PATH)
    primary_inventory_host = host_vars["postgres_ha"]["initial_primary"]
    primary_guest = next(guest for guest in host_vars["proxmox_guests"] if guest["name"] == primary_inventory_host)

    assert platform_vars["openbao_postgres_host"] == primary_guest["ipv4"]
    assert platform_vars["platform_postgres_host"] == "database.lv3.org"


def test_guest_side_postgres_clients_use_the_primary_guest_address() -> None:
    mattermost_defaults = (
        REPO_ROOT
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "mattermost_runtime"
        / "defaults"
        / "main.yml"
    ).read_text(encoding="utf-8")
    netbox_defaults = (
        REPO_ROOT
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "netbox_runtime"
        / "defaults"
        / "main.yml"
    ).read_text(encoding="utf-8")

    expected = "{{ hostvars[hostvars['proxmox_florin'].postgres_ha.initial_primary].ansible_host }}"

    assert f'mattermost_database_host: "{expected}"' in mattermost_defaults
    assert f'netbox_database_host: "{expected}"' in netbox_defaults


def test_openbao_rotation_catalog_is_loaded_before_derived_facts() -> None:
    tasks = read_openbao_runtime_tasks_text()

    assert "- name: Load the rotatable secret catalog and controller secret manifest" in tasks
    assert "- name: Derive OpenBao secret rotation facts from the loaded catalog" in tasks
    assert (
        "openbao_rotatable_secret_catalog: \"{{ lookup('ansible.builtin.file', openbao_secret_catalog_file) | from_json }}\""
        in tasks
    )
    assert "openbao_rotation_metadata: >-" in tasks


def test_openbao_runtime_checks_certificate_freshness_before_renewal() -> None:
    tasks = read_openbao_runtime_tasks_text()

    assert "Check whether the OpenBao external TLS certificate remains fresh enough" in tasks
    assert "openbao_tls_certificate_freshness" in tasks
    assert "failed_when: false" in tasks
    assert "when: openbao_tls_certificate_freshness.rc != 0" in tasks


def test_openbao_runtime_recovers_detached_empty_default_network_before_compose_up() -> None:
    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")
    tasks = read_openbao_runtime_tasks_text()

    assert 'openbao_default_network_name: "{{ openbao_site_dir | basename }}_default"' in defaults
    assert "Inspect the managed OpenBao default network before compose up" in tasks
    assert "Remove the detached managed OpenBao default network before compose up" in tasks
    assert "openbao_default_network_inspect.stdout | from_json | first" in tasks
    assert ".Containers | default({})" in tasks
    assert "      - network\n      - rm" in tasks


def test_openbao_runtime_retries_seal_status_during_restart_window() -> None:
    tasks = read_openbao_runtime_tasks_text()
    ensure_unsealed_tasks = ENSURE_UNSEALED_TASKS_PATH.read_text(encoding="utf-8")

    assert "- name: Read OpenBao initialization status" in tasks
    assert "register: openbao_init_status" in tasks
    assert "until: openbao_init_status.status == 200" in tasks
    assert "changed_when: false" in tasks
    assert "- name: Ensure OpenBao is unsealed after bootstrap or restart" in tasks
    assert "include_tasks: ensure_unsealed.yml" in tasks
    assert "openbao_unseal_context: bootstrap or restart recovery" in tasks
    assert "Read OpenBao seal status before" in ensure_unsealed_tasks
    assert "register: openbao_runtime_seal_status" in ensure_unsealed_tasks
    assert "until: openbao_runtime_seal_status.status == 200" in ensure_unsealed_tasks
    assert "register: openbao_runtime_unsealed_status" in ensure_unsealed_tasks
    assert "until:" in ensure_unsealed_tasks
    assert "openbao_runtime_unsealed_status.status == 200" in ensure_unsealed_tasks
    assert "not (openbao_runtime_unsealed_status.json.sealed | bool)" in ensure_unsealed_tasks
    assert "changed_when: false" in ensure_unsealed_tasks


def test_openbao_runtime_restores_legacy_runtime_control_state_when_local_init_exists() -> None:
    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")
    tasks = TASKS_PATH.read_text(encoding="utf-8")

    assert "openbao_legacy_restore_enabled: true" in defaults
    assert "openbao_legacy_restore_target_host: runtime-control-lv3" in defaults
    assert "openbao_legacy_restore_source_host: docker-runtime-lv3" in defaults
    assert "Determine whether legacy OpenBao state restore is required" in tasks
    assert "Read the legacy OpenBao initialization status from the source host" in tasks
    assert "Capture the legacy OpenBao raft snapshot from the source host" in tasks
    assert "Initialize temporary OpenBao barrier state before legacy snapshot restore" in tasks
    assert "Temporarily unseal OpenBao before legacy snapshot restore" in tasks
    assert "Force restore the legacy OpenBao raft snapshot onto the runtime-control node" in tasks
    assert "Refresh OpenBao initialization status after legacy snapshot restore" in tasks
    assert "/v1/sys/storage/raft/snapshot" in tasks
    assert "/v1/sys/storage/raft/snapshot-force" in tasks


def test_openbao_runtime_normalizes_init_status_payloads_before_branching() -> None:
    tasks = TASKS_PATH.read_text(encoding="utf-8")

    assert "Normalize the OpenBao initialization status payload" in tasks
    assert "Normalize the legacy OpenBao initialization status payload" in tasks
    assert "Normalize the refreshed OpenBao initialization status payload" in tasks
    assert "openbao_init_status_payload.initialized | default(false) | bool" in tasks
    assert "openbao_legacy_source_init_status_payload.initialized | default(false) | bool" in tasks


def test_openbao_runtime_continues_after_docker_chain_recheck_when_compose_health_checks_guard_recovery() -> None:
    tasks = read_openbao_runtime_tasks_text()

    assert "Recheck Docker nat chain before OpenBao startup" in tasks
    assert "failed_when: openbao_docker_nat_chain_recheck.rc not in [0, 1]" in tasks
    assert "failed_when: openbao_docker_forward_chain_recheck.rc not in [0, 1]" in tasks
    assert "Record Docker chain readiness before OpenBao startup" in tasks
    assert "Warn when Docker chains are still missing before OpenBao startup" in tasks
    assert "continuing to docker compose up" in tasks
    assert "Assert Docker nat chain is present before OpenBao startup" not in tasks
    assert "Assert Docker forward chain is present before OpenBao startup" not in tasks


def test_openbao_runtime_recovers_dnat_chain_failures_during_compose_startup() -> None:
    tasks = read_openbao_runtime_tasks_text()

    assert "- name: Start the OpenBao stack and recover Docker bridge-chain failures" in tasks
    assert "- name: Flag Docker bridge-chain failures during OpenBao startup" in tasks
    assert "Unable to enable DNAT rule" in tasks
    assert "- name: Restart Docker to restore bridge chains before retrying OpenBao startup" in tasks
    assert "- name: Recheck Docker nat chain after Docker recovery for OpenBao startup" in tasks
    assert "- name: Remove the failed OpenBao container before retrying startup" in tasks
    assert "- name: Remove the detached managed OpenBao default network before retrying startup" in tasks
    assert "- name: Retry OpenBao startup after Docker bridge-chain recovery" in tasks


def test_openbao_runtime_recovers_docker_daemon_failures_during_image_pull() -> None:
    tasks = read_openbao_runtime_tasks_text()

    assert "- name: Pull the OpenBao image and recover Docker daemon availability" in tasks
    assert "- name: Flag Docker daemon availability failures during OpenBao image pull" in tasks
    assert "Cannot connect to the Docker daemon" in tasks
    assert "- name: Restart Docker before retrying OpenBao image pull" in tasks
    assert "- name: Wait for Docker to answer before retrying OpenBao image pull" in tasks
    assert "- name: Retry pulling the OpenBao image after Docker recovery" in tasks


def test_openbao_runtime_uses_the_shared_docker_restart_guard_for_bridge_chain_recovery() -> None:
    tasks = load_openbao_runtime_tasks()
    pull_restart = next(
        task for task in tasks if task.get("name") == "Restart Docker before retrying OpenBao image pull"
    )
    startup_restart = next(
        task
        for task in tasks
        if task.get("name") == "Restart Docker when required chains are missing before OpenBao startup"
    )
    retry_restart = next(
        task
        for task in tasks
        if task.get("name") == "Restart Docker to restore bridge chains before retrying OpenBao startup"
    )

    assert pull_restart["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert pull_restart["ansible.builtin.include_role"]["tasks_from"] == "docker_daemon_restart"
    assert pull_restart["vars"]["common_docker_daemon_restart_service_name"] == "docker"
    assert pull_restart["vars"]["common_docker_daemon_restart_reason"] == "OpenBao image pull recovery"
    assert startup_restart["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert startup_restart["ansible.builtin.include_role"]["tasks_from"] == "docker_daemon_restart"
    assert startup_restart["vars"]["common_docker_daemon_restart_service_name"] == "docker"
    assert startup_restart["vars"]["common_docker_daemon_restart_reason"] == "OpenBao startup bridge-chain recovery"
    assert retry_restart["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert retry_restart["ansible.builtin.include_role"]["tasks_from"] == "docker_daemon_restart"
    assert retry_restart["vars"]["common_docker_daemon_restart_service_name"] == "docker"
    assert retry_restart["vars"]["common_docker_daemon_restart_reason"] == "OpenBao retry bridge-chain recovery"


def test_openbao_runtime_persisted_approles_use_reusable_secret_ids() -> None:
    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")

    assert defaults.count("secret_id_num_uses: 0") >= 4


def test_openbao_runtime_pins_a_non_expiring_atlas_secret_id() -> None:
    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")

    assert "  - name: atlas\n" in defaults
    assert "    secret_id_ttl: 0\n" in defaults


def test_openbao_postgres_backend_grants_reserved_connection_admin_option() -> None:
    tasks = OPENBAO_POSTGRES_BACKEND_TASKS_PATH.read_text(encoding="utf-8")

    assert "Ensure the shared OpenBao database-connect role exists" in tasks
    assert "Grant CONNECT on every managed database to the shared OpenBao database-connect role" in tasks
    assert "GRANT CONNECT ON DATABASE %I TO %I" in tasks
    assert "Grant the shared OpenBao database-connect role to the rotator with admin option" in tasks
    assert "GRANT {{ openbao_postgres_connect_role }} TO {{ openbao_postgres_admin_role }} WITH ADMIN OPTION" in tasks
    assert "Grant pg_read_all_data with admin option to the OpenBao rotator role" in tasks
    assert "Grant reserved PostgreSQL connection capability to the OpenBao rotator role" in tasks
    assert (
        "GRANT {{ openbao_postgres_reserved_connection_role }} TO {{ openbao_postgres_admin_role }} WITH ADMIN OPTION"
        in tasks
    )


def test_openbao_runtime_verifies_the_atlas_approle_path() -> None:
    tasks = read_openbao_runtime_tasks_text()

    assert "Read the Atlas AppRole artifact" in tasks
    assert "openbao_atlas_approle_raw" in tasks
    assert "Login with the Atlas AppRole" in tasks
    assert "Request a PostgreSQL schema-inspection credential through the Atlas AppRole" in tasks
    assert "postgres-atlas-readonly" in tasks


def test_openbao_runtime_reconciles_allowed_roles_after_database_role_upserts() -> None:
    tasks = yaml.safe_load(TASKS_PATH.read_text(encoding="utf-8"))
    task_names = [task["name"] for task in tasks]

    backend_index = task_names.index(
        "Configure the PostgreSQL dynamic credential backend through recovery-aware retries"
    )
    roles_index = task_names.index("Configure OpenBao database roles")
    reconcile_index = task_names.index(
        "Reconcile PostgreSQL dynamic credential backend allowed roles after role upserts"
    )

    assert backend_index < roles_index < reconcile_index

    backend_task = tasks[backend_index]
    configure_task = backend_task["block"][1]
    uri_module = configure_task["ansible.builtin.uri"]

    assert uri_module["body"]["allowed_roles"] == "{{ openbao_database_allowed_roles | join(',') }}"
    assert (
        backend_task["block"][0]["name"]
        == "Ensure OpenBao remains unsealed before configuring the PostgreSQL dynamic credential backend"
    )
    assert configure_task["register"] == "openbao_database_backend_result"
    assert configure_task["until"] == "openbao_database_backend_result.status == 204"
    assert (
        backend_task["rescue"][0]["name"]
        == "Ensure OpenBao remains unsealed before retrying the PostgreSQL dynamic credential backend configuration"
    )
    assert (
        backend_task["rescue"][1]["name"]
        == "Retry configuring the PostgreSQL dynamic credential backend after runtime recovery"
    )

    reconcile_task = tasks[reconcile_index]
    assert (
        reconcile_task["block"][0]["name"]
        == "Ensure OpenBao remains unsealed before reconciling PostgreSQL dynamic credential backend allowed roles"
    )
    assert (
        reconcile_task["block"][1]["name"]
        == "Reconcile PostgreSQL dynamic credential backend allowed roles after role upserts"
    )
    assert reconcile_task["block"][1]["until"] == "openbao_database_backend_allowed_roles_result.status == 204"
    assert (
        reconcile_task["rescue"][0]["name"]
        == "Ensure OpenBao remains unsealed before retrying PostgreSQL dynamic credential backend allowed role reconciliation"
    )
    assert (
        reconcile_task["rescue"][1]["name"]
        == "Retry reconciling PostgreSQL dynamic credential backend allowed roles after runtime recovery"
    )


def test_openbao_runtime_rechecks_seal_state_before_auth_verification() -> None:
    tasks = read_openbao_runtime_tasks_text()
    ensure_unsealed_tasks = ENSURE_UNSEALED_TASKS_PATH.read_text(encoding="utf-8")
    unseal_key_tasks = UNSEAL_KEY_TASKS_PATH.read_text(encoding="utf-8")

    assert "Ensure OpenBao remains unsealed before authentication verification" in tasks
    assert "import_tasks: seeded_secrets_and_verification.yml" in TASKS_PATH.read_text(encoding="utf-8")
    assert "include_tasks: ensure_unsealed.yml" in tasks
    assert "Read OpenBao seal status before" in ensure_unsealed_tasks
    assert "openbao_runtime_unseal_completed" in ensure_unsealed_tasks
    assert "include_tasks: unseal_key.yml" in ensure_unsealed_tasks
    assert "/v1/sys/unseal" in unseal_key_tasks
    assert "openbao_runtime_unseal_completed" in unseal_key_tasks
    assert "- openbao_runtime_unsealed_status.status == 200" in ensure_unsealed_tasks
    assert "- not (openbao_runtime_unsealed_status.json.sealed | bool)" in ensure_unsealed_tasks
    assert "Wait for OpenBao to become active before" in ensure_unsealed_tasks


def test_openbao_runtime_retries_policy_reads_during_post_restart_recovery() -> None:
    tasks = read_openbao_runtime_tasks_text()

    assert "- name: Read current OpenBao policies" in tasks
    assert "register: openbao_current_policies" in tasks
    assert "      - 500" in tasks
    assert "      - 502" in tasks
    assert "      - 503" in tasks
    assert "retries: 12" in tasks
    assert "delay: 2" in tasks
    assert "until: openbao_current_policies.status in [200, 404]" in tasks
    assert "changed_when: false" in tasks


def test_openbao_runtime_sends_database_role_statements_to_openbao_as_lists() -> None:
    tasks = TASKS_PATH.read_text(encoding="utf-8")

    assert "openbao_database_role_creation_statements" in tasks
    assert "openbao_database_role_revocation_statements" in tasks
    assert "openbao_database_role_rollback_statements" in tasks
    assert "openbao_database_role_renew_statements" in tasks
    assert "item.creation_statements is not string" in tasks
    assert "(item.rollback_statements | default([])) is not string" in tasks
    assert 'creation_statements: "{{ openbao_database_role_creation_statements }}"' in tasks
    assert 'revocation_statements: "{{ openbao_database_role_revocation_statements }}"' in tasks


def test_openbao_runtime_waits_out_background_apt_maintenance() -> None:
    tasks = yaml.safe_load(TASKS_PATH.read_text(encoding="utf-8"))
    apt_task = next(
        task for task in tasks if task["name"] == "Ensure OpenBao runtime prerequisite packages are present"
    )
    apt_module = apt_task["ansible.builtin.apt"]

    assert apt_module["name"] == ["curl"]
    assert apt_module["state"] == "present"
    assert apt_module["update_cache"] is True
    assert apt_module["cache_valid_time"] == 3600
    assert apt_module["lock_timeout"] == 300
    assert apt_module["force_apt_get"] is True


def test_openbao_runtime_renders_rotatable_secret_keys_dynamically() -> None:
    tasks = read_openbao_runtime_tasks_text()

    assert "- name: Resolve controller-local seed source paths for rotatable secrets" in tasks
    assert "- name: Read controller-local seed source files for rotatable secrets" in tasks
    assert "- name: Seed dedicated rotatable secrets into OpenBao" in tasks
    assert "(item.value.openbao_field):" in tasks
    assert "register: openbao_seed_rotatable_secret_result" in tasks
    assert "until: openbao_seed_rotatable_secret_result.status == 200" in tasks
    assert (
        "- name: Seed rotation metadata for dedicated rotatable secrets one at a time through recovery-aware retries"
        in tasks
    )
    assert "ansible.builtin.include_tasks: seed_rotation_metadata.yml" in tasks
    assert "loop_var: openbao_rotation_contract" in tasks
    assert "repo_shared_local_root | default((playbook_dir | dirname) ~ '/.local', true)" in tasks
    assert "openbao_rotatable_secret_repo_local_root:" in tasks
    assert "openbao_rotatable_secret_seed_path.startswith('.local/')" in tasks
    assert (
        'openbao_rotatable_secret_seed_path: "{{ openbao_controller_secret_manifest.secrets[item.value.seed_controller_secret_id].path }}"'
        in tasks
    )
    assert "| ternary(" in tasks
    assert "| replace('.local/', '', 1)" in tasks
    assert "openbao_rotatable_secret_seed_files.results" in tasks
    assert '"{{ item.value.openbao_field }}":' not in tasks
    assert (
        "(openbao_rotation_metadata.last_rotated_metadata_key):"
        in PLAYBOOK_SEED_ROTATION_METADATA_TASKS_PATH.read_text(encoding="utf-8")
    )
    assert (
        "(openbao_rotation_metadata.rotated_by_metadata_key): 'openbao-seed'"
        in PLAYBOOK_SEED_ROTATION_METADATA_TASKS_PATH.read_text(encoding="utf-8")
    )


def test_openbao_runtime_reads_rotatable_seed_sources_from_the_shared_overlay_root() -> None:
    tasks = load_seeded_secret_tasks()
    resolve_task = next(
        task for task in tasks if task["name"] == "Resolve controller-local seed source paths for rotatable secrets"
    )
    stat_task = next(
        task for task in tasks if task["name"] == "Check controller-local seed source files for rotatable secrets"
    )
    slurp_task = next(
        task for task in tasks if task["name"] == "Read controller-local seed source files for rotatable secrets"
    )
    seed_task = next(task for task in tasks if task["name"] == "Seed dedicated rotatable secrets into OpenBao")

    assert resolve_task["vars"]["openbao_rotatable_secret_seed_path"] == (
        "{{ openbao_controller_secret_manifest.secrets[item.value.seed_controller_secret_id].path }}"
    )
    assert resolve_task["vars"]["openbao_rotatable_secret_repo_local_root"] == (
        "{{ repo_shared_local_root | default((playbook_dir | dirname) ~ '/.local', true) }}"
    )
    assert stat_task["delegate_to"] == "localhost"
    assert stat_task["become"] is False
    assert slurp_task["delegate_to"] == "localhost"
    assert slurp_task["become"] is False
    assert seed_task["no_log"] is True
    assert "openbao_rotatable_secret_seed_files.results" in seed_task["ansible.builtin.uri"]["body"]["data"]


def test_openbao_seed_rotation_metadata_task_recovers_each_secret_through_unseal_checks() -> None:
    metadata_tasks = yaml.safe_load(PLAYBOOK_SEED_ROTATION_METADATA_TASKS_PATH.read_text(encoding="utf-8"))
    task_names = [task["name"] for task in metadata_tasks]

    assert (
        "Ensure OpenBao remains unsealed before seeding rotation metadata for {{ openbao_rotation_contract.key }}"
        in task_names
    )
    assert "Seed rotation metadata for {{ openbao_rotation_contract.key }}" in task_names

    seed_task = next(
        task
        for task in metadata_tasks
        if task["name"] == "Seed rotation metadata for {{ openbao_rotation_contract.key }}"
    )
    update_task = seed_task["block"][0]
    update_module = update_task["ansible.builtin.uri"]

    assert update_module["url"] == (
        "http://127.0.0.1:{{ openbao_http_port }}/v1/kv/metadata/{{ openbao_rotation_contract.value.openbao_path }}"
    )
    assert update_module["status_code"] == [200, 204, 500, 502, 503]
    assert update_task["register"] == "openbao_seed_rotation_metadata_item_result"
    assert update_task["until"] == "openbao_seed_rotation_metadata_item_result.status in [200, 204]"

    retry_task = seed_task["rescue"][1]
    assert (
        retry_task["name"]
        == "Retry the OpenBao rotation metadata update after runtime recovery for {{ openbao_rotation_contract.key }}"
    )


def test_openbao_runtime_retries_other_read_side_api_checks_after_restart() -> None:
    tasks = read_openbao_runtime_tasks_text()

    assert "- name: Discover enabled auth methods" in tasks
    assert "register: openbao_auth_methods" in tasks
    assert "until: openbao_auth_methods.status == 200" in tasks
    assert "- name: Discover enabled secret engines" in tasks
    assert "register: openbao_secret_engines" in tasks
    assert "until: openbao_secret_engines.status == 200" in tasks
    assert "- name: Read current OpenBao transit keys" in tasks
    assert "register: openbao_transit_key_statuses" in tasks
    assert "until: openbao_transit_key_statuses.status in [200, 404]" in tasks
    assert "- name: Read current controller Proxmox API secret" in tasks
    assert "until: openbao_controller_proxmox_api_current.status in [200, 404]" in tasks
    assert "- name: Read current controller monitoring secret" in tasks
    assert "until: openbao_controller_monitoring_current.status in [200, 404]" in tasks
    assert "- name: Read current mail platform runtime secret" in tasks
    assert "until: openbao_mail_platform_runtime_current.status in [200, 404]" in tasks
    assert "- name: Read current dedicated rotatable secrets from OpenBao" in tasks
    assert "      - 500" in tasks
    assert "      - 502" in tasks
    assert "      - 503" in tasks
    assert "retries: 12" in tasks
    assert "changed_when: false" in tasks
    assert "until: openbao_rotatable_secret_current.status in [200, 404]" in tasks


def test_openbao_runtime_verification_requests_skip_become_on_loopback() -> None:
    tasks = read_openbao_runtime_tasks_text()

    ops_login_section = tasks.split("- name: Verify userpass login for the ops operator", 1)[1].split(
        "- name: Assert that the ops userpass login succeeded",
        1,
    )[0]
    dynamic_credential_section = tasks.split(
        "- name: Request a PostgreSQL dynamic credential through the controller AppRole",
        1,
    )[1].split("- name: Assert that a PostgreSQL dynamic credential was issued", 1)[0]

    assert "become: false" in ops_login_section
    assert "become: false" in dynamic_credential_section
    assert "- name: Read AppRole role IDs" in tasks
    assert "until: openbao_approle_role_ids.status == 200" in tasks
    assert "- name: Generate fresh short-lived AppRole secret IDs" in tasks
    assert "until: openbao_generated_secret_ids.status | default(0) == 200" in tasks
    assert "- name: Assert fresh short-lived AppRole secret IDs were generated successfully" in tasks
    assert "- name: Verify userpass login for the ops operator" in tasks
    assert "until: openbao_ops_login.status == 200" in tasks
    assert "- name: Login with the controller AppRole" in tasks
    assert "- openbao_controller_login.status | default(0) == 200" in tasks
    assert "- openbao_controller_login.json.auth.client_token | default('') | length > 0" in tasks
    assert "- name: Read the controller Proxmox API secret through the AppRole" in tasks
    assert "until: openbao_controller_secret_read.status == 200" in tasks
    assert "- name: Encrypt test material with the controller transit key" in tasks
    assert "until: openbao_controller_transit_encrypt.status == 200" in tasks
    assert "- name: Decrypt test material with the controller transit key" in tasks
    assert "until: openbao_controller_transit_decrypt.status == 200" in tasks
    assert "- name: Login with the mail-platform AppRole" in tasks
    assert "- openbao_mail_platform_login.status | default(0) == 200" in tasks
    assert "- openbao_mail_platform_login.json.auth.client_token | default('') | length > 0" in tasks
    assert "- name: Read the mail-platform runtime secret through the AppRole" in tasks
    assert "until: openbao_mail_platform_secret_read.status == 200" in tasks
    assert "- name: Refresh short-lived AppRole secret IDs after managed verification" in tasks
    assert "until: openbao_refreshed_secret_ids.status | default(0) == 200" in tasks


def test_openbao_runtime_resets_ssh_before_final_health_verification() -> None:
    tasks = load_openbao_runtime_tasks()

    names = {task["name"] for task in tasks}
    assert "Reset SSH connection before OpenBao health verification" in names
    assert "Wait for SSH after resetting the connection before OpenBao health verification" in names

    wait_for_ssh = next(
        task
        for task in tasks
        if task["name"] == "Wait for SSH after resetting the connection before OpenBao health verification"
    )
    assert wait_for_ssh["ansible.builtin.wait_for_connection"]["timeout"] == 60
    assert wait_for_ssh["ansible.builtin.wait_for_connection"]["connect_timeout"] == 5
    assert wait_for_ssh["ansible.builtin.wait_for_connection"]["sleep"] == 2


def test_openbao_compose_template_supports_private_extra_http_bindings() -> None:
    template = (
        REPO_ROOT
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "openbao_runtime"
        / "templates"
        / "docker-compose.yml.j2"
    ).read_text(encoding="utf-8")

    assert "{{ openbao_http_bind_address }}:{{ openbao_http_port }}:{{ openbao_http_port }}" in template
    assert "{% for bind_address in openbao_http_extra_bind_addresses %}" in template


def test_openbao_runtime_renders_the_compose_file_from_the_active_role_path() -> None:
    tasks = yaml.safe_load(TASKS_PATH.read_text(encoding="utf-8"))
    render_task = next(task for task in tasks if task["name"] == "Render the OpenBao Compose file")
    copy_module = render_task["ansible.builtin.copy"]

    assert copy_module["dest"] == "{{ openbao_compose_file }}"
    assert "role_path ~ '/templates/docker-compose.yml.j2'" in copy_module["content"]


def test_openbao_playbook_refreshes_secret_ids_from_local_artifacts() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text(encoding="utf-8"))
    refresh_play = next(
        play
        for play in plays
        if play["name"] == "Refresh persisted OpenBao AppRole artifacts after end-to-end verification"
    )
    tasks = refresh_play["tasks"]
    task_names = [task["name"] for task in tasks]

    assert "Read the persisted AppRole artifacts before refreshing secret IDs" in task_names
    assert "Record persisted AppRole artifact facts before refreshing secret IDs" in task_names
    assert "Ensure OpenBao remains unsealed before refreshing controller-local AppRole artifacts" in task_names
    assert "Refresh persisted AppRole artifacts one at a time after end-to-end verification" in task_names
    assert "Read AppRole role IDs for refreshed controller-local artifacts" not in task_names
    assert "Generate refreshed AppRole secret IDs after end-to-end verification" not in task_names
    assert "Persist refreshed AppRole artifacts locally after end-to-end verification" not in task_names

    include_task = next(
        task
        for task in tasks
        if task["name"] == "Refresh persisted AppRole artifacts one at a time after end-to-end verification"
    )
    assert include_task["ansible.builtin.include_tasks"] == "tasks/openbao-refresh-approle-artifact.yml"
    assert include_task["loop_control"]["loop_var"] == "openbao_refresh_approle"
    assert {"name": "atlas", "local_file": "{{ openbao_atlas_approle_local_file }}"} in refresh_play["vars"][
        "openbao_verification_approles"
    ]


def test_openbao_playbook_refresh_task_recovers_each_approle_through_unseal_checks() -> None:
    refresh_tasks = yaml.safe_load(PLAYBOOK_REFRESH_APPROLE_TASKS_PATH.read_text(encoding="utf-8"))
    task_names = [task["name"] for task in refresh_tasks]

    assert (
        "Ensure OpenBao remains unsealed before refreshing the controller-local AppRole artifact for {{ openbao_refresh_approle.name }}"
        in task_names
    )
    assert (
        "Persist the refreshed AppRole artifact locally after end-to-end verification for {{ openbao_refresh_approle.name }}"
        in task_names
    )

    request_task = next(
        task
        for task in refresh_tasks
        if task["name"]
        == "Generate the refreshed AppRole secret ID after end-to-end verification for {{ openbao_refresh_approle.name }}"
    )
    request_block = request_task["block"][0]
    request_module = request_block["ansible.builtin.uri"]

    assert request_module["url"] == (
        "http://127.0.0.1:{{ openbao_http_port }}/v1/auth/approle/role/{{ openbao_refresh_approle.name }}/secret-id"
    )
    assert request_block["retries"] == 12
    assert request_block["delay"] == 5
    assert request_block["changed_when"] is False
    assert request_task["rescue"][0]["ansible.builtin.include_role"]["tasks_from"] == "ensure_unsealed.yml"

    persist_task = next(
        task
        for task in refresh_tasks
        if task["name"]
        == "Persist the refreshed AppRole artifact locally after end-to-end verification for {{ openbao_refresh_approle.name }}"
    )
    assert (
        "openbao_refresh_existing_artifacts[openbao_refresh_approle.name].role_id"
        in persist_task["ansible.builtin.copy"]["content"]
    )


def test_openbao_playbook_verifies_dynamic_credentials_with_env_and_retries() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text(encoding="utf-8"))
    verify_play = next(play for play in plays if play["name"] == "Verify PostgreSQL dynamic credentials end to end")
    verify_task = next(
        task
        for task in verify_play["tasks"]
        if task["name"] == "Verify the issued PostgreSQL credential against the local database"
    )

    assert "PGPASSWORD='" not in verify_task["ansible.builtin.shell"]
    assert (
        verify_task["environment"]["PGPASSWORD"]
        == "{{ openbao_verify_postgres_dynamic_credential.json.data.password }}"
    )
    assert verify_task["retries"] == 6
    assert verify_task["delay"] == 5
    assert verify_task["failed_when"] is False


def test_openbao_inventory_exports_controller_local_artifact_paths_used_outside_role_scope() -> None:
    group_vars = yaml.safe_load(GROUP_VARS_PATH.read_text(encoding="utf-8"))

    assert group_vars["openbao_postgres_connect_role"] == "lv3_openbao_connect_all"
    assert (
        group_vars["openbao_controller_approle_local_file"]
        == "{{ repo_shared_local_root }}/openbao/controller-automation-approle.json"
    )
    assert group_vars["openbao_atlas_approle_local_file"] == "{{ repo_shared_local_root }}/openbao/atlas-approle.json"
    assert (
        group_vars["openbao_mail_platform_approle_local_file"]
        == "{{ repo_shared_local_root }}/openbao/mail-platform-approle.json"
    )
