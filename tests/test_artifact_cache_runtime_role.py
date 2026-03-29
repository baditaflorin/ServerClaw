from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "artifact_cache_runtime"
)


def test_artifact_cache_defaults_define_four_upstream_mirrors() -> None:
    defaults = yaml.safe_load((ROLE_ROOT / "defaults" / "main.yml").read_text())
    mirrors = defaults["artifact_cache_registry_mirrors"]
    assert defaults["artifact_cache_network_mode"] == "host"
    assert list(mirrors.keys()) == ["docker_io", "ghcr_io", "artifacts_plane_so", "docker_n8n_io"]
    assert mirrors["docker_io"]["upstream_registry"] == "https://registry-1.docker.io"
    assert mirrors["ghcr_io"]["bind_port"] == 5002
    assert mirrors["docker_io"]["mirror_registry"] == "{{ artifact_cache_bind_host }}:5001"


def test_artifact_cache_tasks_render_seed_plan_then_warm_images() -> None:
    tasks = yaml.safe_load((ROLE_ROOT / "tasks" / "main.yml").read_text())
    task_names = [task["name"] for task in tasks]
    assert "Generate the artifact cache seed plan from repo catalogs" in task_names
    assert "Persist the artifact cache seed plan on the guest" in task_names
    assert "Warm the mirrored image set through the cache endpoints" in task_names


def test_artifact_cache_compose_template_exposes_proxy_remote_urls() -> None:
    template = (ROLE_ROOT / "templates" / "docker-compose.yml.j2").read_text()
    assert "REGISTRY_PROXY_REMOTEURL" in template
    assert "network_mode: {{ artifact_cache_network_mode }}" in template
    assert "REGISTRY_HTTP_ADDR: 0.0.0.0:{{ (artifact_cache_network_mode == 'host') | ternary(mirror.bind_port, 5000) }}" in template
    assert "{% if artifact_cache_network_mode != 'host' %}" in template
    assert "{{ mirror.storage_path }}:/var/lib/registry" in template
