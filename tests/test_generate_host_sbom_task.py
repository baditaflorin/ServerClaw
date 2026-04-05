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


def test_generate_host_sbom_scans_the_package_inventory_by_default() -> None:
    tasks = load_tasks(COLLECTION_TASKS)
    remove_task = next(task for task in tasks if task["name"] == "Remove any stale host SBOM before regeneration")
    load_task = next(task for task in tasks if task["name"] == "Load the shared SBOM scanner config")
    generate_task = next(task for task in tasks if task["name"] == "Generate the host CycloneDX SBOM")
    argv = generate_task["ansible.builtin.command"]["argv"]

    assert remove_task["ansible.builtin.file"]["path"] == (
        "{{ security_sbom_remote_dir }}/{{ inventory_hostname }}-host-sbom.cdx.json"
    )
    assert remove_task["ansible.builtin.file"]["state"] == "absent"
    assert argv[:2] == ["timeout", "{{ security_sbom_timeout_seconds }}"]
    assert "/usr/local/bin/syft" == argv[2]
    assert argv[4] == "{{ security_sbom_source }}"
    assert "security_sbom_source" in load_task["ansible.builtin.set_fact"]
    assert "file:/var/lib/dpkg/status" in load_task["ansible.builtin.set_fact"]["security_sbom_source"]
    assert "dir:/" not in argv
    assert "--base-path" not in argv
    assert "--exclude" not in argv


def test_generate_host_sbom_defaults_include_timeout_seconds() -> None:
    tasks = load_tasks(COLLECTION_TASKS)
    load_task = next(task for task in tasks if task["name"] == "Load the shared SBOM scanner config")

    assert "security_sbom_timeout_seconds" in load_task["ansible.builtin.set_fact"]
    assert "default(900, true)" in load_task["ansible.builtin.set_fact"]["security_sbom_timeout_seconds"]
