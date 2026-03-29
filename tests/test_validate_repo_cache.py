from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_REPO_SCRIPT = REPO_ROOT / "scripts" / "validate_repo.sh"
CHECK_ROLE_ARGUMENT_SPECS_SCRIPT = REPO_ROOT / "scripts" / "check_role_argument_specs.sh"


def test_validate_repo_supports_shared_ansible_collection_cache() -> None:
    script = VALIDATE_REPO_SCRIPT.read_text()

    assert "LV3_ANSIBLE_COLLECTIONS_DIR" in script
    assert "LV3_ANSIBLE_COLLECTIONS_SHA_FILE" in script
    assert "sha256sum \"$requirements_file\"" in script
    assert "cmp -s" in script


def test_validate_repo_runs_tofu_validation_when_present() -> None:
    script = VALIDATE_REPO_SCRIPT.read_text()

    assert "scripts/tofu_exec.sh" in script
    assert "validate_tofu" in script


def test_validate_repo_supports_ansible_idempotency_stage() -> None:
    script = VALIDATE_REPO_SCRIPT.read_text()

    assert "ansible-idempotency" in script
    assert "scripts/ansible_role_idempotency.py" in script


def test_validate_repo_avoids_bash4_only_mapfile() -> None:
    script = VALIDATE_REPO_SCRIPT.read_text()

    assert "load_lines_into_array()" in script
    assert "mapfile" not in script


def test_validate_repo_supports_workstream_surface_stage() -> None:
    script = VALIDATE_REPO_SCRIPT.read_text()

    assert "workstream-surfaces" in script
    assert "scripts/workstream_surface_ownership.py" in script


def test_validate_repo_supports_architecture_fitness_stage() -> None:
    script = VALIDATE_REPO_SCRIPT.read_text()

    assert "architecture-fitness" in script
    assert "scripts/replaceability_scorecards.py" in script


def test_validate_repo_json_stage_falls_back_without_jq() -> None:
    script = VALIDATE_REPO_SCRIPT.read_text()

    assert "if command -v jq" in script
    assert 'resolved_json_file="$REPO_ROOT/$json_file"' in script
    assert "json.loads" in script


def test_validate_repo_json_stage_skips_missing_remote_artifacts() -> None:
    script = VALIDATE_REPO_SCRIPT.read_text()

    assert 'if [[ ! -f "$resolved_json_file" ]]; then' in script
    assert "continue" in script


def test_validate_repo_generated_portals_stage_does_not_require_make() -> None:
    script = VALIDATE_REPO_SCRIPT.read_text()

    assert 'run --with-requirements "$REPO_ROOT/requirements/docs.txt"' in script
    assert "mkdocs build --strict" in script
    assert "generate_docs_site.py" in script
    assert 'sed "s|^docs_dir: .*|docs_dir: $generated_docs_dir|"' in script
    assert 'make -C "$REPO_ROOT" docs' not in script


def test_validate_repo_tracked_files_fall_back_without_git_metadata() -> None:
    script = VALIDATE_REPO_SCRIPT.read_text()

    assert 'rev-parse --is-inside-work-tree' in script
    assert 'repo_root.glob(pattern) if "/" in pattern else repo_root.rglob(pattern)' in script
    assert 'skip_dirs = {".ansible", ".git", ".local", ".pytest_cache", ".venv", ".worktrees"}' in script


def test_validate_repo_tracked_files_skip_appledouble_artifacts() -> None:
    script = VALIDATE_REPO_SCRIPT.read_text()

    assert 'if any(part.startswith("._") for part in parts):' in script
    assert 'if rel.name == ".DS_Store":' in script


def test_check_role_argument_specs_avoids_bash4_only_mapfile() -> None:
    script = CHECK_ROLE_ARGUMENT_SPECS_SCRIPT.read_text()

    assert "changed_roles=()" in script
    assert "while IFS= read -r line;" in script
    assert "mapfile" not in script


def test_check_role_argument_specs_handles_missing_merge_base_history() -> None:
    script = CHECK_ROLE_ARGUMENT_SPECS_SCRIPT.read_text()

    assert "changed_from_base" in script
    assert "rev-parse --verify --quiet origin/main >/dev/null 2>/dev/null" in script
    assert "2>/dev/null" in script


def test_check_role_argument_specs_falls_back_without_git_metadata() -> None:
    script = CHECK_ROLE_ARGUMENT_SPECS_SCRIPT.read_text()

    assert 'rev-parse --is-inside-work-tree >/dev/null 2>&1' in script
    assert 'find "$REPO_ROOT/$COLLECTION_ROLES_ROOT" -mindepth 1 -maxdepth 1 -type d' in script
