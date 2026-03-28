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
    / "server_resident_reconciliation"
)


def test_defaults_define_checkout_timer_and_low_privilege_gitea_identity() -> None:
    defaults = (ROLE_ROOT / "defaults" / "main.yml").read_text(encoding="utf-8")

    assert "server_resident_reconciliation_checkout_path: /srv/proxmox_florin_server" in defaults
    assert "server_resident_reconciliation_gitea_username: lv3-reconcile" in defaults
    assert "read:repository" in defaults
    assert 'server_resident_reconciliation_on_calendar: "*:0/30"' in defaults


def test_tasks_bootstrap_gitea_access_only_when_requested() -> None:
    tasks = yaml.safe_load((ROLE_ROOT / "tasks" / "main.yml").read_text(encoding="utf-8"))
    task_names = {task["name"] for task in tasks}

    assert "Bootstrap low-privilege Gitea pull access from the controller" in task_names
    assert "Fail when the recurring reconcile path lacks its host-local Gitea read token" in task_names
    assert "Render the server-resident reconciliation wrapper" in task_names
    assert "Enable the server-resident reconciliation timer" in task_names


def test_bootstrap_tasks_create_restricted_user_and_read_token() -> None:
    tasks = (ROLE_ROOT / "tasks" / "bootstrap_gitea_access.yml").read_text(encoding="utf-8")

    assert "/api/v1/admin/users" in tasks
    assert "permission: \"{{ server_resident_reconciliation_gitea_collaborator_permission }}\"" in tasks
    assert "/api/v1/users/{{ server_resident_reconciliation_gitea_username }}/tokens" in tasks
    assert "- ls-remote" in tasks


def test_wrapper_uses_ansible_pull_with_git_askpass_and_local_limit() -> None:
    wrapper = (ROLE_ROOT / "templates" / "server-resident-reconciliation.sh.j2").read_text(encoding="utf-8")

    assert "ansible-pull" in wrapper
    assert 'export GIT_ASKPASS="$askpass_path"' in wrapper
    assert '-l "$inventory_host"' in wrapper
    assert '-c local' in wrapper
    assert 'cp "$receipt_path" "$latest_path"' in wrapper


def test_systemd_units_reference_managed_wrapper_and_timer_schedule() -> None:
    service = (ROLE_ROOT / "templates" / "lv3-server-resident-reconciliation.service.j2").read_text(encoding="utf-8")
    timer = (ROLE_ROOT / "templates" / "lv3-server-resident-reconciliation.timer.j2").read_text(encoding="utf-8")

    assert "ExecStart={{ server_resident_reconciliation_wrapper_path }}" in service
    assert "ConditionPathExists={{ server_resident_reconciliation_http_token_remote_file }}" in service
    assert "OnCalendar={{ server_resident_reconciliation_on_calendar }}" in timer
    assert "RandomizedDelaySec={{ server_resident_reconciliation_randomized_delay_sec }}" in timer


def test_playbook_metadata_and_role_reference_are_present() -> None:
    playbook = (REPO_ROOT / "playbooks" / "server-resident-reconciliation.yml").read_text(encoding="utf-8")

    assert "# Purpose: Bootstrap and maintain the Proxmox host's server-resident ansible-pull reconcile loop." in playbook
    assert "server_resident_reconciliation_bootstrap_gitea_access" in playbook
    assert "lv3.platform.server_resident_reconciliation" in playbook
