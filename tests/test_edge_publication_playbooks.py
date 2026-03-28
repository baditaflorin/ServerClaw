from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PLATFORM_VARS = [
    "{{ lookup('ansible.builtin.env', 'PWD') }}/inventory/group_vars/platform.yml"
]
EDGE_PLAYBOOKS = [
    REPO_ROOT / "playbooks" / "outline.yml",
    REPO_ROOT / "playbooks" / "excalidraw.yml",
    REPO_ROOT / "playbooks" / "public-edge.yml",
    REPO_ROOT / "playbooks" / "langfuse.yml",
    REPO_ROOT / "playbooks" / "homepage.yml",
    REPO_ROOT / "playbooks" / "keycloak.yml",
    REPO_ROOT / "playbooks" / "headscale.yml",
    REPO_ROOT / "playbooks" / "n8n.yml",
    REPO_ROOT / "playbooks" / "uptime-kuma.yml",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "dozzle.yml",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "headscale.yml",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "keycloak.yml",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "n8n.yml",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "public-edge.yml",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "uptime-kuma.yml",
]


def test_edge_publication_playbooks_load_canonical_platform_vars() -> None:
    for playbook_path in EDGE_PLAYBOOKS:
        plays = yaml.safe_load(playbook_path.read_text())
        edge_plays = [
            play
            for play in plays
            if {"role": "lv3.platform.nginx_edge_publication"} in play.get("roles", [])
        ]

        assert edge_plays, f"{playbook_path} should publish through lv3.platform.nginx_edge_publication"
        assert all(
            play.get("vars_files") == CANONICAL_PLATFORM_VARS for play in edge_plays
        ), f"{playbook_path} must load the canonical platform vars before republishing the shared edge"
