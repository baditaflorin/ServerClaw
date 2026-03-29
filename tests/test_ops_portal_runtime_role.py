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

    assert "Remove stale ops portal build context entries before sync" in tasks
    assert '"{{ ops_portal_service_dir }}/ops_portal"' in tasks
    assert '"{{ ops_portal_service_dir }}/search_fabric"' in tasks
    assert '"{{ ops_portal_service_dir }}/publication_contract.py"' in tasks
    assert '"{{ ops_portal_service_dir }}/requirements.txt"' in tasks
    assert "Stage and expand the ops portal application sources" in tasks
    assert 'tar -C "{{ ops_portal_repo_root }}/scripts" -czf "{{ ops_portal_app_archive_local.path }}" ops_portal' in tasks
    assert "Stage and expand the shared search fabric package" in tasks
    assert 'tar -C "{{ ops_portal_repo_root }}/scripts" -czf "{{ ops_portal_search_fabric_archive_local.path }}" search_fabric' in tasks
    assert "Sync the ops portal service build inputs explicitly" in tasks
    assert '{{ ops_portal_repo_root }}/scripts/publication_contract.py' in tasks
    assert '{{ ops_portal_repo_root }}/requirements/ops-portal.txt' in tasks
    assert "Remove stale ops portal directory-backed data sources before sync" in tasks
    assert "Build local staging archives for the ops portal directory-backed data sources" in tasks
    assert 'tar -C "{{ item.src | regex_replace(\'/$\', \'\') | dirname }}" \\' in tasks
    assert '"/tmp/ops-portal-{{ item.dest | regex_replace(\'/$\', \'\') | basename }}-sync.tar.gz"' in tasks
    assert "Copy the staged archives to the guest for the ops portal directory-backed data sources" in tasks
    assert "Expand the staged archives on the guest for the ops portal directory-backed data sources" in tasks


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
