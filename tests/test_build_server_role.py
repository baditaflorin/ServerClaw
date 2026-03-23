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
    assert defaults["build_server_buildkit_cache_gb"] == 50


def test_role_argument_specs_expose_buildkit_and_cache_inputs() -> None:
    argument_specs = load_yaml(ROLE_ARGUMENT_SPECS)
    options = argument_specs["argument_specs"]["main"]["options"]
    assert options["build_server_buildkit_builder_name"]["type"] == "str"
    assert options["build_server_buildkit_cache_gb"]["type"] == "int"
    assert options["build_server_pip_cache_volume"]["default"] == "pip-cache"


def test_role_tasks_manage_buildkit_builder_and_pip_volume() -> None:
    tasks = load_yaml(ROLE_TASKS)
    task_names = [task["name"] for task in tasks]
    assert "Render BuildKit daemon configuration" in task_names
    assert "Create the managed buildx builder" in task_names
    assert "Create the pip cache Docker volume" in task_names


def test_buildkit_config_template_enables_gc_policy() -> None:
    template = BUILDKIT_TEMPLATE.read_text()
    assert "keepDuration" in template
    assert "keepBytes" in template
    assert "root = \"{{ build_server_buildkit_cache_dir }}\"" in template


def test_buildkit_service_template_mounts_host_cache_and_socket() -> None:
    template = SERVICE_TEMPLATE.read_text()
    assert "-v {{ build_server_buildkit_cache_dir }}:/var/lib/buildkit" in template
    assert "-v {{ build_server_buildkit_socket_dir }}:{{ build_server_buildkit_socket_dir }}" in template
    assert "--addr unix://{{ build_server_buildkit_socket_file }}" in template
