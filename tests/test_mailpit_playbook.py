from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
COLLECTION_PLAYBOOK = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "playbooks"
    / "mailpit.yml"
)
ROOT_PLAYBOOK = REPO_ROOT / "playbooks" / "mailpit.yml"
SERVICE_PLAYBOOK = REPO_ROOT / "playbooks" / "services" / "mailpit.yml"


def test_collection_playbook_targets_runtime_host_and_roles() -> None:
    plays = yaml.safe_load(COLLECTION_PLAYBOOK.read_text())
    play = plays[0]

    assert play["hosts"] == "{{ 'docker-runtime-staging-lv3' if (env | default('production')) == 'staging' else 'docker-runtime-lv3' }}"
    assert play["roles"] == [
        {"role": "lv3.platform.linux_guest_firewall"},
        {"role": "lv3.platform.docker_runtime"},
        {"role": "lv3.platform.mailpit_runtime"},
    ]

    preflight = next(task for task in play["pre_tasks"] if task["name"] == "Run shared preflight checks")
    assert preflight["vars"]["playbook_execution_audit_target"] == "mailpit"

    post_verify = next(task for task in play["post_tasks"] if task["name"] == "Run shared post-verify checks")
    assert post_verify["vars"]["service_health_probe_id"] == "mailpit"


def test_root_and_service_wrappers_import_mailpit_playbooks() -> None:
    root = yaml.safe_load(ROOT_PLAYBOOK.read_text())
    service = yaml.safe_load(SERVICE_PLAYBOOK.read_text())

    assert root == [{"import_playbook": "../collections/ansible_collections/lv3/platform/playbooks/mailpit.yml"}]
    assert service == [{"import_playbook": "../mailpit.yml"}]
