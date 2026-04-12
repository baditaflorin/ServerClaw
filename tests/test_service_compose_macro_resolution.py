import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


REPO_ROOT = Path(__file__).resolve().parents[1]
LITELLM_TEMPLATE = REPO_ROOT / "roles" / "litellm_runtime" / "templates" / "docker-compose.yml.j2"
LIBRECHAT_TEMPLATE = REPO_ROOT / "roles" / "librechat_runtime" / "templates" / "docker-compose.yml.j2"
COMMON_MACROS = REPO_ROOT / "roles" / "common" / "templates" / "compose_macros.j2"
PLAYBOOK_MACROS = REPO_ROOT / "playbooks" / "templates" / "compose_macros.j2"


def test_litellm_compose_template_only_imports_compose_macros_when_openbao_is_enabled() -> None:
    template = LITELLM_TEMPLATE.read_text(encoding="utf-8")

    assert (
        "{% if litellm_enable_openbao_agent | bool %}\n{% from 'compose_macros.j2' import openbao_sidecar %}\n{% endif %}\nservices:"
        in template
    )
    assert '{{ openbao_sidecar("litellm") }}' in template


def test_librechat_compose_template_only_imports_compose_macros_when_openbao_is_enabled() -> None:
    template = LIBRECHAT_TEMPLATE.read_text(encoding="utf-8")

    assert (
        "{% if librechat_enable_openbao_agent | bool %}\n{% from 'compose_macros.j2' import openbao_sidecar %}\n{% endif %}\nservices:"
        in template
    )
    assert '{{ openbao_sidecar("librechat") }}' in template


def test_playbook_compose_macros_bridge_matches_common_library() -> None:
    assert PLAYBOOK_MACROS.read_text(encoding="utf-8") == COMMON_MACROS.read_text(encoding="utf-8")


def test_openbao_sidecar_renders_volume_mounts_on_separate_lines() -> None:
    env = Environment(loader=FileSystemLoader(str(COMMON_MACROS.parent)))
    env.filters["dirname"] = lambda value: str(Path(value).parent)
    env.filters["to_json"] = json.dumps
    env.globals["lookup"] = lambda kind, name: {
        "platform_context_openbao_agent_image": "docker.io/openbao/openbao:latest",
        "platform_context_openbao_agent_container_name": "platform-context-openbao-agent",
        "platform_context_env_file": "/run/lv3-secrets/platform-context/runtime.env",
        "platform_context_openbao_agent_dir": "/opt/platform-context/openbao",
    }[name]

    rendered = env.from_string(
        "{% from 'compose_macros.j2' import openbao_sidecar %}\nservices:\n{{ openbao_sidecar('platform_context') }}"
    ).render()

    assert "\n  openbao-agent:\n" in rendered
    assert "      - /opt/platform-context/openbao:/openbao-agent:ro\n" in rendered
    assert "      - /run/lv3-secrets/platform-context:/run/lv3-secrets/platform-context\n" in rendered
