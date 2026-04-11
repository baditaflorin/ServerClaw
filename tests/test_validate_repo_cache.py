import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_REPO_SCRIPT = REPO_ROOT / "scripts" / "validate_repo.sh"
CHECK_ROLE_ARGUMENT_SPECS_SCRIPT = REPO_ROOT / "scripts" / "check_role_argument_specs.sh"
REMOTE_EXEC_SCRIPT = REPO_ROOT / "scripts" / "remote_exec.sh"
PYTHON_WITH_PACKAGES_SCRIPT = REPO_ROOT / "scripts" / "run_python_with_packages.sh"


def test_validate_repo_supports_shared_ansible_collection_cache() -> None:
    script = VALIDATE_REPO_SCRIPT.read_text()

    assert "LV3_ANSIBLE_COLLECTIONS_DIR" in script
    assert "LV3_ANSIBLE_COLLECTIONS_SHA_FILE" in script
    assert "LV3_ANSIBLE_GALAXY_SERVER" in script
    assert 'sha256sum "$requirements_file"' in script
    assert 'galaxy_server_args=(--server "$LV3_ANSIBLE_GALAXY_SERVER")' in script
    assert "cmp -s" in script
    assert '"MANIFEST.json"' in script
    assert '"galaxy.yml"' in script


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


def test_validate_repo_checks_generated_discovery_artifacts() -> None:
    script = VALIDATE_REPO_SCRIPT.read_text()

    assert "scripts/generate_discovery_artifacts.py" in script
    assert 'generate_discovery_artifacts.py" --check' in script


def test_validate_repo_uses_python_package_runner_for_yaml_validators() -> None:
    script = VALIDATE_REPO_SCRIPT.read_text()

    assert "scripts/run_python_with_packages.sh" in script
    assert '"$REPO_ROOT/scripts/run_python_with_packages.sh"' in script


def test_validate_repo_runs_public_endpoint_admission_check() -> None:
    script = VALIDATE_REPO_SCRIPT.read_text()

    assert "scripts/subdomain_exposure_audit.py" in script
    assert 'subdomain_exposure_audit.py" --validate' in script


def test_validate_repo_supports_architecture_fitness_stage() -> None:
    script = VALIDATE_REPO_SCRIPT.read_text()

    assert "architecture-fitness" in script
    assert "scripts/replaceability_scorecards.py" in script
    assert "scripts/validate_renovate_contract.py" in script
    assert "scripts/renovate_stack_digest_guard.py" in script


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

    assert 'run_python_with_requirements "$REPO_ROOT/requirements/docs.txt"' in script
    assert "build_docs_portal.py" in script
    assert '--generated-dir "$generated_docs_dir"' in script
    assert 'generated_portal_output_dir="$(mktemp -d "${TMPDIR:-/tmp}/lv3-docs-portal.XXXXXX")"' in script
    assert '--output-dir "$generated_portal_output_dir"' in script
    assert 'make -C "$REPO_ROOT" docs' not in script


def test_validate_repo_tracked_files_fall_back_without_git_metadata() -> None:
    script = VALIDATE_REPO_SCRIPT.read_text()

    assert "rev-parse --is-inside-work-tree" in script
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


def test_remote_exec_avoids_bash4_only_mapfile() -> None:
    script = REMOTE_EXEC_SCRIPT.read_text()

    assert "load_lines_into_array()" in script
    assert "mapfile" not in script


def test_check_role_argument_specs_handles_missing_merge_base_history() -> None:
    script = CHECK_ROLE_ARGUMENT_SPECS_SCRIPT.read_text()

    assert "changed_from_base" in script
    assert "rev-parse --verify --quiet origin/main >/dev/null 2>/dev/null" in script
    assert "2>/dev/null" in script


def test_check_role_argument_specs_falls_back_without_git_metadata() -> None:
    script = CHECK_ROLE_ARGUMENT_SPECS_SCRIPT.read_text()

    assert "rev-parse --is-inside-work-tree >/dev/null 2>&1" in script
    assert 'find "$REPO_ROOT/$COLLECTION_ROLES_ROOT" -mindepth 1 -maxdepth 1 -type d' in script
    assert 'find "$REPO_ROOT/$role_dir" -type f' in script


def _stage_role_argument_specs_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = tmp_path / "repo"
    script_path = repo_root / "scripts" / "check_role_argument_specs.sh"
    script_path.parent.mkdir(parents=True)
    script_path.write_text(CHECK_ROLE_ARGUMENT_SPECS_SCRIPT.read_text(), encoding="utf-8")
    script_path.chmod(0o755)
    return repo_root, script_path


def test_check_role_argument_specs_skips_empty_roles_without_git_metadata(tmp_path: Path) -> None:
    repo_root, script_path = _stage_role_argument_specs_repo(tmp_path)
    roles_root = repo_root / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"

    (roles_root / "empty_role" / "defaults").mkdir(parents=True)
    good_role_meta = roles_root / "good_role" / "meta"
    good_role_meta.mkdir(parents=True)
    (good_role_meta / "argument_specs.yml").write_text(
        "argument_specs:\n  main:\n    options: {}\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        ["bash", str(script_path)],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "empty_role" not in result.stderr


def test_check_role_argument_specs_still_flags_populated_roles_without_meta(tmp_path: Path) -> None:
    repo_root, script_path = _stage_role_argument_specs_repo(tmp_path)
    role_dir = repo_root / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "bad_role" / "tasks"
    role_dir.mkdir(parents=True)
    (role_dir / "main.yml").write_text("---\n[]\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(script_path)],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Missing meta/argument_specs.yml for bad_role" in result.stderr


def test_python_package_runner_handles_pyyaml_module_mapping() -> None:
    script = PYTHON_WITH_PACKAGES_SCRIPT.read_text(encoding="utf-8")

    assert "pyyaml)" in script
    assert 'echo "yaml"' in script
