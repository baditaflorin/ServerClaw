from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLES_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"
COMMON_COMPOSE_MACROS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "common"
    / "templates"
    / "compose_macros.j2"
)
PLAYBOOK_COMPOSE_MACROS_PATH = REPO_ROOT / "playbooks" / "templates" / "compose_macros.j2"
PLAYBOOK_INCLUDE_COMPOSE_MACROS_PATH = REPO_ROOT / "playbooks" / "_includes" / "templates" / "compose_macros.j2"
COLLECTION_PLAYBOOK_INCLUDE_COMPOSE_MACROS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "playbooks"
    / "_includes"
    / "templates"
    / "compose_macros.j2"
)


def test_roles_using_compose_macros_depend_on_common_role() -> None:
    missing_common_dependency: list[str] = []

    for role_dir in sorted(ROLES_ROOT.iterdir()):
        compose_template = role_dir / "templates" / "docker-compose.yml.j2"
        meta_main = role_dir / "meta" / "main.yml"
        if not compose_template.exists() or not meta_main.exists():
            continue
        if "compose_macros.j2" not in compose_template.read_text():
            continue

        metadata = yaml.safe_load(meta_main.read_text()) or {}
        dependencies = metadata.get("dependencies") or []
        depends_on_common = any(
            isinstance(dependency, dict) and dependency.get("role") == "lv3.platform.common"
            for dependency in dependencies
        )
        if not depends_on_common:
            missing_common_dependency.append(role_dir.name)

    assert missing_common_dependency == []


def test_playbook_template_loader_exports_current_shared_compose_macros() -> None:
    common_macros = COMMON_COMPOSE_MACROS_PATH.read_text()

    assert PLAYBOOK_COMPOSE_MACROS_PATH.read_text() == common_macros
    assert PLAYBOOK_INCLUDE_COMPOSE_MACROS_PATH.read_text() == common_macros
    assert COLLECTION_PLAYBOOK_INCLUDE_COMPOSE_MACROS_PATH.read_text() == common_macros


def test_roles_using_compose_macros_import_them_via_the_loader_root() -> None:
    unexpected_imports: list[str] = []

    for role_dir in sorted(ROLES_ROOT.iterdir()):
        compose_template = role_dir / "templates" / "docker-compose.yml.j2"
        if not compose_template.exists():
            continue

        for line in compose_template.read_text().splitlines():
            stripped = line.strip()
            if "compose_macros.j2" not in stripped or "{%" not in stripped:
                continue
            if "from 'compose_macros.j2'" not in stripped:
                unexpected_imports.append(f"{role_dir.name}: {stripped}")

    assert unexpected_imports == []
