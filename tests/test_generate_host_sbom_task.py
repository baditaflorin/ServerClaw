from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
TOP_LEVEL_TASKS = REPO_ROOT / "playbooks" / "tasks" / "generate-host-sbom.yml"
COLLECTION_TASKS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "playbooks"
    / "tasks"
    / "generate-host-sbom.yml"
)


def load_tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())


def test_generate_host_sbom_task_copies_stay_in_sync() -> None:
    assert load_tasks(TOP_LEVEL_TASKS) == load_tasks(COLLECTION_TASKS)


def test_generate_host_sbom_uses_syft_relative_excludes() -> None:
    tasks = load_tasks(COLLECTION_TASKS)
    generate_task = next(task for task in tasks if task["name"] == "Generate the host CycloneDX SBOM")
    argv = generate_task["ansible.builtin.command"]["argv"]

    assert "./dev/**" in argv
    assert "./proc/**" in argv
    assert "./run/**" in argv
    assert "./sys/**" in argv
    assert "./tmp/**" in argv
    assert "./var/tmp/**" in argv
    assert "./var/lib/containerd/**" in argv
    assert "./var/lib/docker/**" in argv
    assert "/dev/**" not in argv
    assert "/proc/**" not in argv
    assert "/run/**" not in argv
    assert "/sys/**" not in argv
    assert "/tmp/**" not in argv
    assert "/var/tmp/**" not in argv
    assert "/var/lib/containerd/**" not in argv
    assert "/var/lib/docker/**" not in argv
