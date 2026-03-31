from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_PLAYBOOK = REPO_ROOT / "playbooks" / "woodpecker.yml"
SERVICE_PLAYBOOK = REPO_ROOT / "playbooks" / "services" / "woodpecker.yml"
COLLECTION_PLAYBOOK = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "playbooks"
    / "woodpecker.yml"
)


def test_woodpecker_root_playbook_converges_proxy_postgres_runtime_and_edge() -> None:
    plays = yaml.safe_load(ROOT_PLAYBOOK.read_text())

    assert plays[0]["roles"][0]["role"] == "lv3.platform.proxmox_tailscale_proxy"
    assert plays[2]["roles"] == [
        {"role": "lv3.platform.linux_guest_firewall"},
        {"role": "lv3.platform.postgres_vm"},
        {"role": "lv3.platform.woodpecker_postgres"},
    ]
    assert plays[3]["roles"] == [
        {"role": "lv3.platform.linux_guest_firewall"},
        {"role": "lv3.platform.docker_runtime"},
        {"role": "lv3.platform.woodpecker_runtime"},
    ]
    verify = next(task for task in plays[3]["post_tasks"] if task["name"] == "Verify Woodpecker health probes")
    post_verify = next(task for task in plays[3]["post_tasks"] if task["name"] == "Run shared post-verify checks")
    assert verify["ansible.builtin.include_role"]["name"] == "lv3.platform.woodpecker_runtime"
    assert post_verify["vars"]["playbook_execution_verify_readiness"] is False
    assert plays[4]["roles"] == [{"role": "lv3.platform.nginx_edge_publication"}]


def test_woodpecker_root_playbook_bootstraps_controller_artifacts_and_seed_repo() -> None:
    plays = yaml.safe_load(ROOT_PLAYBOOK.read_text())
    bootstrap_play = plays[5]
    public_health_task = next(task for task in bootstrap_play["tasks"] if task["name"] == "Wait for the public Woodpecker health endpoint to answer")

    assert bootstrap_play["vars"]["woodpecker_seed_repo_full_name"] == "ops/proxmox_florin_server"
    assert public_health_task["ansible.builtin.uri"]["status_code"] == [200, 204]
    assert public_health_task["until"] == "woodpecker_public_health.status in [200, 204]"
    task_argvs = [task["ansible.builtin.command"]["argv"] for task in bootstrap_play["tasks"] if "ansible.builtin.command" in task]

    assert any("scripts/woodpecker_bootstrap.py" in " ".join(argv) for argv in task_argvs)
    assert any("scripts/woodpecker_tool.py" in " ".join(argv) for argv in task_argvs)


def test_woodpecker_service_and_collection_wrappers_import_root_playbook() -> None:
    service = yaml.safe_load(SERVICE_PLAYBOOK.read_text())
    collection = yaml.safe_load(COLLECTION_PLAYBOOK.read_text())

    assert service == [{"import_playbook": "../woodpecker.yml"}]
    assert collection == [{"import_playbook": "../../../../../playbooks/woodpecker.yml"}]
