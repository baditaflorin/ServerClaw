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
    / "fleet_runner_image_publisher_identity"
)
COLLECTION_PLAYBOOK = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "playbooks"
    / "fleet-runner-image-publisher.yml"
)
ROOT_PLAYBOOK = REPO_ROOT / "playbooks" / "fleet-runner-image-publisher.yml"
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "fleet-runner-image-publisher.md"


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_publisher_identity_defaults_are_closed_to_builder_lxc_108() -> None:
    defaults = load_yaml(ROLE_ROOT / "defaults" / "main.yml")

    assert defaults == {
        "fleet_runner_image_publisher_target_host": "0docker_builder",
        "fleet_runner_image_publisher_config_dir": "/etc/fleet-runner",
        "fleet_runner_image_publisher_config_file": "/etc/fleet-runner/image-publisher.json",
        "fleet_runner_image_publisher_identity": "builder-lxc-108",
        "fleet_runner_image_publisher_version": 1,
        "fleet_runner_image_publisher_config_dir_mode": "0700",
        "fleet_runner_image_publisher_config_file_mode": "0600",
    }


def test_publisher_identity_role_rejects_retargeting_before_writing() -> None:
    tasks = load_yaml(ROLE_ROOT / "tasks" / "main.yml")
    names = [task["name"] for task in tasks]
    guard = tasks[0]["ansible.builtin.assert"]

    assert names[0] == "Reject image publisher identity convergence on any host except the designated 0docker builder"
    assert names.index(
        "Reject image publisher identity convergence on any host except the designated 0docker builder"
    ) < names.index("Ensure the root-only image publisher configuration parent exists")
    assert names.index("Refuse a non-directory or symlink image publisher configuration parent") < names.index(
        "Ensure the root-only image publisher configuration parent exists"
    )
    assert names.index("Require the managed root-only image publisher configuration parent") < names.index(
        "Write the fixed root-only image publisher identity contract"
    )
    assert names.index("Refuse a symlink image publisher identity contract") < names.index(
        "Write the fixed root-only image publisher identity contract"
    )
    assert "inventory_hostname == '0docker_builder'" in guard["that"]
    assert "fleet_runner_image_publisher_identity == 'builder-lxc-108'" in guard["that"]
    assert "fleet_runner_image_publisher_config_dir_mode == '0700'" in guard["that"]
    assert "fleet_runner_image_publisher_config_file_mode == '0600'" in guard["that"]


def test_publisher_identity_role_writes_exact_root_only_contract() -> None:
    tasks = load_yaml(ROLE_ROOT / "tasks" / "main.yml")
    directory_task = next(
        task for task in tasks if task["name"] == "Ensure the root-only image publisher configuration parent exists"
    )["ansible.builtin.file"]
    copy_task = next(
        task for task in tasks if task["name"] == "Write the fixed root-only image publisher identity contract"
    )["ansible.builtin.copy"]
    final_assert = next(
        task for task in tasks if task["name"] == "Require root-only image publisher identity permissions"
    )["ansible.builtin.assert"]
    parent_assert = next(
        task for task in tasks if task["name"] == "Require the managed root-only image publisher configuration parent"
    )["ansible.builtin.assert"]

    assert directory_task == {
        "path": "{{ fleet_runner_image_publisher_config_dir }}",
        "state": "directory",
        "owner": "root",
        "group": "root",
        "mode": "{{ fleet_runner_image_publisher_config_dir_mode }}",
    }
    assert copy_task == {
        "dest": "{{ fleet_runner_image_publisher_config_file }}",
        "content": '{"version":1,"identity":"builder-lxc-108"}',
        "owner": "root",
        "group": "root",
        "mode": "{{ fleet_runner_image_publisher_config_file_mode }}",
    }
    assert "fleet_runner_image_publisher_config_file_after.stat.isreg" in final_assert["that"]
    assert "not (fleet_runner_image_publisher_config_file_after.stat.islnk | default(false))" in final_assert["that"]
    assert "fleet_runner_image_publisher_config_file_after.stat.mode == '0600'" in final_assert["that"]
    assert "fleet_runner_image_publisher_config_dir_after.stat.pw_name == 'root'" in parent_assert["that"]
    assert "fleet_runner_image_publisher_config_dir_after.stat.gr_name == 'root'" in parent_assert["that"]
    assert "fleet_runner_image_publisher_config_dir_after.stat.mode == '0700'" in parent_assert["that"]


def test_controlled_playbook_targets_only_the_designated_builder() -> None:
    playbook = load_yaml(COLLECTION_PLAYBOOK)

    assert len(playbook) == 1
    assert playbook[0]["hosts"] == "0docker_builder"
    assert playbook[0]["become"] is True
    assert playbook[0]["roles"] == [{"role": "lv3.platform.fleet_runner_image_publisher_identity"}]
    assert (
        ROOT_PLAYBOOK.read_text(encoding="utf-8")
        .rstrip()
        .endswith(
            "- import_playbook: ../collections/ansible_collections/lv3/platform/playbooks/fleet-runner-image-publisher.yml"
        )
    )


def test_runbook_documents_non_secret_identity_and_verification() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")

    assert "no\ncredential" in runbook
    assert "`0docker_builder`" in runbook
    assert "`builder-lxc-108`" in runbook
    assert "`root:root` mode `0600`" in runbook
    assert '{"version":1,"identity":"builder-lxc-108"}' in runbook
