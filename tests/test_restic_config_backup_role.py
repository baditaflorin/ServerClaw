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


def test_defaults_pin_repo_checkout_and_receipt_locations() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert defaults["restic_config_backup_repo_checkout_host_path"] == "/srv/proxmox-host_server"
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
    assert defaults["restic_config_backup_timer_name"] == "lv3-restic-config-backup.timer"
    assert defaults["restic_config_backup_minio_container_name"] == "minio"
    assert defaults["restic_config_backup_minio_access_key"] == "minio-root"
    assert defaults["restic_config_backup_minio_secret_key_local_file"].endswith("/.local/minio/root-password.txt")


def test_minio_bucket_bootstrap_keeps_mc_alias_and_commands_in_one_exec_session() -> None:
    tasks = load_tasks()
    bootstrap_task = next(
        task for task in tasks if task.get("name") == "Ensure the MinIO restic bucket exists with object lock"
    )
    shell = bootstrap_task["ansible.builtin.shell"]

    assert shell.count("docker exec") == 1
    assert "container_name={{ restic_config_backup_minio_container_name | quote }}" in shell
    assert "if docker inspect outline-minio >/dev/null 2>&1; then" in shell
    assert "container_name=outline-minio" in shell
    assert "docker inspect --format '{% raw %}{{.State.Running}}{% endraw %}' \"$container_name\"" in shell
    assert 'docker start "$container_name" >/dev/null' in shell
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

    assert names.index("Check whether the shared MinIO container exists") < names.index(
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
        "{{ restic_config_backup_minio_container_name }}",
    ]

    wait_task = next(
        task for task in tasks if task.get("name") == "Wait for the shared MinIO container to report running"
    )
    assert wait_task["retries"] == 12
    assert wait_task["delay"] == 5
    assert "restic_config_backup_minio_container_running_verify.stdout_lines" in wait_task["until"]


def test_runtime_support_files_are_staged_into_worker_checkout_before_validation_run() -> None:
    tasks = load_tasks()
    sync_task = next(
        task for task in tasks if task.get("name") == "Sync restic runtime support files into the worker checkout"
    )

    assert (
        sync_task["ansible.builtin.copy"]["dest"]
        == "{{ restic_config_backup_repo_checkout_host_path }}/{{ item.dest }}"
    )
    loop = sync_task["loop"]
    assert loop == [
        {
            "src": "{{ playbook_dir | dirname }}/scripts/restic_config_backup.py",
            "dest": "scripts/restic_config_backup.py",
            "mode": "0755",
        },
        {
            "src": "{{ playbook_dir | dirname }}/scripts/script_bootstrap.py",
            "dest": "scripts/script_bootstrap.py",
            "mode": "0644",
        },
        {
            "src": "{{ playbook_dir | dirname }}/scripts/controller_automation_toolkit.py",
            "dest": "scripts/controller_automation_toolkit.py",
            "mode": "0644",
        },
        {
            "src": "{{ playbook_dir | dirname }}/config/restic-file-backup-catalog.json",
            "dest": "config/restic-file-backup-catalog.json",
            "mode": "0644",
        },
    ]


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
