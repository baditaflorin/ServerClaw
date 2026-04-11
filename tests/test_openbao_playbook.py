from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "openbao.yml"


def test_openbao_postgres_dynamic_credential_verification_skips_become_on_delegated_uri_calls() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text(encoding="utf-8"))
    verify_play = next(play for play in plays if play.get("name") == "Verify PostgreSQL dynamic credentials end to end")
    login_task = next(
        task for task in verify_play["tasks"] if task.get("name") == "Login to OpenBao as the controller AppRole"
    )
    credential_task = next(
        task for task in verify_play["tasks"] if task.get("name") == "Request a PostgreSQL dynamic credential"
    )
    atlas_login_task = next(
        task for task in verify_play["tasks"] if task.get("name") == "Login to OpenBao as the Atlas AppRole"
    )
    atlas_credential_task = next(
        task
        for task in verify_play["tasks"]
        if task.get("name") == "Request an Atlas PostgreSQL schema-inspection credential"
    )

    assert login_task["delegate_to"] == "{{ playbook_execution_host_patterns.runtime_control[playbook_execution_env] }}"
    assert login_task["become"] is False
    assert (
        credential_task["delegate_to"]
        == "{{ playbook_execution_host_patterns.runtime_control[playbook_execution_env] }}"
    )
    assert credential_task["become"] is False
    assert (
        atlas_login_task["delegate_to"]
        == "{{ playbook_execution_host_patterns.runtime_control[playbook_execution_env] }}"
    )
    assert atlas_login_task["become"] is False
    assert (
        atlas_credential_task["delegate_to"]
        == "{{ playbook_execution_host_patterns.runtime_control[playbook_execution_env] }}"
    )
    assert atlas_credential_task["become"] is False


def test_openbao_playbook_reestablishes_unsealed_state_before_postgres_end_to_end_verification() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text(encoding="utf-8"))
    unseal_play = next(
        play
        for play in plays
        if play.get("name") == "Ensure OpenBao remains unsealed before PostgreSQL end-to-end verification"
    )
    ensure_task = next(
        task
        for task in unseal_play["tasks"]
        if task.get("name") == "Ensure OpenBao remains unsealed before PostgreSQL end-to-end verification"
    )

    assert (
        unseal_play["hosts"]
        == "{{ 'docker-runtime' if (env | default('production')) == 'staging' else 'runtime-control' }}"
    )
    assert ensure_task["ansible.builtin.include_role"]["name"] == "lv3.platform.openbao_runtime"
    assert ensure_task["ansible.builtin.include_role"]["tasks_from"] == "ensure_unsealed.yml"
