from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "restic_config_backup"
)
DEFAULTS_PATH = ROLE_ROOT / "defaults" / "main.yml"
TASKS_PATH = ROLE_ROOT / "tasks" / "main.yml"
SERVICE_TEMPLATE_PATH = ROLE_ROOT / "templates" / "lv3-restic-config-backup.service.j2"


def load_tasks() -> list[dict]:
    return yaml.safe_load(TASKS_PATH.read_text(encoding="utf-8"))


def test_defaults_pin_repo_checkout_and_receipt_locations() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert defaults["restic_config_backup_repo_checkout_host_path"] == "/srv/proxmox_florin_server"
    assert defaults["restic_config_backup_catalog_repo_path"].endswith("/config/restic-file-backup-catalog.json")
    assert defaults["restic_config_backup_backup_receipts_dir"].endswith("/receipts/restic-backups")
    assert defaults["restic_config_backup_restore_verification_dir"].endswith(
        "/receipts/restic-restore-verifications"
    )
    assert defaults["restic_config_backup_timer_name"] == "lv3-restic-config-backup.timer"
    assert defaults["restic_config_backup_minio_container_name"] == "minio"
    assert defaults["restic_config_backup_minio_access_key"] == "minio-root"
    assert defaults["restic_config_backup_minio_secret_key_local_file"].endswith("/.local/minio/root-password.txt")


def test_minio_bucket_bootstrap_keeps_mc_alias_and_commands_in_one_exec_session() -> None:
    tasks = load_tasks()
    bootstrap_task = next(task for task in tasks if task.get("name") == "Ensure the MinIO restic bucket exists with object lock")
    shell = bootstrap_task["ansible.builtin.shell"]

    assert shell.count("docker exec") == 1
    assert "docker inspect --format '{% raw %}{{.State.Running}}{% endraw %}' {{ restic_config_backup_minio_container_name | quote }}" in shell
    assert "docker start {{ restic_config_backup_minio_container_name | quote }} >/dev/null" in shell
    assert "{{ restic_config_backup_minio_container_name | quote }} sh -ceu" in shell
    assert "-e MINIO_ROOT_USER={{ restic_config_backup_minio_access_key | quote }}" in shell
    assert "mc alias set local http://127.0.0.1:9000 \"$MINIO_ROOT_USER\" \"$MINIO_ROOT_PASSWORD\"" in shell
    assert "mc mb --ignore-existing --with-lock local/restic-config-backup" in shell
    assert "mc version enable local/restic-config-backup" in shell


def test_runtime_support_files_are_staged_into_worker_checkout_before_validation_run() -> None:
    tasks = load_tasks()
    sync_task = next(task for task in tasks if task.get("name") == "Sync restic runtime support files into the worker checkout")

    assert sync_task["ansible.builtin.copy"]["dest"] == "{{ restic_config_backup_repo_checkout_host_path }}/{{ item.dest }}"
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
    assert "ReadWritePaths={{ restic_config_backup_runtime_state_dir }} {{ restic_config_backup_repo_checkout_host_path }}/receipts" in template
