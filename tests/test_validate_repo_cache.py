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


def test_check_role_argument_specs_avoids_bash4_only_mapfile() -> None:
    script = CHECK_ROLE_ARGUMENT_SPECS_SCRIPT.read_text()

    assert "changed_roles=()" in script
    assert "while IFS= read -r line;" in script
    assert "mapfile" not in script
