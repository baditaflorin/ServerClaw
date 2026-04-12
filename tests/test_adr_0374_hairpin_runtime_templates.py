from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


COMMON_MACRO_PATH = REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/common/templates/compose_macros.j2"

HAIRPIN_MACRO_TEMPLATES = [
    "collections/ansible_collections/lv3/platform/roles/directus_runtime/templates/docker-compose.yml.j2",
    "collections/ansible_collections/lv3/platform/roles/grist_runtime/templates/docker-compose.yml.j2",
    "collections/ansible_collections/lv3/platform/roles/outline_runtime/templates/docker-compose.yml.j2",
    "collections/ansible_collections/lv3/platform/roles/paperless_runtime/templates/docker-compose.yml.j2",
    "collections/ansible_collections/lv3/platform/roles/sftpgo_runtime/templates/docker-compose.yml.j2",
    "collections/ansible_collections/lv3/platform/roles/superset_runtime/templates/docker-compose.yml.j2",
]

DIRECT_HAIRPIN_TEMPLATES = [
    "collections/ansible_collections/lv3/platform/roles/gitea_runtime/templates/docker-compose.yml.j2",
    "collections/ansible_collections/lv3/platform/roles/langfuse_runtime/templates/docker-compose.yml.j2",
    "collections/ansible_collections/lv3/platform/roles/librechat_runtime/templates/docker-compose.yml.j2",
]


def test_common_hairpin_macro_guards_empty_input() -> None:
    template = COMMON_MACRO_PATH.read_text(encoding="utf-8")
    assert "{% if platform_hairpin_nat_hosts | default([]) | length > 0 %}" in template
    assert "{{ entry.hostname }}:{{ entry.address }}" in template


@pytest.mark.parametrize("relative_path", HAIRPIN_MACRO_TEMPLATES)
def test_runtime_templates_use_shared_hairpin_macro(relative_path: str) -> None:
    template = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    assert "hairpin_hosts" in template
    assert "{{ hairpin_hosts() }}" in template


@pytest.mark.parametrize("relative_path", DIRECT_HAIRPIN_TEMPLATES)
def test_runtime_templates_render_shared_hairpin_entries_directly(relative_path: str) -> None:
    template = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    assert "platform_hairpin_nat_hosts" in template
    assert "{{ entry.hostname }}:{{ entry.address }}" in template
