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
    assert "Sync the ops portal application sources" in tasks
    assert "Sync the shared search fabric package" in tasks
    assert "Sync the shared publication contract helper" in tasks
    assert "Sync the ops portal requirements file" in tasks


def test_ops_portal_dockerfile_depends_on_synced_helper_files() -> None:
    dockerfile = DOCKERFILE_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "COPY requirements.txt ./requirements.txt" in dockerfile
    assert "COPY publication_contract.py ./publication_contract.py" in dockerfile
    assert "COPY ops_portal ./ops_portal" in dockerfile
    assert "COPY search_fabric ./search_fabric" in dockerfile
