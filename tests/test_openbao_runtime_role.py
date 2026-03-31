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
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "openbao.yml"


def read_openbao_runtime_tasks_text() -> str:
    return TASKS_PATH.read_text(encoding="utf-8") + "\n" + SEEDED_SECRET_TASKS_PATH.read_text(encoding="utf-8")


def test_openbao_runtime_defaults_use_postgres_primary_address() -> None:
    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")

    assert "openbao_postgres_host:" in defaults
    assert 'openbao_controller_url | urlsplit(\'hostname\')' in defaults
    assert "postgres_ha.initial_primary" in defaults
    assert "ansible_host" in defaults
    assert "@{{ openbao_postgres_host }}:5432/postgres?sslmode=disable" in defaults
    assert 'CREATE ROLE "{{name}}" WITH LOGIN PASSWORD \'{{password}}\' VALID UNTIL \'{{expiration}}\';' in defaults
    assert 'GRANT pg_read_all_data TO "{{name}}";' in defaults
    assert 'DROP ROLE IF EXISTS "{{name}}";' in defaults
    assert "openbao_http_extra_bind_addresses: []" in defaults


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

    assert f"mattermost_database_host: \"{expected}\"" in mattermost_defaults
    assert f"netbox_database_host: \"{expected}\"" in netbox_defaults


def test_openbao_rotation_catalog_is_loaded_before_derived_facts() -> None:
    tasks = read_openbao_runtime_tasks_text()

    assert "- name: Load the rotatable secret catalog and controller secret manifest" in tasks
    assert "- name: Derive OpenBao secret rotation facts from the loaded catalog" in tasks
    assert "openbao_rotatable_secret_catalog: \"{{ lookup('ansible.builtin.file', openbao_secret_catalog_file) | from_json }}\"" in tasks
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
    assert '      - network\n      - rm' in tasks


def test_openbao_runtime_retries_seal_status_during_restart_window() -> None:
    tasks = read_openbao_runtime_tasks_text()

    assert "- name: Read OpenBao initialization status" in tasks
    assert "register: openbao_init_status" in tasks
    assert "until: openbao_init_status.status == 200" in tasks
    assert "- name: Read OpenBao seal status" in tasks
    assert "register: openbao_seal_status" in tasks
    assert "until: openbao_seal_status.status == 200" in tasks
    assert "register: openbao_unsealed_status" in tasks
    assert "until: openbao_unsealed_status.status == 200" in tasks
    assert "changed_when: false" in tasks


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


def test_openbao_runtime_persisted_approles_use_reusable_secret_ids() -> None:
    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")

    assert defaults.count("secret_id_num_uses: 0") >= 3


def test_openbao_runtime_rechecks_seal_state_before_auth_verification() -> None:
    tasks = read_openbao_runtime_tasks_text()
    ensure_unsealed_tasks = ENSURE_UNSEALED_TASKS_PATH.read_text(encoding="utf-8")

    assert "Ensure OpenBao remains unsealed before authentication verification" in tasks
    assert "import_tasks: seeded_secrets_and_verification.yml" in TASKS_PATH.read_text(encoding="utf-8")
    assert "include_tasks: ensure_unsealed.yml" in tasks
    assert "Read OpenBao seal status before" in ensure_unsealed_tasks
    assert "/v1/sys/unseal" in ensure_unsealed_tasks
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


def test_openbao_runtime_waits_out_background_apt_maintenance() -> None:
    tasks = yaml.safe_load(TASKS_PATH.read_text(encoding="utf-8"))
    apt_task = next(task for task in tasks if task["name"] == "Ensure OpenBao runtime prerequisite packages are present")
    apt_module = apt_task["ansible.builtin.apt"]

    assert apt_module["name"] == ["curl"]
    assert apt_module["state"] == "present"
    assert apt_module["update_cache"] is True
    assert apt_module["cache_valid_time"] == 3600
    assert apt_module["lock_timeout"] == 300
    assert apt_module["force_apt_get"] is True


def test_openbao_runtime_renders_rotatable_secret_keys_dynamically() -> None:
    tasks = read_openbao_runtime_tasks_text()

    assert "- name: Seed dedicated rotatable secrets into OpenBao" in tasks
    assert "(item.value.openbao_field):" in tasks
    assert "register: openbao_seed_rotatable_secret_result" in tasks
    assert "until: openbao_seed_rotatable_secret_result.status == 200" in tasks
    assert "\"{{ item.value.openbao_field }}\":" not in tasks
    assert "(openbao_rotation_metadata.last_rotated_metadata_key):" in tasks
    assert "(openbao_rotation_metadata.rotated_by_metadata_key): 'openbao-seed'" in tasks
    assert "register: openbao_rotatable_secret_metadata_seed" in tasks
    assert "until: openbao_rotatable_secret_metadata_seed.status in [200, 204]" in tasks
    assert "- name: Assert rotation metadata for dedicated rotatable secrets was seeded successfully" in tasks


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
    assert "until: openbao_rotatable_secret_current.status in [200, 404]" in tasks
    assert "- name: Read AppRole role IDs" in tasks
    assert "until: openbao_approle_role_ids.status == 200" in tasks
    assert "- name: Generate fresh short-lived AppRole secret IDs" in tasks
    assert "until: openbao_generated_secret_ids.status == 200" in tasks
    assert "- name: Assert fresh short-lived AppRole secret IDs were generated successfully" in tasks
    assert "- name: Verify userpass login for the ops operator" in tasks
    assert "until: openbao_ops_login.status == 200" in tasks
    assert "- name: Login with the controller AppRole" in tasks
    assert "until: openbao_controller_login.status == 200" in tasks
    assert "- name: Read the controller Proxmox API secret through the AppRole" in tasks
    assert "until: openbao_controller_secret_read.status == 200" in tasks
    assert "- name: Encrypt test material with the controller transit key" in tasks
    assert "until: openbao_controller_transit_encrypt.status == 200" in tasks
    assert "- name: Decrypt test material with the controller transit key" in tasks
    assert "until: openbao_controller_transit_decrypt.status == 200" in tasks
    assert "- name: Login with the mail-platform AppRole" in tasks
    assert "until: openbao_mail_platform_login.status == 200" in tasks
    assert "- name: Read the mail-platform runtime secret through the AppRole" in tasks
    assert "until: openbao_mail_platform_secret_read.status == 200" in tasks
    assert "- name: Refresh short-lived AppRole secret IDs after managed verification" in tasks
    assert "until: openbao_refreshed_secret_ids.status == 200" in tasks
    assert "- name: Assert refreshed short-lived AppRole secret IDs were generated successfully" in tasks


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
    assert "Assert refreshed AppRole secret IDs were generated successfully after end-to-end verification" in task_names
    assert "Read AppRole role IDs for refreshed controller-local artifacts" not in task_names

    refresh_task = next(
        task for task in tasks if task["name"] == "Generate refreshed AppRole secret IDs after end-to-end verification"
    )
    assert refresh_task["retries"] == 6
    assert refresh_task["delay"] == 2
    assert refresh_task["until"] == "openbao_refresh_secret_ids.status == 200"

    persist_task = next(
        task for task in tasks if task["name"] == "Persist refreshed AppRole artifacts locally after end-to-end verification"
    )
    assert "openbao_refresh_existing_artifacts[item.item.name].role_id" in persist_task["ansible.builtin.copy"]["content"]
