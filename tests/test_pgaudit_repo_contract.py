from pathlib import Path
import re

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
APPROVED_ROLES_PATH = REPO_ROOT / "config" / "pgaudit" / "approved-roles.yaml"
SENSITIVE_TABLES_PATH = REPO_ROOT / "config" / "pgaudit" / "sensitive-tables.yaml"


SAFE_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


def test_approved_roles_are_unique_and_cover_live_high_risk_logins() -> None:
    payload = yaml.safe_load(APPROVED_ROLES_PATH.read_text())
    roles = payload["approved_roles"]

    assert roles == sorted(roles)
    assert len(roles) == len(set(roles))
    assert {
        "directus",
        "flagsmith",
        "n8n",
        "ops",
        "plausible",
        "postgres",
        "temporal",
        "windmill",
        "windmill_admin",
        "woodpecker",
    } <= set(roles)


def test_sensitive_table_catalog_uses_safe_identifiers_and_declares_expected_targets() -> None:
    payload = yaml.safe_load(SENSITIVE_TABLES_PATH.read_text())
    table_grants = payload["table_grants"]

    assert payload["audit_role"] == "pgaudit_auditor"
    assert len(table_grants) >= 10
    assert {"n8n", "windmill"} <= {entry["database"] for entry in table_grants}

    for entry in table_grants:
        assert SAFE_IDENTIFIER.fullmatch(entry["database"])
        assert SAFE_IDENTIFIER.fullmatch(entry["schema"])
        assert SAFE_IDENTIFIER.fullmatch(entry["table"])
        assert entry["service_roles"]
        assert entry["privileges"] == ["select", "insert", "update", "delete"]
