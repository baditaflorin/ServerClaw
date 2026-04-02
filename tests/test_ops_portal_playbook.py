from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "ops-portal.yml"
ROLE_TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "ops_portal_runtime"
    / "tasks"
)


def test_ops_portal_playbook_uses_controller_pwd_as_repo_root() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    play = plays[0]

    assert play["vars"]["ops_portal_repo_root"] == "{{ lookup('ansible.builtin.env', 'PWD') }}"


def test_ops_portal_runtime_clears_previous_build_context_before_sync() -> None:
    tasks = yaml.safe_load((ROLE_TASKS_PATH / "main.yml").read_text())
    cleanup_task = next(task for task in tasks if task["name"] == "Remove stale ops portal service sources before sync")

    assert cleanup_task["ansible.builtin.file"]["state"] == "absent"
    assert cleanup_task["loop"] == [
        "{{ ops_portal_service_dir }}/ops_portal",
        "{{ ops_portal_service_dir }}/search_fabric",
        "{{ ops_portal_service_dir }}/publication_contract.py",
        "{{ ops_portal_service_dir }}/stage_smoke.py",
        "{{ ops_portal_service_dir }}/requirements.txt",
    ]


def test_ops_portal_runtime_removes_macos_metadata_sidecars_after_sync() -> None:
    tasks = yaml.safe_load((ROLE_TASKS_PATH / "main.yml").read_text())
    discover_task = next(
        task for task in tasks if task["name"] == "Discover macOS metadata sidecars in synced ops portal sources"
    )
    cleanup_task = next(
        task for task in tasks if task["name"] == "Remove macOS metadata sidecars from synced ops portal sources"
    )

    assert discover_task["ansible.builtin.find"]["paths"] == "{{ ops_portal_service_dir }}"
    assert discover_task["ansible.builtin.find"]["patterns"] == "._*"
    assert discover_task["ansible.builtin.find"]["recurse"] is True

    assert cleanup_task["ansible.builtin.file"]["state"] == "absent"
    assert cleanup_task["loop"] == "{{ ops_portal_metadata_sidecars.files }}"
    assert cleanup_task["when"] == "ops_portal_metadata_sidecars.matched | int > 0"


def test_ops_portal_runtime_retries_local_health_and_root_checks() -> None:
    tasks = yaml.safe_load((ROLE_TASKS_PATH / "verify.yml").read_text())
    health_task = next(task for task in tasks if task["name"] == "Verify the ops portal health endpoint responds locally")
    root_task = next(task for task in tasks if task["name"] == "Verify the ops portal root page renders locally")
    root_assert = next(
        task for task in tasks if task["name"] == "Assert the contextual help drawer is present on the ops portal root page"
    )

    assert health_task["retries"] == 20
    assert health_task["delay"] == 3
    assert health_task["until"] == "ops_portal_verify_health.status == 200"

    assert root_task["retries"] == 20
    assert root_task["delay"] == 3
    assert root_task["until"] == "ops_portal_verify_root.status == 200"
    assert root_task["ansible.builtin.uri"]["return_content"] is True
    assert "'Contextual Help' in ops_portal_verify_root.content" in root_assert["ansible.builtin.assert"]["that"]


def test_ops_portal_runtime_syncs_activation_catalog_and_partial() -> None:
    defaults = (ROLE_TASKS_PATH.parent / "defaults" / "main.yml").read_text()
    verify = (ROLE_TASKS_PATH / "verify.yml").read_text()

    assert "config/activation-checklist.json" in defaults
    assert "scripts/ops_portal/templates/partials/activation.html" in defaults
    assert "Verify the activation checklist partial renders locally" in verify
