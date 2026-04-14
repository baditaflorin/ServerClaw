from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
EDGE_PLAYBOOKS = [
    REPO_ROOT / "playbooks" / "outline.yml",
    REPO_ROOT / "playbooks" / "excalidraw.yml",
    REPO_ROOT / "playbooks" / "public-edge.yml",
    REPO_ROOT / "playbooks" / "langfuse.yml",
    REPO_ROOT / "playbooks" / "minio.yml",
    REPO_ROOT / "playbooks" / "homepage.yml",
    REPO_ROOT / "playbooks" / "keycloak.yml",
    REPO_ROOT / "playbooks" / "ntfy.yml",
    REPO_ROOT / "playbooks" / "directus.yml",
    REPO_ROOT / "playbooks" / "label-studio.yml",
    REPO_ROOT / "playbooks" / "headscale.yml",
    REPO_ROOT / "playbooks" / "matrix-synapse.yml",
    REPO_ROOT / "playbooks" / "n8n.yml",
    REPO_ROOT / "playbooks" / "uptime-kuma.yml",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "dozzle.yml",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "headscale.yml",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "keycloak.yml",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "ntfy.yml",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "directus.yml",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "label-studio.yml",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "matrix-synapse.yml",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "minio.yml",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "n8n.yml",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "public-edge.yml",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "uptime-kuma.yml",
]


def expected_platform_vars(playbook_path: Path) -> list[str]:
    relative_path = playbook_path.relative_to(REPO_ROOT)
    if relative_path.parts[0] == "collections":
        return ["{{ playbook_dir }}/../../../../../inventory/group_vars/platform.yml"]
    return ["{{ playbook_dir }}/../inventory/group_vars/platform.yml"]


def expected_include_platform_vars(include_path: Path) -> list[str]:
    relative_path = include_path.relative_to(REPO_ROOT)
    if relative_path.parts[0] == "collections":
        return ["{{ playbook_dir }}/../../../../../../inventory/group_vars/platform.yml"]
    return ["{{ playbook_dir }}/../../inventory/group_vars/platform.yml"]


def test_edge_publication_playbooks_load_canonical_platform_vars() -> None:
    for playbook_path in EDGE_PLAYBOOKS:
        playbook_text = playbook_path.read_text()
        plays = yaml.safe_load(playbook_text)
        edge_plays = [
            play for play in plays if {"role": "lv3.platform.nginx_edge_publication"} in play.get("roles", [])
        ]

        if edge_plays:
            assert all(play.get("vars_files") == expected_platform_vars(playbook_path) for play in edge_plays), (
                f"{playbook_path} must load the canonical platform vars before republishing the shared edge"
            )
            continue

        assert "_includes/nginx_edge_publication.yml" in playbook_text, (
            f"{playbook_path} should publish through lv3.platform.nginx_edge_publication or import the shared edge include"
        )
        if playbook_path.relative_to(REPO_ROOT).parts[0] == "collections":
            include_path = (
                REPO_ROOT
                / "collections"
                / "ansible_collections"
                / "lv3"
                / "platform"
                / "playbooks"
                / "_includes"
                / "nginx_edge_publication.yml"
            )
        else:
            include_path = REPO_ROOT / "playbooks" / "_includes" / "nginx_edge_publication.yml"

        include_plays = yaml.safe_load(include_path.read_text())
        include_edge_plays = [
            play for play in include_plays if {"role": "lv3.platform.nginx_edge_publication"} in play.get("roles", [])
        ]

        assert include_edge_plays, f"{include_path} should publish through lv3.platform.nginx_edge_publication"
        assert all(
            play.get("vars_files") == expected_include_platform_vars(include_path) for play in include_edge_plays
        ), f"{include_path} must load the canonical platform vars before republishing the shared edge"
