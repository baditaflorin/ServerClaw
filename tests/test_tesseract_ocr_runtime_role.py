from pathlib import Path
import json

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "tesseract_ocr_runtime" / "tasks" / "main.yml"
ROLE_VERIFY = REPO_ROOT / "roles" / "tesseract_ocr_runtime" / "tasks" / "verify.yml"
ROLE_DEFAULTS = REPO_ROOT / "roles" / "tesseract_ocr_runtime" / "defaults" / "main.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "tesseract_ocr_runtime" / "templates" / "docker-compose.yml.j2"
DOCKERFILE_TEMPLATE = REPO_ROOT / "roles" / "tesseract_ocr_runtime" / "templates" / "Dockerfile.j2"
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "tesseract-ocr.yml"
COLLECTION_PLAYBOOK_PATH = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "tesseract-ocr.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "tesseract-ocr.yml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
ANSIBLE_EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_defaults_define_repo_built_tesseract_ocr_contract() -> None:
    defaults = load_yaml(ROLE_DEFAULTS)

    assert defaults["tesseract_ocr_runtime_site_dir"] == "/opt/tesseract-ocr"
    assert defaults["tesseract_ocr_runtime_service_dir"] == "{{ tesseract_ocr_runtime_site_dir }}/app"
    assert defaults["tesseract_ocr_runtime_container_name"] == "tesseract-ocr"
    assert defaults["tesseract_ocr_runtime_image_name"] == "lv3/tesseract-ocr"
    assert defaults["tesseract_ocr_runtime_base_image"] == "python:3.12-slim-bookworm"
    assert defaults["tesseract_ocr_runtime_container_port"] == 8000
    assert defaults["tesseract_ocr_runtime_port"] == "{{ tesseract_ocr_runtime_service_topology.ports.internal }}"
    assert defaults["tesseract_ocr_runtime_local_base_url"] == "http://127.0.0.1:{{ tesseract_ocr_runtime_port }}"
    assert defaults["tesseract_ocr_runtime_default_language"] == "eng"


def test_main_tasks_render_build_start_and_verify_tesseract_ocr() -> None:
    tasks = load_yaml(ROLE_TASKS)
    names = [task["name"] for task in tasks]

    assert "Render the Tesseract OCR compose file" in names
    assert "Render the Tesseract OCR Dockerfile" in names
    assert "Sync the Tesseract OCR service sources" in names
    assert "Build the Tesseract OCR image" in names
    assert "Start the Tesseract OCR runtime and recover Docker nat-chain or stale compose-network failures" in names
    assert "Verify the Tesseract OCR runtime" in names

    build_task = next(task for task in tasks if task["name"] == "Build the Tesseract OCR image")
    assert build_task["ansible.builtin.shell"].startswith("set -euo pipefail")


def test_verify_tasks_cover_health_and_deterministic_ocr_probe() -> None:
    tasks = load_yaml(ROLE_VERIFY)
    names = [task["name"] for task in tasks]

    assert "Verify the Tesseract OCR health endpoint responds locally" in names
    assert "Verify Tesseract OCR extracts text from the deterministic image fixture" in names
    probe_task = next(
        task for task in tasks if task["name"] == "Verify Tesseract OCR extracts text from the deterministic image fixture"
    )
    assert "{{ tesseract_ocr_runtime_local_base_url }}/ocr" in probe_task["ansible.builtin.shell"]
    assert 'payload.get("extraction_method") == "tesseract"' in probe_task["ansible.builtin.shell"]


def test_templates_define_repo_built_runtime_and_language_env() -> None:
    compose_template = COMPOSE_TEMPLATE.read_text(encoding="utf-8")
    dockerfile_template = DOCKERFILE_TEMPLATE.read_text(encoding="utf-8")

    assert "image: {{ tesseract_ocr_runtime_image_name }}:latest" in compose_template
    assert '"{{ tesseract_ocr_runtime_port }}:{{ tesseract_ocr_runtime_container_port }}"' in compose_template
    assert "TESSERACT_OCR_DEFAULT_LANGUAGE" in compose_template
    assert "FROM {{ tesseract_ocr_runtime_base_image }}" in dockerfile_template
    assert "tesseract-ocr" in dockerfile_template
    assert "poppler-utils" in dockerfile_template


def test_playbook_and_service_wrapper_import_the_tesseract_ocr_runtime() -> None:
    playbook = load_yaml(COLLECTION_PLAYBOOK_PATH)
    root_wrapper = load_yaml(PLAYBOOK_PATH)
    wrapper = load_yaml(SERVICE_WRAPPER_PATH)

    assert "docker-runtime-lv3" in playbook[0]["hosts"]
    roles = [role["role"] for role in playbook[0]["roles"]]
    assert roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.tesseract_ocr_runtime",
    ]
    assert root_wrapper == [{"import_playbook": "../collections/ansible_collections/lv3/platform/playbooks/tesseract-ocr.yml"}]
    assert wrapper == [{"import_playbook": "../tesseract-ocr.yml"}]


def test_inventory_opens_private_tesseract_ocr_access_to_host_guest_and_monitoring_callers() -> None:
    host_vars = load_yaml(HOST_VARS_PATH)

    assert host_vars["platform_port_assignments"]["tesseract_ocr_port"] == 3008
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime-lv3"]["allowed_inbound"]
    assert 3008 in next(rule for rule in docker_runtime_rules if rule["source"] == "host" and 3008 in rule["ports"])["ports"]
    assert 3008 in next(rule for rule in docker_runtime_rules if rule["source"] == "all_guests" and 3008 in rule["ports"])["ports"]
    assert 3008 in next(rule for rule in docker_runtime_rules if rule["source"] == "172.16.0.0/12" and 3008 in rule["ports"])["ports"]
    assert 3008 in next(rule for rule in docker_runtime_rules if rule["source"] == "monitoring-lv3" and 3008 in rule["ports"])["ports"]


def test_workflow_and_command_catalogs_declare_converge_tesseract_ocr_entrypoint() -> None:
    workflow_catalog = json.loads(WORKFLOW_CATALOG_PATH.read_text(encoding="utf-8"))
    command_catalog = json.loads(COMMAND_CATALOG_PATH.read_text(encoding="utf-8"))

    workflow = workflow_catalog["workflows"]["converge-tesseract-ocr"]
    command = command_catalog["commands"]["converge-tesseract-ocr"]

    assert workflow["preferred_entrypoint"] == {
        "kind": "make_target",
        "target": "converge-tesseract-ocr",
        "command": "make converge-tesseract-ocr",
    }
    assert "syntax-check-tesseract-ocr" in workflow["validation_targets"]
    assert workflow["owner_runbook"] == "docs/runbooks/configure-tesseract-ocr.md"
    assert command["workflow_id"] == "converge-tesseract-ocr"
    assert command["approval_policy"] == "sensitive_live_change"
    assert command["evidence"]["live_apply_receipt_required"] is True


def test_ansible_execution_scopes_register_tesseract_ocr_playbooks() -> None:
    scopes = load_yaml(ANSIBLE_EXECUTION_SCOPES_PATH)

    root_entry = scopes["playbooks"]["playbooks/tesseract-ocr.yml"]
    service_entry = scopes["playbooks"]["playbooks/services/tesseract-ocr.yml"]

    assert root_entry["playbook_id"] == "tesseract-ocr"
    assert root_entry["canonical_service_id"] == "tesseract_ocr"
    assert root_entry["mutation_scope"] == "host"
    assert service_entry["playbook_id"] == "tesseract-ocr"
    assert service_entry["canonical_service_id"] == "tesseract_ocr"
    assert service_entry["mutation_scope"] == "host"
