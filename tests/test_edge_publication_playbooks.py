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
    REPO_ROOT / "playbooks" / "authentik.yml",
    REPO_ROOT / "playbooks" / "ntfy.yml",
    REPO_ROOT / "playbooks" / "directus.yml",
    REPO_ROOT / "playbooks" / "label-studio.yml",
    REPO_ROOT / "playbooks" / "headscale.yml",
    REPO_ROOT / "playbooks" / "matrix-synapse.yml",
    REPO_ROOT / "playbooks" / "n8n.yml",
    REPO_ROOT / "playbooks" / "uptime-kuma.yml",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "dozzle.yml",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "headscale.yml",
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


def test_public_edge_roles_have_scoped_apply_tags() -> None:
    plays = yaml.safe_load((REPO_ROOT / "playbooks" / "public-edge.yml").read_text())
    playbook = next(play for play in plays if play.get("name", "").startswith("Configure public publication"))
    role_tags = {role["role"]: set(role.get("tags", [])) for role in playbook["roles"]}

    assert "public-edge-firewall" in role_tags["lv3.platform.linux_guest_firewall"]
    assert "public-edge-oidc-auth" in role_tags["lv3.platform.public_edge_oidc_auth"]
    assert "public-edge-nginx" in role_tags["lv3.platform.nginx_edge_publication"]


def test_public_edge_oidc_recovery_is_scoped_and_preserves_existing_credentials() -> None:
    plays = yaml.safe_load((REPO_ROOT / "playbooks" / "public-edge.yml").read_text())
    recovery_play = next(play for play in plays if "public-edge-oidc-recovery" in play.get("tags", []))
    recovery_include = recovery_play["tasks"][0]["ansible.builtin.include_role"]
    recovery_tasks = (
        REPO_ROOT
        / "collections/ansible_collections/lv3/platform/roles/public_edge_oidc_auth/tasks/recover_existing_proxy.yml"
    ).read_text()

    assert recovery_include["tasks_from"] == "recover_existing_proxy.yml"
    assert recovery_include["apply"]["tags"] == ["public-edge-oidc-recovery"]
    assert "public_edge_oidc_auth_client_secret" not in recovery_tasks
    assert "ansible.builtin.template" not in recovery_tasks
    assert "state: restarted" in recovery_tasks


def test_public_edge_issuer_hosts_regex_uses_yaml_single_backslashes() -> None:
    tasks = yaml.safe_load(
        (
            REPO_ROOT
            / "collections/ansible_collections/lv3/platform/roles/public_edge_oidc_auth/tasks/main.yml"
        ).read_text()
    )
    pin_task = next(task for task in tasks if task.get("name") == "Pin the Authentik issuer hostname to the local NGINX edge")
    regex = pin_task["ansible.builtin.lineinfile"]["regexp"]

    assert "\\s" in regex
    assert "\\\\s" not in regex


def test_edge_publication_playbooks_load_canonical_platform_vars() -> None:
    for playbook_path in EDGE_PLAYBOOKS:
        playbook_text = playbook_path.read_text()
        plays = yaml.safe_load(playbook_text)
        edge_plays = [
            play
            for play in plays
            if any(role.get("role") == "lv3.platform.nginx_edge_publication" for role in play.get("roles", []))
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
            play
            for play in include_plays
            if any(role.get("role") == "lv3.platform.nginx_edge_publication" for role in play.get("roles", []))
        ]

        assert include_edge_plays, f"{include_path} should publish through lv3.platform.nginx_edge_publication"
        assert all(
            play.get("vars_files") == expected_include_platform_vars(include_path) for play in include_edge_plays
        ), f"{include_path} must load the canonical platform vars before republishing the shared edge"
