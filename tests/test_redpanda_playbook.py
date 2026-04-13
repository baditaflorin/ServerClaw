from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
COLLECTION_PLAYBOOK = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "redpanda.yml"
)
ROOT_PLAYBOOK = REPO_ROOT / "playbooks" / "redpanda.yml"
SERVICE_PLAYBOOK = REPO_ROOT / "playbooks" / "services" / "redpanda.yml"


def test_root_playbook_targets_runtime_host_and_roles() -> None:
    plays = yaml.safe_load(ROOT_PLAYBOOK.read_text())
    play = plays[0]

    assert (
        play["hosts"]
        == "{{ 'docker-runtime-staging' if (env | default('production')) == 'staging' else 'docker-runtime' }}"
    )
    assert play["roles"] == [
        {"role": "lv3.platform.linux_guest_firewall"},
        {"role": "lv3.platform.docker_runtime"},
        {"role": "lv3.platform.redpanda_runtime"},
    ]

    preflight = next(task for task in play["pre_tasks"] if task["name"] == "Run shared preflight checks")
    assert preflight["vars"]["playbook_execution_audit_target"] == "redpanda"

    post_verify = next(task for task in play["post_tasks"] if task["name"] == "Run shared post-verify checks")
    assert post_verify["vars"]["service_health_probe_id"] == "redpanda"


def test_collection_and_service_wrappers_import_redpanda_playbooks() -> None:
    collection = yaml.safe_load(COLLECTION_PLAYBOOK.read_text())
    service = yaml.safe_load(SERVICE_PLAYBOOK.read_text())

    assert collection == [{"import_playbook": "../../../../../playbooks/redpanda.yml"}]
    assert service == [{"import_playbook": "../redpanda.yml"}]


def test_host_network_policy_allows_private_redpanda_ports() -> None:
    host_vars = yaml.safe_load((REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml").read_text())
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime"]["allowed_inbound"]

    management_rule = next(
        rule for rule in docker_runtime_rules if rule["source"] == "management" and 9092 in rule["ports"]
    )
    guest_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "all_guests" and 9092 in rule["ports"])

    assert 9644 in management_rule["ports"]
    assert 8103 in management_rule["ports"]
    assert 8104 in management_rule["ports"]
    assert 8103 in guest_rule["ports"]
    assert 8104 in guest_rule["ports"]
