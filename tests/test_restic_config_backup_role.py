from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "restic_config_backup"
DEFAULTS_PATH = ROLE_ROOT / "defaults" / "main.yml"
TASKS_PATH = ROLE_ROOT / "tasks" / "main.yml"
SERVICE_TEMPLATE_PATH = ROLE_ROOT / "templates" / "lv3-restic-config-backup.service.j2"
WRAPPER_TEMPLATE_PATH = ROLE_ROOT / "templates" / "lv3-restic-config-backup.sh.j2"


def load_tasks() -> list[dict]:
    return yaml.safe_load(TASKS_PATH.read_text(encoding="utf-8"))


def test_defaults_derive_repo_checkout_and_receipt_locations_from_platform_identity() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert defaults["restic_config_backup_repo_checkout_host_path"] == "{{ platform_repo_checkout_path }}"
    assert (
        defaults["restic_config_backup_fallback_script_path"]
        == "/opt/api-gateway/service/scripts/restic_config_backup.py"
    )
    assert defaults["restic_config_backup_minio_container_name"] == "minio"
    assert defaults["restic_config_backup_runtime_catalog_path"] == (
        "{{ restic_config_backup_runtime_config_dir }}/restic-file-backup-catalog.json"
    )
    assert defaults["restic_config_backup_catalog_repo_path"].endswith("/config/restic-file-backup-catalog.json")
    assert defaults["restic_config_backup_backup_receipts_dir"].endswith("/receipts/restic-backups")
    assert defaults["restic_config_backup_restore_verification_dir"].endswith("/receipts/restic-restore-verifications")
    assert defaults["restic_config_backup_minio_container_name"] == "minio"
    assert (
        defaults["restic_config_backup_timer_name"]
        == "{{ platform_identity.config_prefix }}-restic-config-backup.timer"
    )
    assert defaults["restic_config_backup_minio_container_name"] == "minio"
    assert defaults["restic_config_backup_minio_access_key"] == "minio-root"
    assert defaults["restic_config_backup_minio_secret_key_local_file"].endswith("/.local/minio/root-password.txt")
    assert defaults["restic_config_backup_runtime_openbao_provisioner_approle_name"] == "runtime-secret-provisioner"
    assert (
        "agent-runtime-secret-provisioner" in defaults["restic_config_backup_runtime_openbao_provisioner_policy_name"]
    )


def test_minio_bucket_bootstrap_keeps_mc_alias_and_commands_in_one_exec_session() -> None:
    tasks = load_tasks()
    bootstrap_task = next(
        task for task in tasks if task.get("name") == "Ensure the MinIO restic bucket exists with object lock"
    )
    shell = bootstrap_task["ansible.builtin.shell"]

    assert shell.count("docker exec") == 1
    assert "container_name={{ restic_config_backup_minio_container_effective_name.stdout | trim | quote }}" in shell
    assert '"$container_name" sh -ceu' in shell
    assert "-e MINIO_ROOT_USER={{ restic_config_backup_minio_access_key | quote }}" in shell
    assert 'mc alias set local http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"' in shell
    assert "mc mb --ignore-existing --with-lock local/restic-config-backup" in shell
    assert "mc version enable local/restic-config-backup" in shell
    assert bootstrap_task["retries"] == 12
    assert bootstrap_task["delay"] == 5
    assert bootstrap_task["until"] == "restic_config_backup_bucket_bootstrap.rc == 0"


def test_role_starts_shared_minio_container_before_bucket_bootstrap() -> None:
    tasks = load_tasks()
    names = [task.get("name") for task in tasks]

    assert names.index("Determine the effective shared MinIO container name") < names.index(
        "Assert the shared MinIO container exists"
    )
    assert names.index("Assert the shared MinIO container exists") < names.index(
        "Ensure the MinIO restic bucket exists with object lock"
    )
    assert names.index("Start the shared MinIO container when it is stopped") < names.index(
        "Ensure the MinIO restic bucket exists with object lock"
    )

    start_task = next(
        task for task in tasks if task.get("name") == "Start the shared MinIO container when it is stopped"
    )
    assert start_task["ansible.builtin.command"]["argv"] == [
        "docker",
        "start",
        "{{ restic_config_backup_minio_container_effective_name.stdout | trim }}",
    ]

    wait_task = next(
        task for task in tasks if task.get("name") == "Wait for the shared MinIO container to report running"
    )
    assert wait_task["retries"] == 12
    assert wait_task["delay"] == 5
    assert "restic_config_backup_minio_container_running_verify.stdout_lines" in wait_task["until"]


def test_runtime_support_files_are_staged_into_managed_runtime_checkout_before_validation_run() -> None:
    tasks = load_tasks()
    sync_task = next(
        task for task in tasks if task.get("name") == "Sync restic runtime support files into the worker checkout"
    )

    assert (
        sync_task["ansible.builtin.copy"]["dest"]
        == "{{ restic_config_backup_repo_checkout_host_path }}/{{ item.dest }}"
    )
    staged_paths = {(item["dest"], item["mode"]) for item in sync_task["loop"]}
    assert staged_paths == {
        ("scripts/restic_config_backup.py", "0755"),
        ("scripts/outline_client.py", "0644"),
        ("scripts/script_bootstrap.py", "0644"),
        ("scripts/controller_automation_toolkit.py", "0644"),
        ("scripts/ntfy_publish.py", "0644"),
        ("scripts/validation_toolkit.py", "0644"),
        ("platform/__init__.py", "0644"),
        ("platform/datetime_compat.py", "0644"),
        ("platform/enum_compat.py", "0644"),
        ("platform/events/__init__.py", "0644"),
        ("platform/events/taxonomy.py", "0644"),
        ("platform/repo.py", "0644"),
        ("platform/retry/__init__.py", "0644"),
        ("platform/retry/classification.py", "0644"),
        ("platform/retry/policy.py", "0644"),
        ("config/event-taxonomy.yaml", "0644"),
        ("config/ntfy/topics.yaml", "0644"),
        ("config/retry-policies.yaml", "0644"),
        ("config/restic-file-backup-catalog.json", "0644"),
        ("config/controller-local-secrets.json", "0644"),
        ("config/falco/rules.d/platform-overrides.yaml", "0644"),
        ("config/falco/suppressions.yaml", "0644"),
        ("versions/stack.yaml", "0644"),
    }


def test_role_bootstraps_its_own_runtime_checkout_before_staging_support_files() -> None:
    tasks = load_tasks()
    names = [task.get("name") for task in tasks]
    skeleton_task = next(
        task
        for task in tasks
        if task.get("name") == "Ensure the managed Restic runtime checkout skeleton exists on docker-runtime"
    )

    assert "{{ restic_config_backup_repo_checkout_host_path }}" in skeleton_task["loop"]
    assert "{{ restic_config_backup_backup_receipts_dir }}" in skeleton_task["loop"]
    assert "{{ restic_config_backup_restore_verification_dir }}" in skeleton_task["loop"]
    assert "{{ restic_config_backup_repo_checkout_host_path }}/config/falco/rules.d" in skeleton_task["loop"]
    assert names.index(skeleton_task["name"]) < names.index(
        "Sync restic runtime support files into the worker checkout"
    )


def test_service_template_allows_runtime_state_and_receipts_writes() -> None:
    template = SERVICE_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "ProtectSystem=strict" in template
    assert (
        "ReadWritePaths={{ restic_config_backup_runtime_state_dir }} {{ restic_config_backup_repo_checkout_host_path }}/receipts"
        in template
    )


def test_wrapper_template_falls_back_to_api_gateway_script_when_worker_checkout_is_incomplete() -> None:
    template = WRAPPER_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert 'fallback_script="{{ restic_config_backup_fallback_script_path }}"' in template
    assert 'fallback_catalog="{{ restic_config_backup_runtime_catalog_path }}"' in template
    assert 'if [ ! -f "$script_path" ] && [ -f "$fallback_script" ]; then' in template
    assert 'if [ ! -f "$catalog_path" ] && [ -f "$fallback_catalog" ]; then' in template
    assert '--catalog "$catalog_path"' in template
    assert 'exec python3 "$script_path"' in template


def test_role_deploys_runtime_restic_catalog() -> None:
    tasks = load_tasks()
    catalog_task = next(task for task in tasks if task.get("name") == "Render the runtime restic catalog")

    assert catalog_task["ansible.builtin.copy"]["src"] == "{{ restic_config_backup_controller_catalog_local_file }}"
    assert catalog_task["ansible.builtin.copy"]["dest"] == "{{ restic_config_backup_runtime_catalog_path }}"
