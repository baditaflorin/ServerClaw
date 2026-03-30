from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "jupyterhub_runtime" / "defaults" / "main.yml"
ROLE_TASKS = REPO_ROOT / "roles" / "jupyterhub_runtime" / "tasks" / "main.yml"
ROLE_VERIFY = REPO_ROOT / "roles" / "jupyterhub_runtime" / "tasks" / "verify.yml"
ROLE_PUBLISH = REPO_ROOT / "roles" / "jupyterhub_runtime" / "tasks" / "publish.yml"
ROLE_META = REPO_ROOT / "roles" / "jupyterhub_runtime" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "jupyterhub_runtime" / "templates" / "docker-compose.yml.j2"
ENV_TEMPLATE = REPO_ROOT / "roles" / "jupyterhub_runtime" / "templates" / "jupyterhub.env.j2"
ENV_CTEMPLATE = REPO_ROOT / "roles" / "jupyterhub_runtime" / "templates" / "jupyterhub.env.ctmpl.j2"
CONFIG_TEMPLATE = REPO_ROOT / "roles" / "jupyterhub_runtime" / "templates" / "jupyterhub_config.py.j2"
HUB_DOCKERFILE = REPO_ROOT / "roles" / "jupyterhub_runtime" / "templates" / "hub.Dockerfile.j2"
SINGLEUSER_DOCKERFILE = REPO_ROOT / "roles" / "jupyterhub_runtime" / "templates" / "singleuser.Dockerfile.j2"


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text())


def test_defaults_define_public_oidc_and_smoke_spawn_contract() -> None:
    defaults = load_yaml(ROLE_DEFAULTS)

    assert defaults["jupyterhub_service_topology"] == "{{ hostvars['proxmox_florin'].lv3_service_topology | service_topology_get('jupyterhub') }}"
    assert defaults["jupyterhub_site_dir"] == "/opt/jupyterhub"
    assert defaults["jupyterhub_compose_file"] == "{{ jupyterhub_site_dir }}/docker-compose.yml"
    assert defaults["jupyterhub_config_file"] == "{{ jupyterhub_site_dir }}/jupyterhub_config.py"
    assert defaults["jupyterhub_public_base_url"] == "https://{{ jupyterhub_service_topology.public_hostname }}"
    assert defaults["jupyterhub_public_hostname_overrides"][0]["hostname"] == "{{ jupyterhub_service_topology.public_hostname }}"
    assert defaults["jupyterhub_public_hostname_overrides"][1]["hostname"] == "{{ hostvars['proxmox_florin'].lv3_service_topology.keycloak.public_hostname }}"
    assert defaults["jupyterhub_hub_image_name"] == "lv3/jupyterhub-hub"
    assert defaults["jupyterhub_singleuser_image_name"] == "lv3/jupyterhub-singleuser"
    assert defaults["jupyterhub_base_image_pull_timeout_seconds"] == 180
    assert defaults["jupyterhub_internal_port"] == "{{ hostvars['proxmox_florin'].platform_port_assignments.jupyterhub_port }}"
    assert defaults["jupyterhub_keycloak_client_id"] == "jupyterhub"
    assert defaults["jupyterhub_verify_username"] == "jupyterhub-smoke"
    assert defaults["jupyterhub_service_api_token_local_file"].endswith("/.local/jupyterhub/service-api-token.txt")
    assert defaults["jupyterhub_minio_root_password_local_file"].endswith("/.local/jupyterhub/minio-root-password.txt")
    assert defaults["jupyterhub_keycloak_client_secret_local_file"].endswith("/.local/keycloak/jupyterhub-client-secret.txt")
    assert defaults["jupyterhub_openai_base_url"] == "{{ jupyterhub_ollama_base_url }}/v1"
    assert "jupyterhub==5.4.4" in defaults["jupyterhub_singleuser_python_dependencies"]


def test_argument_spec_requires_runtime_paths_and_image_inputs() -> None:
    specs = load_yaml(ROLE_META)
    options = specs["argument_specs"]["main"]["options"]

    assert options["jupyterhub_site_dir"]["type"] == "path"
    assert options["jupyterhub_internal_port"]["type"] == "int"
    assert options["jupyterhub_public_base_url"]["type"] == "str"
    assert options["jupyterhub_keycloak_client_secret_local_file"]["type"] == "path"
    assert options["jupyterhub_hub_base_image"]["type"] == "str"
    assert options["jupyterhub_singleuser_base_image"]["type"] == "str"
    assert options["jupyterhub_base_image_pull_timeout_seconds"]["type"] == "int"


def test_main_tasks_render_build_force_recreate_and_verify_runtime() -> None:
    tasks = load_yaml(ROLE_TASKS)
    names = [task["name"] for task in tasks]

    assert "Render the JupyterHub environment file" in names
    assert "Render the JupyterHub config file" in names
    assert "Render the JupyterHub compose file" in names
    assert "Ensure the JupyterHub hub base image is cached locally" in names
    assert "Ensure the JupyterHub single-user base image is cached locally" in names
    assert "Build the JupyterHub hub image" in names
    assert "Build the JupyterHub single-user image" in names
    assert "Check whether the Docker nat chain exists before JupyterHub startup" in names
    assert "Ensure Docker bridge networking chains are present before JupyterHub startup" in names
    assert "Force-recreate the JupyterHub runtime stack after Docker networking recovery" in names
    assert "Verify the JupyterHub runtime" in names

    local_port_probe = next(task for task in tasks if task["name"] == "Check whether the JupyterHub local port is already published")
    assert local_port_probe["ansible.builtin.wait_for"]["port"] == "{{ jupyterhub_internal_port }}"

    health_probe = next(
        task for task in tasks if task["name"] == "Check whether the current JupyterHub local health endpoint is healthy before startup"
    )
    assert health_probe["ansible.builtin.uri"]["url"] == "{{ jupyterhub_internal_base_url }}/hub/health"

    bridge_chain_helper = next(
        task for task in tasks if task["name"] == "Ensure Docker bridge networking chains are present before JupyterHub startup"
    )
    assert bridge_chain_helper["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert bridge_chain_helper["ansible.builtin.include_role"]["tasks_from"] == "docker_bridge_chains"
    assert bridge_chain_helper["vars"]["common_docker_bridge_chains_service_name"] == "docker"
    assert bridge_chain_helper["vars"]["common_docker_bridge_chains_require_nat_chain"] is True

    force_recreate = next(
        task for task in tasks if task["name"] == "Force-recreate the JupyterHub runtime stack after Docker networking recovery"
    )
    assert "--force-recreate" in force_recreate["ansible.builtin.command"]["argv"]
    assert force_recreate["register"] == "jupyterhub_force_recreate_up"
    assert force_recreate["until"] == "jupyterhub_force_recreate_up.rc == 0"

    nat_assert = next(task for task in tasks if task["name"] == "Assert Docker nat chain is present before JupyterHub startup")
    assert nat_assert["ansible.builtin.assert"]["that"] == [
        "jupyterhub_docker_nat_chain.rc == 0 or (common_docker_bridge_chains_nat_verify.rc | default(1)) == 0"
    ]

    hub_cache = next(task for task in tasks if task["name"] == "Ensure the JupyterHub hub base image is cached locally")
    singleuser_cache = next(task for task in tasks if task["name"] == "Ensure the JupyterHub single-user base image is cached locally")
    hub_build = next(task for task in tasks if task["name"] == "Build the JupyterHub hub image")
    singleuser_build = next(task for task in tasks if task["name"] == "Build the JupyterHub single-user image")

    assert "docker image inspect" in hub_cache["ansible.builtin.shell"]
    assert 'timeout "{{ jupyterhub_base_image_pull_timeout_seconds }}"' in hub_cache["ansible.builtin.shell"]
    assert "docker pull" in hub_cache["ansible.builtin.shell"]
    assert hub_cache["until"] == "jupyterhub_hub_base_image_cache.rc == 0"
    assert hub_cache["retries"] == 5
    assert hub_cache["delay"] == 10

    assert "docker image inspect" in singleuser_cache["ansible.builtin.shell"]
    assert 'timeout "{{ jupyterhub_base_image_pull_timeout_seconds }}"' in singleuser_cache["ansible.builtin.shell"]
    assert "docker pull" in singleuser_cache["ansible.builtin.shell"]
    assert singleuser_cache["until"] == "jupyterhub_singleuser_base_image_cache.rc == 0"
    assert singleuser_cache["retries"] == 5
    assert singleuser_cache["delay"] == 10

    assert hub_build["ansible.builtin.command"]["argv"] == [
        "docker",
        "build",
        "--network",
        "host",
        "--pull=false",
        "-t",
        "{{ jupyterhub_hub_image_name }}:latest",
        "{{ jupyterhub_hub_build_dir }}",
    ]
    assert hub_build["environment"] == {"DOCKER_BUILDKIT": "0", "COMPOSE_DOCKER_CLI_BUILD": "0"}
    assert hub_build["until"] == "jupyterhub_hub_build.rc == 0"
    assert hub_build["retries"] == 3
    assert hub_build["delay"] == 10

    assert singleuser_build["ansible.builtin.command"]["argv"] == [
        "docker",
        "build",
        "--network",
        "host",
        "--pull=false",
        "-t",
        "{{ jupyterhub_singleuser_image_name }}:latest",
        "{{ jupyterhub_singleuser_build_dir }}",
    ]
    assert singleuser_build["environment"] == {"DOCKER_BUILDKIT": "0", "COMPOSE_DOCKER_CLI_BUILD": "0"}
    assert singleuser_build["until"] == "jupyterhub_singleuser_build.rc == 0"
    assert singleuser_build["retries"] == 3
    assert singleuser_build["delay"] == 10

    compose_pull = next(task for task in tasks if task["name"] == "Pull the JupyterHub compose-managed images")
    assert compose_pull["ansible.builtin.command"]["argv"] == [
        "docker",
        "compose",
        "--file",
        "{{ jupyterhub_compose_file }}",
        "pull",
        "openbao-agent",
        "minio",
    ]


def test_verify_tasks_cover_local_health_admin_api_and_smoke_spawn() -> None:
    verify = load_yaml(ROLE_VERIFY)
    names = [task["name"] for task in verify]

    assert "Verify the JupyterHub local health endpoint" in names
    assert "Exercise JupyterHub smoke-user provisioning through the local admin API" in names
    assert "Record the spawned Jupyter single-user container name from the admin API payload" in names
    assert "Verify the spawned Jupyter single-user container exposes the expected platform contract" in names
    assert "Stop the JupyterHub smoke user server" in names

    admin_api_task = next(
        task for task in verify if task["name"] == "Exercise JupyterHub smoke-user provisioning through the local admin API"
    )
    assert "{{ jupyterhub_internal_base_url }}" in admin_api_task["ansible.builtin.shell"]
    assert "/hub/api/users/{username}/server" in admin_api_task["ansible.builtin.shell"]

    container_task = next(
        task for task in verify if task["name"] == "Verify the spawned Jupyter single-user container exposes the expected platform contract"
    )
    smoke_name_task = next(
        task for task in verify if task["name"] == "Record the spawned Jupyter single-user container name from the admin API payload"
    )
    assert "jupyterhub_smoke_user_api.stdout | from_json" in smoke_name_task["ansible.builtin.set_fact"]["jupyterhub_smoke_container_name"]
    assert ".object_name" in smoke_name_task["ansible.builtin.set_fact"]["jupyterhub_smoke_container_name"]
    assert 'container_name="{{ jupyterhub_smoke_container_name }}"' in container_task["ansible.builtin.shell"]
    assert "http://minio:9000/minio/health/live" in container_task["ansible.builtin.shell"]
    assert 'assert client.bucket_exists(os.environ["JUPYTERHUB_SHARED_BUCKET"])' in container_task["ansible.builtin.shell"]
    assert "{{ jupyterhub_ollama_base_url }}/api/version" in container_task["ansible.builtin.shell"]


def test_publish_tasks_wait_for_public_health_and_oidc_redirect() -> None:
    publish = load_yaml(ROLE_PUBLISH)
    health_task = next(task for task in publish if task["name"] == "Wait for the JupyterHub public health endpoint")
    redirect_task = next(
        task for task in publish if task["name"] == "Verify the JupyterHub public OIDC login handoff redirects to Keycloak"
    )
    api_task = next(task for task in publish if task["name"] == "Verify the JupyterHub public admin API responds with the service token")

    assert health_task["ansible.builtin.uri"]["url"] == "{{ jupyterhub_public_base_url }}/hub/health"
    assert redirect_task["ansible.builtin.uri"]["url"] == "{{ jupyterhub_public_base_url }}/hub/oauth_login"
    assert redirect_task["ansible.builtin.uri"]["follow_redirects"] == "none"
    assert api_task["ansible.builtin.uri"]["url"] == "{{ jupyterhub_public_base_url }}/hub/api"


def test_templates_define_openbao_envs_compose_and_docker_images() -> None:
    compose_template = COMPOSE_TEMPLATE.read_text()
    env_template = ENV_TEMPLATE.read_text()
    env_ctemplate = ENV_CTEMPLATE.read_text()
    config_template = CONFIG_TEMPLATE.read_text()
    hub_dockerfile = HUB_DOCKERFILE.read_text()
    singleuser_dockerfile = SINGLEUSER_DOCKERFILE.read_text()

    assert "image: {{ jupyterhub_hub_image_name }}:latest" in compose_template
    assert "image: {{ jupyterhub_minio_image }}" in compose_template
    assert '"{{ ansible_host }}:{{ jupyterhub_internal_port }}:8000"' in compose_template
    assert '"127.0.0.1:{{ jupyterhub_internal_port }}:8000"' in compose_template
    assert "name: {{ jupyterhub_compose_network_name }}" in compose_template
    assert "SINGLEUSER_IMAGE={{ jupyterhub_singleuser_image_name }}:latest" in env_template
    assert "OPENAI_BASE_URL={{ jupyterhub_openai_base_url }}" in env_template
    assert 'OIDC_CLIENT_SECRET=[[ with secret "kv/data/{{ jupyterhub_openbao_secret_path }}" ]][[ .Data.data.OIDC_CLIENT_SECRET ]][[ end ]]' in env_ctemplate
    assert "c.JupyterHub.authenticator_class = GenericOAuthenticator" in config_template
    assert 'c.DockerSpawner.name_template = "jupyter-{username}"' in config_template
    assert 'c.JupyterHub.load_roles = [' in config_template
    assert "FROM {{ jupyterhub_hub_base_image }}" in hub_dockerfile
    assert "FROM {{ jupyterhub_singleuser_base_image }}" in singleuser_dockerfile
