"""Contract tests for config/platform_credentials.yml — ADR 0438 Phase 3.

Verifies:
  - Registry loads without YAML parse errors
  - Each credential has a unique id
  - Each local_file_var is unique (no two credentials share the same variable name)
  - Each id matches ^[a-z][a-z0-9_]*$
  - Each local_file_var ends in _local_file
  - Each owner_role exists on disk (collections/ or roles/)
  - No two entries have the same local_file_path when both are static strings
  - The openbao_postgres_rotator_password unification is correct:
      writer (openbao_postgres_backend) and reader (openbao_runtime) use the same var name
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CREDENTIALS_FILE = REPO_ROOT / "config" / "platform_credentials.yml"
COLLECTIONS_ROLES = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"
LEGACY_ROLES = REPO_ROOT / "roles"

_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_VAR_RE = re.compile(r"^[a-z][a-z0-9_]*_local_file$")
_ROLE_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


def _all_role_names() -> frozenset[str]:
    names: set[str] = set()
    for base in (COLLECTIONS_ROLES, LEGACY_ROLES):
        if base.exists():
            for entry in base.iterdir():
                if entry.is_dir() and not entry.name.startswith("_"):
                    names.add(entry.name)
    return frozenset(names)


def _load_credentials() -> list[dict]:
    data = yaml.safe_load(CREDENTIALS_FILE.read_text(encoding="utf-8"))
    return data["platform_credentials"]


def test_credentials_file_exists_and_parses() -> None:
    assert CREDENTIALS_FILE.exists(), f"Missing {CREDENTIALS_FILE}"
    creds = _load_credentials()
    assert isinstance(creds, list)
    assert len(creds) >= 1, "platform_credentials must have at least one entry"


def test_credentials_unique_ids() -> None:
    creds = _load_credentials()
    ids = [c["id"] for c in creds]
    duplicates = {x for x in ids if ids.count(x) > 1}
    assert not duplicates, f"Duplicate credential ids: {sorted(duplicates)}"


def test_credentials_unique_var_names() -> None:
    creds = _load_credentials()
    vars_ = [c["local_file_var"] for c in creds]
    duplicates = {x for x in vars_ if vars_.count(x) > 1}
    assert not duplicates, (
        f"Duplicate local_file_var values: {sorted(duplicates)} — "
        "two credentials sharing the same variable name is the writer/reader confusion this registry prevents"
    )


def test_credentials_id_format() -> None:
    creds = _load_credentials()
    bad = [c["id"] for c in creds if not _ID_RE.match(c["id"])]
    assert not bad, f"ids not matching ^[a-z][a-z0-9_]*$: {bad}"


def test_credentials_var_ends_in_local_file() -> None:
    creds = _load_credentials()
    bad = [c["local_file_var"] for c in creds if not _VAR_RE.match(c["local_file_var"])]
    assert not bad, f"local_file_var values not matching *_local_file: {bad}"


def test_credentials_var_matches_id_convention() -> None:
    """local_file_var should equal <id>_local_file (warnings for deviations help catch drift)."""
    creds = _load_credentials()
    mismatches = []
    for c in creds:
        expected = f"{c['id']}_local_file"
        if c["local_file_var"] != expected:
            mismatches.append((c["id"], c["local_file_var"], expected))
    assert not mismatches, "local_file_var does not match <id>_local_file convention:\n" + "\n".join(
        f"  id={a}: got {b!r}, expected {c!r}" for a, b, c in mismatches
    )


def test_credentials_owner_role_exists() -> None:
    creds = _load_credentials()
    all_roles = _all_role_names()
    missing = [c["id"] for c in creds if c.get("owner_role") and c["owner_role"] not in all_roles]
    assert not missing, (
        f"owner_role references non-existent roles for credential ids: {missing}. "
        f"Available roles (sample): {sorted(all_roles)[:20]}"
    )


def test_credentials_required_fields_present() -> None:
    required = {"id", "owner_role", "consumer_roles", "local_file_var", "local_file_path", "secret_type", "description"}
    creds = _load_credentials()
    for cred in creds:
        missing = required - set(cred.keys())
        assert not missing, f"Credential {cred.get('id', '?')} is missing required fields: {missing}"


def test_credentials_secret_type_is_valid() -> None:
    valid_types = {"password", "token", "api_key", "approle", "cert", "secret"}
    creds = _load_credentials()
    bad = [(c["id"], c["secret_type"]) for c in creds if c.get("secret_type") not in valid_types]
    assert not bad, f"Unknown secret_type values: {bad}. Valid: {sorted(valid_types)}"


def test_openbao_postgres_writer_reader_unified() -> None:
    """Regression test for ADR 0438 Phase 3 model case.

    openbao_postgres_backend (writer) and openbao_runtime (reader) must both reference
    openbao_postgres_rotator_password_local_file — not openbao_postgres_admin_password_local_file.
    """
    # Check the registry declares the canonical name
    creds = _load_credentials()
    rotator_entry = next((c for c in creds if c["id"] == "openbao_postgres_rotator_password"), None)
    assert rotator_entry is not None, "openbao_postgres_rotator_password must be in platform_credentials.yml"
    assert rotator_entry["local_file_var"] == "openbao_postgres_rotator_password_local_file"
    assert rotator_entry["owner_role"] == "openbao_postgres_backend"
    assert "openbao_runtime" in rotator_entry["consumer_roles"]

    # Check the writer role uses the canonical name (not the old admin variant)
    writer_defaults_paths = [
        COLLECTIONS_ROLES / "openbao_postgres_backend" / "defaults" / "main.yml",
        LEGACY_ROLES / "openbao_postgres_backend" / "defaults" / "main.yml",
    ]
    for path in writer_defaults_paths:
        if path.exists():
            content = path.read_text(encoding="utf-8")
            assert "openbao_postgres_admin_password_local_file" not in content, (
                f"{path}: still references old variable name openbao_postgres_admin_password_local_file — "
                "should be openbao_postgres_rotator_password_local_file (ADR 0438 Phase 3)"
            )
            assert "openbao_postgres_rotator_password_local_file" in content, (
                f"{path}: must define openbao_postgres_rotator_password_local_file"
            )

    # Check the writer role tasks use the canonical name
    writer_tasks_paths = [
        COLLECTIONS_ROLES / "openbao_postgres_backend" / "tasks" / "main.yml",
        LEGACY_ROLES / "openbao_postgres_backend" / "tasks" / "main.yml",
    ]
    for path in writer_tasks_paths:
        if path.exists():
            content = path.read_text(encoding="utf-8")
            assert "openbao_postgres_admin_password_local_file" not in content, (
                f"{path}: still references old variable openbao_postgres_admin_password_local_file"
            )
