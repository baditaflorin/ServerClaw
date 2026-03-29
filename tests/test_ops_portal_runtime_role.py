from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "ops_portal_runtime"
    / "tasks"
    / "main.yml"
)
DEFAULTS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "ops_portal_runtime"
    / "defaults"
    / "main.yml"
)
DOCKERFILE_TEMPLATE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "ops_portal_runtime"
    / "templates"
    / "Dockerfile.j2"
)


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
    assert "COPY ops_portal ./ops_portal" in dockerfile
    assert "COPY search_fabric ./search_fabric" in dockerfile


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
