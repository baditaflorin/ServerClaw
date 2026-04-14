from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
HOMEPAGE_PLAYBOOK = REPO_ROOT / "playbooks" / "homepage.yml"
UPTIME_KUMA_PLAYBOOK = REPO_ROOT / "playbooks" / "uptime-kuma.yml"
HOMEPAGE_SERVICE_PLAYBOOK = REPO_ROOT / "playbooks" / "services" / "homepage.yml"
UPTIME_KUMA_SERVICE_PLAYBOOK = REPO_ROOT / "playbooks" / "services" / "uptime-kuma.yml"


def test_homepage_playbook_targets_runtime_general_and_keeps_edge_publication() -> None:
    plays = yaml.safe_load(HOMEPAGE_PLAYBOOK.read_text())

    assert (
        plays[0]["hosts"]
        == "{{ 'docker-runtime-staging' if (env | default('production')) == 'staging' else 'runtime-general' }}"
    )
    assert plays[1]["hosts"] == "{{ 'nginx-staging' if (env | default('production')) == 'staging' else 'nginx' }}"
    preflight = next(task for task in plays[0]["pre_tasks"] if task["name"] == "Run shared preflight checks")
    assert preflight["vars"]["required_hosts"] == [
        "{{ playbook_execution_required_hosts.runtime_general[playbook_execution_env] }}"
    ]


def test_uptime_kuma_playbook_targets_runtime_general_and_keeps_edge_publication() -> None:
    plays = yaml.safe_load(UPTIME_KUMA_PLAYBOOK.read_text())

    assert (
        plays[1]["hosts"]
        == "{{ 'docker-runtime-staging' if (env | default('production')) == 'staging' else 'runtime-general' }}"
    )
    assert plays[2]["hosts"] == "{{ 'nginx-staging' if (env | default('production')) == 'staging' else 'nginx' }}"
    preflight = next(task for task in plays[1]["pre_tasks"] if task["name"] == "Run shared preflight checks")
    assert preflight["vars"]["required_hosts"] == [
        "{{ playbook_execution_required_hosts.runtime_general[playbook_execution_env] }}"
    ]


def test_runtime_general_service_wrappers_import_root_playbooks() -> None:
    assert yaml.safe_load(HOMEPAGE_SERVICE_PLAYBOOK.read_text()) == [{"import_playbook": "../homepage.yml"}]
    assert yaml.safe_load(UPTIME_KUMA_SERVICE_PLAYBOOK.read_text()) == [{"import_playbook": "../uptime-kuma.yml"}]
