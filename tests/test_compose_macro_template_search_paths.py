from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLES_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"


def test_roles_using_compose_macros_include_common_template_search_path() -> None:
    missing_search_path: list[str] = []

    for role_dir in sorted(ROLES_ROOT.iterdir()):
        compose_template = role_dir / "templates" / "docker-compose.yml.j2"
        tasks_main = role_dir / "tasks" / "main.yml"
        if not compose_template.exists() or not tasks_main.exists():
            continue
        if "compose_macros.j2" not in compose_template.read_text():
            continue

        tasks_text = tasks_main.read_text()
        if "ansible_search_path" not in tasks_text or "role_path + '/../common'" not in tasks_text:
            missing_search_path.append(role_dir.name)

    assert missing_search_path == []
