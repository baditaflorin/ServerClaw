from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "netdata_runtime" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "netdata_runtime" / "tasks" / "main.yml"
VERIFY_PATH = REPO_ROOT / "roles" / "netdata_runtime" / "tasks" / "verify.yml"
NETDATA_TEMPLATE_PATH = REPO_ROOT / "roles" / "netdata_runtime" / "templates" / "netdata.conf.j2"
STREAM_TEMPLATE_PATH = REPO_ROOT / "roles" / "netdata_runtime" / "templates" / "stream.conf.j2"


def load_tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())


def test_defaults_define_parent_and_child_inventory_shape() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())

    assert defaults["netdata_runtime_parent_inventory_host"] == "monitoring-lv3"
    assert defaults["netdata_runtime_child_inventory_hosts"] == [
        "proxmox_florin",
        "nginx-lv3",
        "docker-runtime-lv3",
        "postgres-lv3",
    ]
    assert defaults["netdata_runtime_parent_web_port"] == (
        "{{ hostvars[groups['proxmox_hosts'][0]].platform_port_assignments.netdata_port }}"
    )
    assert defaults["netdata_runtime_kickstart_url"] == "https://get.netdata.cloud/kickstart.sh"
    assert "--repositories-only" in defaults["netdata_runtime_repo_bootstrap_args"]
    assert "--stable-channel" in defaults["netdata_runtime_repo_bootstrap_args"]


def test_tasks_manage_stream_api_key_from_control_machine() -> None:
    tasks = load_tasks(TASKS_PATH)

    assert any(task.get("name") == "Check whether the local Netdata stream API key exists" for task in tasks)
    assert any(task.get("name") == "Restore the managed Netdata stream API key from the control machine" for task in tasks)
    assert any(task.get("name") == "Mirror the generated Netdata stream API key to the control machine" for task in tasks)


def test_tasks_bootstrap_the_official_repo_when_native_package_is_missing() -> None:
    tasks = load_tasks(TASKS_PATH)

    policy_task = next(
        task for task in tasks if task.get("name") == "Check whether a native Netdata package candidate is available"
    )
    bootstrap_task = next(
        task for task in tasks if task.get("name") == "Bootstrap the official Netdata native package repository when missing"
    )
    assert_task = next(task for task in tasks if task.get("name") == "Assert a native Netdata package candidate is available")

    assert policy_task["ansible.builtin.command"]["argv"] == ["apt-cache", "policy", "netdata"]
    assert bootstrap_task["ansible.builtin.command"]["argv"] == (
        "{{ [netdata_runtime_kickstart_script_path] + netdata_runtime_repo_bootstrap_args }}"
    )
    assert bootstrap_task["environment"]["DEBIAN_FRONTEND"] == "noninteractive"
    assert assert_task["ansible.builtin.assert"]["fail_msg"].startswith(
        "No Netdata package candidate is available after attempting to bootstrap"
    )


def test_templates_render_parent_and_child_streaming_modes() -> None:
    netdata_template = NETDATA_TEMPLATE_PATH.read_text()
    stream_template = STREAM_TEMPLATE_PATH.read_text()

    assert "dbengine tier 0 retention time" in netdata_template
    assert "destination = {{ netdata_runtime_parent_private_ip }}" in stream_template
    assert "allow from = {{ netdata_runtime_stream_allow_from | join(' ') }}" in stream_template


def test_verify_tasks_cover_info_and_allmetrics_endpoints() -> None:
    tasks = load_tasks(VERIFY_PATH)

    info_task = next(task for task in tasks if task.get("name") == "Verify the local Netdata info endpoint responds")
    metrics_task = next(task for task in tasks if task.get("name") == "Verify the parent Netdata Prometheus exporter responds")

    assert info_task["ansible.builtin.uri"]["url"] == "{{ netdata_runtime_verify_info_url }}"
    assert metrics_task["ansible.builtin.uri"]["url"] == "{{ netdata_runtime_verify_allmetrics_url }}"
