from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "ops_portal_runtime"
DEFAULTS_PATH = ROLE_ROOT / "defaults" / "main.yml"
TASKS_PATH = ROLE_ROOT / "tasks" / "main.yml"
DOCKERFILE_TEMPLATE_PATH = ROLE_ROOT / "templates" / "Dockerfile.j2"


def test_ops_portal_runtime_declares_receipt_directory_sources() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())

    assert defaults["ops_portal_directory_sources"] == [
        {
            "src": "{{ ops_portal_repo_root }}/receipts/live-applies/",
            "dest": "{{ ops_portal_data_dir }}/receipts/live-applies/",
        },
        {
            "src": "{{ ops_portal_repo_root }}/receipts/drift-reports/",
            "dest": "{{ ops_portal_data_dir }}/receipts/drift-reports/",
        },
    ]


def test_ops_portal_runtime_ensures_directory_destinations_before_copying_receipts() -> None:
    tasks = yaml.safe_load(TASKS_PATH.read_text())

    ensure_index = next(
        index
        for index, task in enumerate(tasks)
        if task.get("name") == "Ensure the ops portal directory-backed data destinations exist"
    )
    sync_index = next(
        index
        for index, task in enumerate(tasks)
        if task.get("name") == "Sync the ops portal directory-backed data sources"
    )
    ensure_task = tasks[ensure_index]

    assert ensure_index < sync_index
    assert ensure_task["ansible.builtin.file"] == {
        "path": "{{ item.dest }}",
        "state": "directory",
        "owner": "root",
        "group": "root",
        "mode": "0755",
    }
    assert ensure_task["loop"] == "{{ ops_portal_directory_sources }}"


def test_ops_portal_runtime_explicitly_syncs_search_fabric_package_before_build() -> None:
    tasks = yaml.safe_load(TASKS_PATH.read_text())

    sync_index = next(
        index for index, task in enumerate(tasks) if task.get("name") == "Sync the shared search fabric package explicitly"
    )
    manifest_index = next(
        index for index, task in enumerate(tasks) if task.get("name") == "Gather the synced ops portal build context manifest"
    )
    sync_task = tasks[sync_index]

    assert sync_index < manifest_index
    assert sync_task["ansible.builtin.copy"] == {
        "src": "{{ ops_portal_repo_root }}/scripts/search_fabric/",
        "dest": "{{ ops_portal_service_dir }}/search_fabric/",
        "owner": "root",
        "group": "root",
        "mode": "0644",
        "directory_mode": "0755",
    }


def test_ops_portal_runtime_syncs_search_fabric_tree_as_a_directory_copy() -> None:
    tasks = yaml.safe_load(TASKS_PATH.read_text())

    sync_task = next(
        task for task in tasks if task.get("name") == "Sync the shared search fabric files"
    )

    assert sync_task["ansible.builtin.copy"] == {
        "src": "{{ ops_portal_repo_root }}/scripts/search_fabric/",
        "dest": "{{ ops_portal_service_dir }}/search_fabric/",
        "owner": "root",
        "group": "root",
        "mode": "0644",
        "directory_mode": "0755",
    }


def test_ops_portal_runtime_dockerfile_copies_package_contents_without_nesting() -> None:
    dockerfile_template = DOCKERFILE_TEMPLATE_PATH.read_text()

    assert "COPY ops_portal/ ./ops_portal/" in dockerfile_template
    assert "COPY search_fabric/ ./search_fabric/" in dockerfile_template


def test_ops_portal_role_replaces_stale_build_context_before_sync() -> None:
    tasks = TASKS_PATH.read_text(encoding="utf-8")

    assert "Remove stale ops portal service sources before sync" in tasks
    assert "Discover the ops portal application directories on the controller" in tasks
    assert "Sync the ops portal application files" in tasks
    assert 'src: "{{ item.path }}"' in tasks
    assert "Ensure the ops portal overlay directories exist" in tasks
    assert "Sync critical ops portal runtime files explicitly" in tasks
    assert "Reset the synced search fabric package tree before refresh" in tasks
    assert "Sync the shared search fabric files" in tasks
    assert "Sync the ops portal service build inputs explicitly" in tasks
    assert '{{ ops_portal_repo_root }}/scripts/publication_contract.py' in tasks
    assert '{{ ops_portal_repo_root }}/requirements/ops-portal.txt' in tasks
    assert "Sync the ops portal directory-backed data sources" in tasks
    assert 'directory_mode: "0755"' in tasks
    assert "Discover macOS metadata files in the synced ops portal data tree" in tasks
    assert "Remove macOS metadata files from the synced ops portal data tree" in tasks
    assert "lookup('ansible.builtin.file', item.path)" not in tasks
    assert "lookup('ansible.builtin.file', item.src)" not in tasks


def test_ops_portal_dockerfile_depends_on_synced_helper_files() -> None:
    dockerfile = DOCKERFILE_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "COPY requirements.txt ./requirements.txt" in dockerfile
    assert "COPY publication_contract.py ./publication_contract.py" in dockerfile
    assert "COPY ops_portal/ ./ops_portal/" in dockerfile or "COPY ops_portal ./ops_portal" in dockerfile
    assert "COPY search_fabric/ ./search_fabric/" in dockerfile or "COPY search_fabric ./search_fabric" in dockerfile


def test_ops_portal_verify_checks_launcher_partial() -> None:
    verify_tasks = (
        REPO_ROOT
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "ops_portal_runtime"
        / "tasks"
        / "verify.yml"
    ).read_text(encoding="utf-8")

    assert "Verify the application launcher partial renders locally" in verify_tasks
    assert '/partials/launcher' in verify_tasks
    assert "Application Launcher" in verify_tasks
    assert "Search destinations, pin favorites, and reopen recent paths from one shared masthead control." in verify_tasks


def test_ops_portal_runtime_file_sources_include_launcher_partial() -> None:
    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")

    assert "scripts/ops_portal/templates/partials/launcher.html" in defaults
