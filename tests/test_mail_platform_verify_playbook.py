from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_PLAYBOOK = REPO_ROOT / "playbooks" / "mail-platform-verify.yml"
COLLECTION_PLAYBOOK = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "mail-platform-verify.yml"
)


def test_root_playbook_imports_collection_verify_playbook() -> None:
    assert yaml.safe_load(ROOT_PLAYBOOK.read_text()) == [
        {"import_playbook": "../collections/ansible_collections/lv3/platform/playbooks/mail-platform-verify.yml"}
    ]


def test_collection_playbook_keeps_environment_aware_runtime_targeting() -> None:
    plays = yaml.safe_load(COLLECTION_PLAYBOOK.read_text())

    prepare_play = plays[1]
    send_play = plays[2]
    verify_play = plays[3]

    assert (
        prepare_play["hosts"]
        == "{{ 'docker-runtime' if (env | default('production')) == 'staging' else 'runtime-control' }}"
    )
    assert send_play["hosts"] == "{{ 'monitoring' if (env | default('production')) == 'staging' else 'monitoring' }}"
    assert (
        verify_play["hosts"]
        == "{{ 'docker-runtime' if (env | default('production')) == 'staging' else 'runtime-control' }}"
    )


def test_collection_playbook_adds_staging_mailpit_probe_flow() -> None:
    plays = yaml.safe_load(COLLECTION_PLAYBOOK.read_text())
    prepare_tasks = plays[1]["tasks"]
    send_tasks = plays[2]["tasks"]
    verify_tasks = plays[3]["tasks"]

    clear_task = next(
        task
        for task in prepare_tasks
        if task["name"] == "Clear any previous Mailpit messages before the staging SMTP probe"
    )
    assert "mailpit_http_port" in clear_task["ansible.builtin.uri"]["url"]
    assert clear_task["when"] == "playbook_execution_env == 'staging'"

    send_task = next(task for task in send_tasks if task["name"] == "Send a staging SMTP probe to Mailpit")
    assert "mailpit-staging@example.com" in send_task["ansible.builtin.shell"]
    assert "mailpit_smtp_port" in send_task["ansible.builtin.shell"]
    assert send_task["when"] == "playbook_execution_env == 'staging'"

    read_task = next(task for task in verify_tasks if task["name"] == "Read the captured staging Mailpit messages")
    assert "mailpit_http_port" in read_task["ansible.builtin.uri"]["url"]

    assert_task = next(
        task for task in verify_tasks if task["name"] == "Assert the staging SMTP probe was captured by Mailpit"
    )
    assert (
        "hostvars[playbook_execution_host_patterns.monitoring[playbook_execution_env]].mailpit_staging_probe.stdout == 'sent'"
        in assert_task["ansible.builtin.assert"]["that"]
    )
    assert "'mailpit-staging@example.com'" in str(assert_task["ansible.builtin.assert"]["that"])
