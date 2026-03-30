from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "livekit_runtime" / "defaults" / "main.yml"
ROLE_TASKS = REPO_ROOT / "roles" / "livekit_runtime" / "tasks" / "main.yml"
ROLE_VERIFY = REPO_ROOT / "roles" / "livekit_runtime" / "tasks" / "verify.yml"
ROLE_META = REPO_ROOT / "roles" / "livekit_runtime" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "livekit_runtime" / "templates" / "docker-compose.yml.j2"
CONFIG_TEMPLATE = REPO_ROOT / "roles" / "livekit_runtime" / "templates" / "livekit.yaml.j2"
CTMPL_TEMPLATE = REPO_ROOT / "roles" / "livekit_runtime" / "templates" / "livekit.env.ctmpl.j2"


def test_defaults_define_livekit_runtime_contract() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert defaults["livekit_service_topology"] == "{{ hostvars['proxmox_florin'].lv3_service_topology | service_topology_get('livekit') }}"
    assert defaults["livekit_image"] == "{{ container_image_catalog.images.livekit_runtime.ref }}"
    assert defaults["livekit_compose_file"] == "{{ livekit_site_dir }}/docker-compose.yml"
    assert defaults["livekit_config_file"] == "{{ livekit_site_dir }}/livekit.yaml"
    assert defaults["livekit_env_file"] == "{{ compose_runtime_secret_root }}/livekit/runtime.env"
    assert defaults["livekit_repo_root"] == "{{ inventory_dir | dirname }}"
    assert "rev-parse --path-format=absolute --git-common-dir" in defaults["livekit_shared_local_root"]
    assert defaults["livekit_local_artifact_dir"] == "{{ livekit_shared_local_root }}/livekit"
    assert defaults["livekit_api_key_local_file"] == "{{ livekit_local_artifact_dir }}/api-key.txt"
    assert defaults["livekit_api_secret_local_file"] == "{{ livekit_local_artifact_dir }}/api-secret.txt"
    assert defaults["livekit_helper_script_local_file"] == "{{ livekit_repo_root }}/scripts/livekit_tool.py"
    assert defaults["livekit_signal_port"] == "{{ platform_service_topology | platform_service_port('livekit', 'internal') }}"
    assert defaults["livekit_media_tcp_port"] == "{{ livekit_service_topology.ports.media_tcp }}"
    assert defaults["livekit_media_udp_port"] == "{{ livekit_service_topology.ports.media_udp }}"
    assert defaults["livekit_public_url"] == "https://{{ livekit_public_hostname }}"
    assert defaults["livekit_local_url"] == "http://127.0.0.1:{{ livekit_signal_port }}"


def test_argument_spec_requires_livekit_ports_and_credentials() -> None:
    specs = yaml.safe_load(ROLE_META.read_text())
    options = specs["argument_specs"]["main"]["options"]

    assert options["livekit_config_file"]["type"] == "path"
    assert options["livekit_api_key_local_file"]["type"] == "path"
    assert options["livekit_api_secret_local_file"]["type"] == "path"
    assert options["livekit_signal_port"]["type"] == "int"
    assert options["livekit_media_tcp_port"]["type"] == "int"
    assert options["livekit_media_udp_port"]["type"] == "int"
    assert options["livekit_remote_helper_script"]["type"] == "path"


def test_main_tasks_generate_keys_render_openbao_stack_and_verify_runtime() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text())
    names = [task["name"] for task in tasks]

    assert "Generate the LiveKit API key pair when it is missing locally" in names
    assert "Prepare OpenBao agent runtime secret injection for LiveKit" in names
    assert "Install the LiveKit verification helper on the runtime host" in names
    assert "Render the LiveKit compose file" in names
    assert "Start the LiveKit OpenBao agent" in names
    assert "Wait for the LiveKit runtime env file" in names
    assert "Converge the LiveKit runtime stack" in names
    assert "Wait for the LiveKit UDP media listener" in names
    assert "Verify the LiveKit runtime" in names

    generate_task = next(task for task in tasks if task["name"] == "Generate the LiveKit API key pair when it is missing locally")
    assert "docker run --rm {{ livekit_image | quote }} generate-keys" in generate_task["ansible.builtin.shell"]
    secret_payload_task = next(task for task in tasks if task["name"] == "Record the LiveKit runtime secrets")
    runtime_payload = secret_payload_task["ansible.builtin.set_fact"]["livekit_runtime_secret_payload"]
    assert runtime_payload["LIVEKIT_API_KEY"] == "{{ lookup('ansible.builtin.file', livekit_api_key_local_file) | trim }}"
    assert runtime_payload["LIVEKIT_API_SECRET"] == "{{ lookup('ansible.builtin.file', livekit_api_secret_local_file) | trim }}"
    openbao_task = next(task for task in tasks if task["name"] == "Prepare OpenBao agent runtime secret injection for LiveKit")
    assert openbao_task["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert openbao_task["ansible.builtin.include_role"]["tasks_from"] == "openbao_compose_env"
    agent_task = next(task for task in tasks if task["name"] == "Start the LiveKit OpenBao agent")
    assert agent_task["ansible.builtin.command"]["argv"][-3:] == ["up", "-d", "openbao-agent"]
    env_wait_task = next(task for task in tasks if task["name"] == "Wait for the LiveKit runtime env file")
    assert 'grep -Eq \'^LIVEKIT_KEYS=.+:.+$\'' in env_wait_task["ansible.builtin.shell"]
    up_task = next(task for task in tasks if task["name"] == "Converge the LiveKit runtime stack")
    assert up_task["ansible.builtin.command"]["argv"][-3:] == ["-d", "--remove-orphans", "livekit"]
    verify_task = next(task for task in tasks if task["name"] == "Verify the LiveKit runtime")
    assert verify_task["ansible.builtin.import_tasks"] == "verify.yml"


def test_verify_tasks_probe_signal_media_and_room_lifecycle() -> None:
    tasks = yaml.safe_load(ROLE_VERIFY.read_text())
    names = [task["name"] for task in tasks]

    assert "Verify the LiveKit signal listener is reachable locally" in names
    assert "Verify the LiveKit TCP media listener is reachable locally" in names
    assert "Verify the LiveKit UDP media listener is present locally" in names
    assert "Verify the LiveKit room lifecycle locally" in names
    lifecycle_task = next(task for task in tasks if task["name"] == "Verify the LiveKit room lifecycle locally")
    assert lifecycle_task["ansible.builtin.command"]["argv"][:3] == ["python3", "{{ livekit_remote_helper_script }}", "verify-room-lifecycle"]
    assert "--runtime-env-file" in lifecycle_task["ansible.builtin.command"]["argv"]
    assert lifecycle_task["until"] == (
        "livekit_verify_room_lifecycle.rc == 0 and "
        "(livekit_verify_room_lifecycle.stdout | length > 0) and "
        "((livekit_verify_room_lifecycle.stdout | from_json).verification_passed)"
    )


def test_templates_use_host_network_and_livekit_ports() -> None:
    compose_template = COMPOSE_TEMPLATE.read_text()
    config_template = CONFIG_TEMPLATE.read_text()
    ctmpl_template = CTMPL_TEMPLATE.read_text()

    assert "network_mode: host" in compose_template
    assert "container_name: {{ livekit_container_name }}" in compose_template
    assert "      - {{ livekit_env_file }}" in compose_template
    assert "      - /etc/livekit/livekit.yaml" in compose_template
    assert "port: {{ livekit_signal_port }}" in config_template
    assert "tcp_port: {{ livekit_media_tcp_port }}" in config_template
    assert "udp_port: {{ livekit_media_udp_port }}" in config_template
    assert "use_external_ip: {{ 'true' if livekit_use_external_ip | bool else 'false' }}" in config_template
    assert '[[ with secret "kv/data/{{ livekit_openbao_secret_path }}" ]]' in ctmpl_template
