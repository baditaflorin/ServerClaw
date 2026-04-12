from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
TOP_LEVEL_TASKS = REPO_ROOT / "playbooks" / "tasks" / "security-scan.yml"
COLLECTION_TASKS = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "tasks" / "security-scan.yml"
)


def load_tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())


def test_security_scan_task_copies_stay_in_sync() -> None:
    assert load_tasks(TOP_LEVEL_TASKS) == load_tasks(COLLECTION_TASKS)


def test_security_scan_only_installs_lynis_when_missing() -> None:
    tasks = load_tasks(COLLECTION_TASKS)[0]["tasks"]
    check_task = next(task for task in tasks if task["name"] == "Check whether Lynis is already installed")
    install_task = next(task for task in tasks if task["name"] == "Ensure Lynis is installed when missing")

    assert check_task["ansible.builtin.command"]["argv"] == ["dpkg-query", "-W", "-f=${Status}", "lynis"]
    assert check_task["failed_when"] is False
    assert install_task["ansible.builtin.apt"]["update_cache"] is True
    assert install_task["when"] == [
        'security_scan_lynis_installed.rc != 0 or "install ok installed" not in security_scan_lynis_installed.stdout'
    ]
