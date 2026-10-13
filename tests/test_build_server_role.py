from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "build_server" / "tasks" / "main.yml"
ROLE_DEFAULTS = REPO_ROOT / "roles" / "build_server" / "defaults" / "main.yml"
ROLE_ARGUMENT_SPECS = REPO_ROOT / "roles" / "build_server" / "meta" / "argument_specs.yml"
BUILDKIT_TEMPLATE = REPO_ROOT / "roles" / "build_server" / "templates" / "buildkitd.toml.j2"
SERVICE_TEMPLATE = REPO_ROOT / "roles" / "build_server" / "templates" / "lv3-buildkitd.service.j2"


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text())


def test_role_defaults_capture_cache_paths() -> None:
    defaults = load_yaml(ROLE_DEFAULTS)
    assert defaults["build_server_packer_plugin_cache"] == "/opt/builds/.packer.d"
    assert defaults["build_server_ansible_collection_cache"] == "/opt/builds/.ansible/collections"
    assert defaults["build_server_pip_cache_volume"] == "pip-cache"
    assert defaults["build_server_buildkit_service_name"] == "{{ platform_identity.config_prefix }}-buildkitd"
    assert defaults["build_server_buildkit_container_name"] == "{{ platform_identity.config_prefix }}-buildkitd-managed"
    assert defaults["build_server_buildkit_cache_gb"] == 50
    assert defaults["build_server_buildkit_legacy_container_names"] == []
    assert defaults["build_server_buildkit_legacy_containers_idle_confirmed"] is False
    assert defaults["build_server_registry_hosts"][0]["hostname"] == "registry.{{ platform_domain }}"
    assert (
        "playbook_execution_host_patterns.nginx_edge[playbook_execution_env]"
        in (defaults["build_server_registry_hosts"][0]["address"])
    )


def test_role_argument_specs_expose_buildkit_and_cache_inputs() -> None:
    argument_specs = load_yaml(ROLE_ARGUMENT_SPECS)
    options = argument_specs["argument_specs"]["main"]["options"]
    assert options["build_server_buildkit_builder_name"]["type"] == "str"
    assert options["build_server_buildkit_container_name"]["type"] == "str"
    assert options["build_server_buildkit_service_name"]["default"] == "lv3-buildkitd"
    assert options["build_server_buildkit_container_name"]["default"] == "lv3-buildkitd-managed"
    assert options["build_server_buildkit_cache_gb"]["type"] == "int"
    assert options["build_server_pip_cache_volume"]["default"] == "pip-cache"
    assert options["build_server_registry_hosts"]["elements"] == "dict"
    assert options["build_server_buildkit_legacy_container_names"]["elements"] == "str"
    assert options["build_server_buildkit_legacy_containers_idle_confirmed"]["type"] == "bool"


def test_role_tasks_manage_buildkit_builder_and_pip_volume() -> None:
    tasks = load_yaml(ROLE_TASKS)
    task_names = [task["name"] for task in tasks]
    identity_guard = next(
        task
        for task in tasks
        if task["name"] == "Require the selected deployment identity before changing the build host"
    )
    assert (
        "platform_domain | lower not in ['example.com', 'example.org']"
        in identity_guard["ansible.builtin.assert"]["that"]
    )
    assert "platform_identity.config_prefix | lower != 'example'" in identity_guard["ansible.builtin.assert"]["that"]
    assert task_names.index(identity_guard["name"]) < task_names.index("Ensure build server packages are present")
    assert "Render BuildKit daemon configuration" in task_names
    assert "Create the managed buildx builder" in task_names
    assert "Create the pip cache Docker volume" in task_names
    assert "Ensure the build host resolves private registries through the edge" in task_names
    assert "Validate private registry host mappings" in task_names
    assert "Validate explicit legacy BuildKit retirement request" in task_names
    assert "Inspect explicitly listed legacy BuildKit containers" in task_names
    assert (
        "Require listed legacy containers to be the expected BuildKit daemon with its persistent mounts" in task_names
    )
    assert "Inspect systemd units corresponding to explicitly listed legacy BuildKit containers" in task_names
    assert "Require legacy BuildKit systemd-unit inspection to be conclusive" in task_names
    assert "Stop explicit legacy BuildKit systemd units and disable non-canonical units" in task_names
    assert "Reinspect legacy BuildKit containers after stopping their systemd units" in task_names
    assert "Require post-unit legacy BuildKit inspection to be conclusive" in task_names
    assert "Stop explicitly listed idle legacy BuildKit containers" in task_names
    host_mapping_task = next(
        task for task in tasks if task["name"] == "Ensure the build host resolves private registries through the edge"
    )
    assert host_mapping_task["ansible.builtin.blockinfile"]["state"] == (
        "{{ 'present' if build_server_registry_hosts | length > 0 else 'absent' }}"
    )
    retirement_guard = next(
        task for task in tasks if task["name"] == "Validate explicit legacy BuildKit retirement request"
    )
    assert (
        "build_server_buildkit_legacy_containers_idle_confirmed | bool"
        in retirement_guard["ansible.builtin.assert"]["that"]
    )
    assert (
        "build_server_buildkit_legacy_container_names | unique | list | length"
        in retirement_guard["ansible.builtin.assert"]["that"][1]
    )
    assert (
        "build_server_buildkit_container_name not in build_server_buildkit_legacy_container_names"
        in (retirement_guard["ansible.builtin.assert"]["that"])
    )
    stop_task = next(task for task in tasks if task["name"] == "Stop explicitly listed idle legacy BuildKit containers")
    assert stop_task["ansible.builtin.command"]["argv"] == [
        "docker",
        "stop",
        "--time",
        "30",
        "{{ item.item }}",
    ]
    assert "item.rc == 0" in stop_task["when"]
    assert "item.stdout | trim == 'true'" in stop_task["when"]
    assert "No such container" in " ".join(stop_task["failed_when"])
    post_unit_inspect = next(
        task
        for task in tasks
        if task["name"] == "Reinspect legacy BuildKit containers after stopping their systemd units"
    )
    assert post_unit_inspect["ansible.builtin.command"]["argv"] == [
        "docker",
        "inspect",
        "--format",
        "{{ '{{' }}.State.Running{{ '}}' }}",
        "{{ item }}",
    ]
    assert post_unit_inspect["failed_when"] is False
    post_unit_assert = next(
        task for task in tasks if task["name"] == "Require post-unit legacy BuildKit inspection to be conclusive"
    )
    assert "No such object: ' ~ item.item" in post_unit_assert["ansible.builtin.assert"]["that"][0]
    assert "post-unit state" in post_unit_assert["ansible.builtin.assert"]["fail_msg"]
    inspect_units = next(
        task
        for task in tasks
        if task["name"] == "Inspect systemd units corresponding to explicitly listed legacy BuildKit containers"
    )
    assert inspect_units["ansible.builtin.command"]["argv"] == [
        "systemctl",
        "show",
        "--property=LoadState",
        "--value",
        "{{ item }}.service",
    ]
    assert inspect_units["failed_when"] is False
    retire_units = next(
        task
        for task in tasks
        if task["name"] == "Stop explicit legacy BuildKit systemd units and disable non-canonical units"
    )
    assert retire_units["ansible.builtin.systemd_service"]["state"] == "stopped"
    assert (
        retire_units["ansible.builtin.systemd_service"]["enabled"]
        == "{{ item.item == build_server_buildkit_service_name }}"
    )
    assert (
        task_names.index(
            "Require listed legacy containers to be the expected BuildKit daemon with its persistent mounts"
        )
        < task_names.index("Stop explicit legacy BuildKit systemd units and disable non-canonical units")
        < task_names.index("Reinspect legacy BuildKit containers after stopping their systemd units")
        < task_names.index("Require post-unit legacy BuildKit inspection to be conclusive")
        < task_names.index("Stop explicitly listed idle legacy BuildKit containers")
    )


def test_buildkit_config_template_enables_gc_policy() -> None:
    template = BUILDKIT_TEMPLATE.read_text()
    assert "keepDuration" in template
    assert "keepBytes" in template
    assert 'root = "{{ build_server_buildkit_cache_dir }}"' in template


def test_buildkit_service_template_mounts_host_cache_and_socket() -> None:
    template = SERVICE_TEMPLATE.read_text()
    assert "-v {{ build_server_buildkit_cache_dir }}:/var/lib/buildkit" in template
    assert "-v {{ build_server_buildkit_socket_dir }}:{{ build_server_buildkit_socket_dir }}" in template
    assert "--addr unix://{{ build_server_buildkit_socket_file }}" in template
    assert "--add-host {{ registry_host.hostname }}:{{ registry_host.address }}" in template
