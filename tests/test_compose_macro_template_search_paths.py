from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLES_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"


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
