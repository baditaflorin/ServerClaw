from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_VALIDATORS = {
    "require_mapping",
    "require_str",
    "require_string_list",
    "require_unique_string_list",
    "require_list",
    "require_bool",
    "require_int",
    "require_identifier",
    "require_http_url",
    "require_semver",
    "require_enum",
    "require_path",
}
EXEMPT_FILES = {
    REPO_ROOT / "scripts" / "validation_toolkit.py",
    REPO_ROOT / "scripts" / "test_validation_toolkit.py",
}


def test_only_validation_toolkit_defines_canonical_validators() -> None:
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "scripts").rglob("*.py")):
        if path in EXEMPT_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        for name in sorted(CANONICAL_VALIDATORS):
            if re.search(rf"^def {name}\b", text, re.MULTILINE):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{name}")
    assert offenders == []


def test_validate_repo_runs_full_validation_toolkit_enforcement() -> None:
    script = (REPO_ROOT / "scripts" / "validate_repo.sh").read_text(encoding="utf-8")

    assert 'scripts/enforce_validation_toolkit.sh" --all-files' in script
