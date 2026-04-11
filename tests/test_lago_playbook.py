import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "lago.yml"
ROOT_PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "lago.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "lago.yml"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
ANSIBLE_EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"


def test_lago_playbook_converges_dns_postgres_runtime_edge_and_public_verify() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())

    dns_play = plays[0]
    postgres_play = next(play for play in plays if play["name"] == "Prepare PostgreSQL for Lago")
    runtime_play = next(
        play
        for play in plays
        if play["name"] == "Converge Lago and the billing ingest adapter on the Docker runtime VM"
    )
    nginx_play = next(play for play in plays if play["name"] == "Publish Lago through the NGINX edge")
    verify_play = next(play for play in plays if play["name"] == "Verify Lago end to end after edge publication")

    assert dns_play["hosts"] == "localhost"
    assert dns_play["connection"] == "local"
    assert dns_play["vars"]["subdomain_fqdn"] == "billing.lv3.org"

    assert postgres_play["roles"] == [
        {"role": "lv3.platform.linux_guest_firewall"},
        {"role": "lv3.platform.postgres_vm"},
        {"role": "lv3.platform.lago_postgres"},
    ]
    assert runtime_play["roles"] == [
        {"role": "lv3.platform.docker_runtime"},
        {"role": "lv3.platform.linux_guest_firewall"},
        {"role": "lv3.platform.lago_runtime"},
        {"role": "lv3.platform.api_gateway_runtime"},
    ]
    assert nginx_play["roles"] == [{"role": "lv3.platform.nginx_edge_publication"}]
    assert verify_play["vars_files"] == ["{{ playbook_dir }}/../../../../../inventory/group_vars/platform.yml"]
    assert verify_play["vars"]["lago_public_base_url"] == "{{ platform_service_topology.lago.urls.public }}"
    assert verify_play["vars"]["lago_public_ingest_url"] == "{{ lago_public_base_url }}/api/v1/events"
    assert verify_play["vars"]["lago_api_local_base_url"] == "{{ platform_service_topology.lago.urls.api }}"
    assert verify_play["vars"]["lago_direct_api_local_base_url"] == (
        "http://127.0.0.1:{{ platform_service_topology.lago.ports.api }}"
    )
    assert verify_play["vars"]["lago_org_api_key_local_file"].endswith("/.local/lago/org-api-key.txt")
    assert verify_play["vars"]["lago_smoke_producer_token_local_file"].endswith("/.local/lago/smoke-producer-token.txt")

    public_smoke_task = next(
        task
        for task in verify_play["tasks"]
        if task["name"] == "Submit a public Lago smoke event through the API gateway adapter"
    )
    usage_task = next(
        task
        for task in verify_play["tasks"]
        if task["name"] == "Verify Lago current usage reflects the public smoke event"
    )

    assert public_smoke_task["ansible.builtin.uri"]["url"] == "{{ lago_public_ingest_url }}"
    assert public_smoke_task["retries"] == 48
    assert public_smoke_task["delay"] == 5
    assert public_smoke_task["until"] == "lago_public_smoke_event.status == 200"
    assert (
        "{{ lago_direct_api_local_base_url }}/api/v1/customers/{{ lago_smoke_external_customer_id }}/current_usage"
        in usage_task["ansible.builtin.uri"]["url"]
    )
    assert (
        "?external_subscription_id={{ lago_smoke_external_subscription_id | urlencode }}"
        in usage_task["ansible.builtin.uri"]["url"]
    )


def test_root_lago_playbook_imports_the_collection_entrypoint() -> None:
    wrapper = yaml.safe_load(ROOT_PLAYBOOK_PATH.read_text())
    assert wrapper == [{"import_playbook": "../collections/ansible_collections/lv3/platform/playbooks/lago.yml"}]


def test_service_wrapper_imports_the_root_lago_playbook() -> None:
    wrapper = yaml.safe_load(SERVICE_WRAPPER_PATH.read_text())
    assert wrapper == [{"import_playbook": "../lago.yml"}]


def test_workflow_and_command_catalogs_declare_converge_lago_entrypoint() -> None:
    workflow_catalog = json.loads(WORKFLOW_CATALOG_PATH.read_text())
    command_catalog = json.loads(COMMAND_CATALOG_PATH.read_text())

    workflow = workflow_catalog["workflows"]["converge-lago"]
    command = command_catalog["commands"]["converge-lago"]

    assert workflow["preferred_entrypoint"] == {
        "kind": "make_target",
        "target": "converge-lago",
        "command": "HETZNER_DNS_API_TOKEN=... make converge-lago",
    }
    assert "syntax-check-lago" in workflow["validation_targets"]
    assert workflow["owner_runbook"] == "docs/runbooks/configure-lago.md"
    assert command["workflow_id"] == "converge-lago"
    assert command["approval_policy"] == "sensitive_live_change"
    assert command["evidence"]["live_apply_receipt_required"] is True


def test_ansible_execution_scopes_register_the_direct_lago_playbook() -> None:
    scopes = yaml.safe_load(ANSIBLE_EXECUTION_SCOPES_PATH.read_text())
    entry = scopes["playbooks"]["playbooks/lago.yml"]

    assert entry["playbook_id"] == "lago"
    assert entry["mutation_scope"] == "platform"
    assert "service:lago" in entry["shared_surfaces"]
