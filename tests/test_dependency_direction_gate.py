from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_validation_gate_runs_dependency_direction_check() -> None:
    validate_gate = (REPO_ROOT / "config" / "validation-gate.json").read_text(encoding="utf-8")

    assert "scripts/validate_dependency_direction.py" in validate_gate


def test_validate_repo_and_make_expose_dependency_direction_stage() -> None:
    validate_script = (REPO_ROOT / "scripts" / "validate_repo.sh").read_text(encoding="utf-8")
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "dependency-direction" in validate_script
    assert "scripts/validate_dependency_direction.py" in validate_script
    assert "validate-dependency-direction" in makefile
