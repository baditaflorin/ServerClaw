from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_validation_gate_runs_data_catalog_check() -> None:
    validate_gate = (REPO_ROOT / "config" / "validation-gate.json").read_text(encoding="utf-8")
    validate_script = (REPO_ROOT / "scripts" / "validate_repo.sh").read_text(encoding="utf-8")

    assert "scripts/data_catalog.py --validate" in validate_gate
    assert 'scripts/data_catalog.py" --validate' in validate_script


def test_data_retention_role_deploys_systemd_timer() -> None:
    tasks = (REPO_ROOT / "roles" / "data_retention" / "tasks" / "main.yml").read_text(encoding="utf-8")
    service = (REPO_ROOT / "roles" / "data_retention" / "templates" / "lv3-data-retention.service.j2").read_text(
        encoding="utf-8"
    )
    timer = (REPO_ROOT / "roles" / "data_retention" / "templates" / "lv3-data-retention.timer.j2").read_text(
        encoding="utf-8"
    )

    assert "Copy the repo-managed purge script" in tasks
    assert "--receipts-root {{ data_retention_receipts_root }}" in service
    assert "OnCalendar={{ data_retention_on_calendar }}" in timer


def test_monitoring_and_runtime_roles_expose_retention_settings() -> None:
    monitoring_defaults = (REPO_ROOT / "roles" / "monitoring_vm" / "defaults" / "main.yml").read_text(encoding="utf-8")
    monitoring_tasks = (REPO_ROOT / "roles" / "monitoring_vm" / "tasks" / "main.yml").read_text(encoding="utf-8")
    mattermost_env = (REPO_ROOT / "roles" / "mattermost_runtime" / "templates" / "mattermost.env.j2").read_text(
        encoding="utf-8"
    )
    mattermost_env_ctmpl = (
        REPO_ROOT / "roles" / "mattermost_runtime" / "templates" / "mattermost.env.ctmpl.j2"
    ).read_text(encoding="utf-8")
    netbox_env = (REPO_ROOT / "roles" / "netbox_runtime" / "templates" / "netbox.env.j2").read_text(encoding="utf-8")
    netbox_tasks = (REPO_ROOT / "roles" / "netbox_runtime" / "tasks" / "main.yml").read_text(encoding="utf-8")
    preflight_tasks = (REPO_ROOT / "roles" / "preflight" / "tasks" / "main.yml").read_text(encoding="utf-8")

    assert "monitoring_loki_retention_default: 720h" in monitoring_defaults
    assert "monitoring_tempo_trace_retention: 336h" in monitoring_defaults
    assert "option: max_age" in monitoring_tasks
    assert "MM_DATARETENTIONSETTINGS_ENABLEMESSAGEDELETION=true" in mattermost_env
    assert "MM_DATARETENTIONSETTINGS_MESSAGERETENTIONDAYS=0" in mattermost_env
    assert "MM_DATARETENTIONSETTINGS_FILERETENTIONDAYS=0" in mattermost_env
    assert "MM_DATARETENTIONSETTINGS_MESSAGERETENTIONHOURS={{ mattermost_message_retention_hours }}" in mattermost_env
    assert "MM_DATARETENTIONSETTINGS_FILERETENTIONHOURS={{ mattermost_file_retention_hours }}" in mattermost_env
    assert "MM_DATARETENTIONSETTINGS_MESSAGERETENTIONDAYS=0" in mattermost_env_ctmpl
    assert "MM_DATARETENTIONSETTINGS_FILERETENTIONDAYS=0" in mattermost_env_ctmpl
    assert (
        "MM_DATARETENTIONSETTINGS_MESSAGERETENTIONHOURS={{ mattermost_message_retention_hours }}"
        in mattermost_env_ctmpl
    )
    assert "MM_DATARETENTIONSETTINGS_FILERETENTIONHOURS={{ mattermost_file_retention_hours }}" in mattermost_env_ctmpl
    assert "CHANGELOG_RETENTION={{ netbox_changelog_retention_days }}" in netbox_env
    assert "Enable the NetBox housekeeping timer" in netbox_tasks
    assert "Find controller-side .env files in the repository workspace" in preflight_tasks
