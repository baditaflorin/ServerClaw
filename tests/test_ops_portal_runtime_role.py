from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
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
VERIFY_TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "ops_portal_runtime"
    / "tasks"
    / "verify.yml"
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
COMPOSE_TEMPLATE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "ops_portal_runtime"
    / "templates"
    / "docker-compose.yml.j2"
)


def test_ops_portal_role_replaces_stale_build_context_before_sync() -> None:
    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")
    tasks = TASKS_PATH.read_text(encoding="utf-8")
    compose_template = COMPOSE_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert 'ops_portal_build_context_dir: "{{ ops_portal_site_dir }}/build-context"' in defaults
    assert "ops_portal_build_context_dir" in tasks
    assert "Remove stale ops portal service sources before sync" in tasks
    assert "Discover the ops portal application directories on the controller" in tasks
    assert "Sync the ops portal application files" in tasks
    assert 'src: "{{ item.path }}"' in tasks
    assert "Ensure the ops portal overlay directories exist" in tasks
    assert "Sync critical ops portal runtime files explicitly" in tasks
    assert "Reset the synced search fabric package tree before refresh" in tasks
    assert "Sync the shared search fabric files" in tasks
    assert "ops_portal_service_dir ~ '/search_fabric/'" in tasks
    assert "Sync the ops portal service build inputs explicitly" in tasks
    assert '{{ ops_portal_repo_root }}/scripts/publication_contract.py' in tasks
    assert '{{ ops_portal_repo_root }}/scripts/stage_smoke.py' in tasks
    assert '{{ ops_portal_repo_root }}/requirements/ops-portal.txt' in tasks
    assert 'patterns:' in defaults
    assert '"*.json"' in defaults
    assert 'excludes:' in defaults
    assert '- evidence' in defaults
    assert '- preview' in defaults
    assert "Discover the ops portal directory-backed data files on the controller" in tasks
    assert "item.excludes | default([])" in tasks
    assert "Ensure the synced ops portal directory-backed data subdirectories exist" in tasks
    assert "select('in', item.1.path.split('/'))" in tasks
    assert "Sync the ops portal directory-backed data source files" in tasks
    assert "ops_portal_directory_source_files.results | subelements('files', skip_missing=True)" in tasks
    assert "Remove stale ops portal build-context ignore and metadata files" in tasks
    assert "{{ ops_portal_build_context_dir }}/._publication_contract.py" in tasks
    assert "{{ ops_portal_build_context_dir }}/._stage_smoke.py" in tasks
    assert "Remove stale ops portal build-context entries before sync" in tasks
    assert "Sync the clean ops portal Docker build-context directories" in tasks
    assert "Sync the clean ops portal Docker build-context root files" in tasks
    assert "remote_src: true" in tasks
    assert 'src: "{{ ops_portal_service_dir }}/ops_portal/"' in tasks
    assert 'dest: "{{ ops_portal_build_context_dir }}/ops_portal/"' in tasks
    assert 'src: "{{ ops_portal_service_dir }}/search_fabric/"' in tasks
    assert 'dest: "{{ ops_portal_build_context_dir }}/search_fabric/"' in tasks
    assert "{{ ops_portal_build_context_dir }}/publication_contract.py" in tasks
    assert "{{ ops_portal_build_context_dir }}/stage_smoke.py" in tasks
    assert "{{ ops_portal_build_context_dir }}/requirements.txt" in tasks
    assert "{{ ops_portal_build_context_dir }}/Dockerfile" in tasks
    assert "Discover macOS metadata files in the synced ops portal data tree" in tasks
    assert "Remove macOS metadata files from the synced ops portal data tree" in tasks
    assert "lookup('ansible.builtin.file', item.path)" not in tasks
    assert "lookup('ansible.builtin.file', item.src)" not in tasks
    assert "context: {{ ops_portal_build_context_dir }}" in compose_template


def test_ops_portal_dockerfile_depends_on_synced_helper_files() -> None:
    dockerfile = DOCKERFILE_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "COPY requirements.txt ./requirements.txt" in dockerfile
    assert "COPY publication_contract.py ./publication_contract.py" in dockerfile
    assert "COPY stage_smoke.py ./stage_smoke.py" in dockerfile
    assert "COPY ops_portal/ ./ops_portal/" in dockerfile
    assert "COPY search_fabric/ ./search_fabric/" in dockerfile


def test_ops_portal_verify_checks_launcher_and_runtime_assurance_partials() -> None:
    verify_tasks = VERIFY_TASKS_PATH.read_text(encoding="utf-8")

    assert "Assert the contextual help drawer is present on the ops portal root page" in verify_tasks
    assert "'Contextual Help' in ops_portal_verify_root.content" in verify_tasks
    assert "'Escalation Path' in ops_portal_verify_root.content" in verify_tasks
    assert "Verify the journey-aware entry surface renders locally" in verify_tasks
    assert "/entry?neutral=1" in verify_tasks
    assert "'Journey-Aware Start Surface' in ops_portal_verify_entry.content" in verify_tasks
    assert "'Complete the activation checklist or skip it before pinning a preferred home.' in ops_portal_verify_entry.content" in verify_tasks
    assert "Verify the application launcher partial renders locally" in verify_tasks
    assert '/partials/launcher' in verify_tasks
    assert "Application Launcher" in verify_tasks
    assert "Search destinations, pin favorites, and reopen recent paths from one shared masthead control." in verify_tasks
    assert "Verify the runtime assurance matrix partial renders locally" in verify_tasks
    assert '/partials/runtime-assurance' in verify_tasks
    assert "Ops portal runtime assurance matrix partial did not render the ADR 0244 view." in verify_tasks
    assert "Assert the runtime assurance matrix panel is not degraded" in verify_tasks
    assert "'Runtime assurance data is degraded:' not in ops_portal_verify_runtime_assurance.content" in verify_tasks


def test_ops_portal_runtime_file_sources_include_launcher_partial() -> None:
    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")

    assert "scripts/ops_portal/templates/entry.html" in defaults
    assert "scripts/ops_portal/templates/partials/launcher.html" in defaults
