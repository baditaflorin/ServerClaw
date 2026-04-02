from pathlib import Path

import json
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "nats_jetstream_runtime" / "tasks" / "main.yml"
ROLE_DEFAULTS = REPO_ROOT / "roles" / "nats_jetstream_runtime" / "defaults" / "main.yml"
ROLE_META = REPO_ROOT / "roles" / "nats_jetstream_runtime" / "meta" / "argument_specs.yml"
ROLE_TEMPLATE = REPO_ROOT / "roles" / "nats_jetstream_runtime" / "templates" / "nats-server.conf.j2"
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "nats-jetstream.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "nats-jetstream.yml"
SECRET_MANIFEST_PATH = REPO_ROOT / "config" / "controller-local-secrets.json"
ANSIBLE_EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_defaults_define_expected_runtime_and_preserved_principals() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert defaults["nats_jetstream_site_dir"] == "/opt/nats-jetstream"
    assert defaults["nats_jetstream_container_name"] == "lv3-nats-jetstream"
    assert defaults["nats_jetstream_port"] == 4222
    assert defaults["nats_jetstream_monitor_port"] == 8222
    assert defaults["nats_jetstream_publish_allow"] == ["$JS.API.>", "platform.>", "rag.document.>", "secret.rotation.>"]

    principals = {entry["user"]: entry for entry in defaults["nats_jetstream_additional_users"]}
    assert set(principals) == {
        "control-plane-publisher",
        "workflow-consumer",
        "alert-consumer",
        "receipt-consumer",
        "agent-consumer",
    }
    assert principals["control-plane-publisher"]["publish_allow"] == ["lv3.>"]
    assert principals["workflow-consumer"]["allow_responses"] is True


def test_argument_spec_accepts_additional_user_catalog() -> None:
    specs = yaml.safe_load(ROLE_META.read_text())
    options = specs["argument_specs"]["main"]["options"]

    assert options["nats_jetstream_additional_users"]["type"] == "list"
    assert options["nats_jetstream_additional_users"]["elements"] == "dict"
    nested = options["nats_jetstream_additional_users"]["options"]
    assert nested["user"]["type"] == "str"
    assert nested["password_local_file"]["type"] == "path"
    assert nested["publish_allow"]["elements"] == "str"
    assert nested["allow_responses"]["type"] == "bool"


def test_main_tasks_read_additional_passwords_and_build_principal_list() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text())
    names = [task["name"] for task in tasks]

    assert "Read the controller-local NATS additional user passwords" in names
    assert "Seed the resolved NATS principal list with the admin principal" in names
    assert "Append the additional NATS principals" in names
    append_task = next(task for task in tasks if task["name"] == "Append the additional NATS principals")
    assert "nats_jetstream_users_resolved" in append_task["ansible.builtin.set_fact"]


def test_template_renders_resolved_principals_and_allow_responses() -> None:
    template = ROLE_TEMPLATE.read_text()

    assert "{% for principal in nats_jetstream_users_resolved %}" in template
    assert 'user: "{{ principal.user }}"' in template
    assert 'password: "{{ principal.password }}"' in template
    assert "principal.allow_responses" in template


def test_playbook_and_service_wrapper_point_to_runtime_role() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)
    wrapper = load_yaml(SERVICE_WRAPPER_PATH)

    assert [role["role"] for role in playbook[0]["roles"]] == [
        "lv3.platform.docker_runtime",
        "lv3.platform.nats_jetstream_runtime",
        "lv3.platform.linux_guest_firewall",
    ]
    assert wrapper == [{"import_playbook": "../nats-jetstream.yml"}]


def test_inventory_allows_monitoring_relay_access_to_the_nats_client_listener() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text())
    runtime_control_rules = host_vars["network_policy"]["guests"]["runtime-control-lv3"]["allowed_inbound"]

    monitoring_rule = next(
        rule for rule in runtime_control_rules if rule["source"] == "monitoring-lv3" and 4222 in rule["ports"]
    )
    assert 4222 in monitoring_rule["ports"]


def test_secret_manifest_and_execution_scopes_register_nats_runtime_inputs() -> None:
    manifest = json.loads(SECRET_MANIFEST_PATH.read_text())
    secrets = manifest["secrets"]

    assert "nats_jetstream_admin_password" in secrets
    assert "nats_jetstream_control_plane_publisher_password" in secrets
    assert "nats_jetstream_workflow_consumer_password" in secrets
    assert "nats_jetstream_alert_consumer_password" in secrets
    assert "nats_jetstream_receipt_consumer_password" in secrets
    assert "nats_jetstream_agent_consumer_password" in secrets

    scopes = yaml.safe_load(ANSIBLE_EXECUTION_SCOPES_PATH.read_text())
    entry = scopes["playbooks"]["playbooks/nats-jetstream.yml"]
    assert entry["playbook_id"] == "nats-jetstream"
    assert entry["canonical_service_id"] == "nats_jetstream"
