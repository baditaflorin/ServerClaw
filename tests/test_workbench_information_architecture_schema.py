import json
from pathlib import Path

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "docs" / "schema" / "workbench-information-architecture.schema.json"
CONFIG_PATH = REPO_ROOT / "config" / "workbench-information-architecture.json"


def test_workbench_information_architecture_matches_schema() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    jsonschema.validate(instance=payload, schema=schema)
