from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "playbooks"
    / "services"
    / "build-server-gate-tools.yml"
)


def test_native_gate_playbook_installs_isolated_semgrep_and_gitleaks() -> None:
    source = PLAYBOOK.read_text(encoding="utf-8")

    assert 'gate_tools_semgrep_version: "1.155.0"' in source
    assert "uv tool install --force --python /usr/bin/python3" in source
    assert "UV_TOOL_DIR: /opt/builds/gate-tools/uv-tools" in source
    assert 'gate_tools_gitleaks_version: "8.28.0"' in source
    assert "gitleaks_{{ gate_tools_gitleaks_version }}_linux_x64.tar.gz" in source
    assert 'gitleaks: "{{ gate_tools_gitleaks_version }}"' in source


def test_native_gate_playbook_pins_a_tofu_version_supported_by_the_repo() -> None:
    source = PLAYBOOK.read_text(encoding="utf-8")

    assert 'gate_tools_tofu_version: "1.12.6"' in source
    assert "tofu_{{ gate_tools_tofu_version }}_linux_amd64.zip" in source
