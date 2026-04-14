from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "proxmox_security" / "tasks" / "main.yml"
COLLECTION_ROLE_TASKS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "proxmox_security"
    / "tasks"
    / "main.yml"
)


def test_acme_plugin_detection_uses_json_output_and_parsed_conditions() -> None:
    for path in (ROLE_TASKS, COLLECTION_ROLE_TASKS):
        task_text = path.read_text()
        assert "pvenode\n      - acme\n      - plugin\n      - list\n      - --output-format\n      - json" in task_text
        assert "map(attribute='plugin')" in task_text
        assert "is not contains(proxmox_acme_plugin_id)" in task_text
        assert "is contains(proxmox_acme_plugin_id)" in task_text
