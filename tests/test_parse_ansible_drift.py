from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import parse_ansible_drift as parser  # noqa: E402


def test_parse_ansible_json_payload_detects_changed_and_unreachable() -> None:
    payload = {
        "plays": [
            {
                "tasks": [
                    {
                        "task": {"name": "openbao_runtime : render config"},
                        "hosts": {
                            "docker-runtime": {
                                "changed": True,
                                "diff": [{"before": "old", "after": "new"}],
                            }
                        },
                    },
                    {
                        "task": {"name": "wait_for_connection"},
                        "hosts": {
                            "monitoring": {
                                "unreachable": True,
                                "msg": "ssh failed",
                            }
                        },
                    },
                ]
            }
        ]
    }

    records = parser.parse_ansible_output(json.dumps(payload))

    assert records[0]["role"] == "openbao_runtime"
    assert records[0]["task"] == "render config"
    assert records[0]["diff_before"] == "old"
    assert records[0]["severity"] == "warn"
    assert records[1]["type"] == "unreachable"
    assert records[1]["event"] == "platform.drift.unreachable"


def test_parse_ansible_text_payload_detects_changed_task() -> None:
    payload = """
PLAY [all] *********************************************************************

TASK [windmill_runtime : render compose] ****************************************
--- before
+++ after
changed: [docker-runtime]
""".strip()

    records = parser.parse_ansible_output(payload)

    assert len(records) == 1
    assert records[0]["role"] == "windmill_runtime"
    assert records[0]["task"] == "render compose"
    assert records[0]["host"] == "docker-runtime"


def test_parse_ansible_output_handles_empty_input() -> None:
    assert parser.parse_ansible_output("") == []
