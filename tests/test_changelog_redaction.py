import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from deployment_history import query_deployment_history  # noqa: E402
from generate_changelog_portal import render_portal  # noqa: E402


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, payloads: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(item, sort_keys=True) for item in payloads]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_query_deployment_history_redacts_secret_and_pii_fields(tmp_path: Path) -> None:
    receipts_dir = tmp_path / "receipts" / "live-applies"
    promotions_dir = tmp_path / "receipts" / "promotions"
    mutation_audit_file = tmp_path / "fixtures" / "mutation-audit-sensitive.jsonl"

    write_json(
        receipts_dir / "2026-03-24-adr-0134-redaction-live-apply.json",
        {
            "schema_version": "1.0.0",
            "receipt_id": "2026-03-24-adr-0134-redaction-live-apply",
            "applied_on": "2026-03-24",
            "recorded_on": "2026-03-24",
            "recorded_by": "ops.contractor@example.com",
            "workflow_id": "converge-windmill",
            "adr": "0134",
            "summary": (
                "Applied Windmill on docker-runtime-lv3 for ops.contractor@example.com "
                "using db_password=swordfish and token test-openbao-token at 10.10.10.20."
            ),
            "targets": [
                {"kind": "vm", "name": "docker-runtime-lv3", "address": "10.10.10.20"},
                {"kind": "internal_hostname", "name": "netbox-vm.lv3.internal"},
            ],
            "verification": [
                {
                    "check": "stack trace omitted from portal",
                    "result": "fail",
                    "observed": 'Traceback (most recent call last): File "/Users/live/tmp.py", line 12, in run',
                }
            ],
            "evidence_refs": ["https://10.10.10.20:8200/v1/auth", "docs/runbooks/windmill.md"],
            "notes": ["Set client_secret=supersecret and notified ops.contractor@example.com."],
        },
    )

    write_jsonl(
        mutation_audit_file,
        [
            {
                "ts": "2026-03-24T10:15:00Z",
                "actor": {"class": "operator", "id": "alice@example.com"},
                "surface": "manual",
                "action": "windmill.reconfigure",
                "target": "netbox-vm.lv3.internal",
                "outcome": "failure",
                "correlation_id": "manual:redaction:20260324",
                "evidence_ref": "https://10.10.10.20/logs",
                "params": {"db_password": "hunter2", "host": "netbox-vm.lv3.internal"},
                "env_vars": {"API_URL": "https://10.10.10.20", "OPENBAO_TOKEN": "hvs.secretvalue"},
                "error_detail": "client_secret=topsecret for alice@example.com on 10.10.10.20",
                "stack_trace": 'Traceback (most recent call last): File "/Users/live/app.py", line 9, in main',
                "job_payload": {"secret": "value", "path": "/Users/live/private"},
            }
        ],
    )

    result = query_deployment_history(
        days=30,
        receipts_dir=receipts_dir,
        promotions_dir=promotions_dir,
        mutation_audit_file=mutation_audit_file,
    )

    receipt_entry = next(entry for entry in result["entries"] if entry["change_type"] == "live-apply")
    audit_entry = next(entry for entry in result["entries"] if entry["change_type"] == "manual")

    assert receipt_entry["actor"] == "ops.contractor"
    assert "ops.contractor@example.com" not in receipt_entry["summary"]
    assert "swordfish" not in receipt_entry["summary"]
    assert "10.10.10.20" not in receipt_entry["summary"]
    assert "docker-runtime-lv3" not in receipt_entry["summary"]
    assert "docker-runtime" in receipt_entry["summary"]
    assert receipt_entry["targets"] == ["vm:docker-runtime", "internal_hostname:netbox"]

    assert audit_entry["actor"] == "alice"
    assert audit_entry["summary"] == "manual windmill.reconfigure on netbox"
    assert audit_entry["metadata"]["params"] == "{2 params}"
    assert audit_entry["metadata"]["env_vars"] == "API_URL, OPENBAO_TOKEN"
    assert audit_entry["metadata"]["error_detail"] == "[details omitted]"
    assert audit_entry["metadata"]["stack_trace"] == "[details omitted]"
    assert audit_entry["metadata"]["job_payload"] == "[details omitted]"
    assert audit_entry["metadata"]["evidence_ref"] == "https://[redacted ip]/logs"


def test_render_portal_omits_raw_secret_and_pii_content(tmp_path: Path) -> None:
    receipts_dir = tmp_path / "receipts" / "live-applies"
    promotions_dir = tmp_path / "receipts" / "promotions"
    mutation_audit_file = tmp_path / "fixtures" / "mutation-audit-sensitive.jsonl"

    write_json(
        receipts_dir / "2026-03-24-adr-0134-redaction-live-apply.json",
        {
            "schema_version": "1.0.0",
            "receipt_id": "2026-03-24-adr-0134-redaction-live-apply",
            "applied_on": "2026-03-24",
            "recorded_on": "2026-03-24",
            "recorded_by": "ops.contractor@example.com",
            "workflow_id": "converge-netbox",
            "adr": "0134",
            "summary": (
                "Applied NetBox on docker-runtime-lv3 with password=plaintext "
                "and contacted alice@example.com via 10.10.10.20."
            ),
            "targets": [{"kind": "vm", "name": "docker-runtime-lv3", "address": "10.10.10.20"}],
            "verification": [],
            "evidence_refs": ["docs/runbooks/netbox.md"],
            "notes": [],
        },
    )

    write_jsonl(
        mutation_audit_file,
        [
            {
                "ts": "2026-03-24T11:15:00Z",
                "actor": {"class": "operator", "id": "alice@example.com"},
                "surface": "manual",
                "action": "netbox.sync",
                "target": "netbox-vm.lv3.internal",
                "outcome": "success",
                "correlation_id": "manual:redaction:portal",
                "evidence_ref": "https://10.10.10.20/logs",
            }
        ],
    )

    render_portal(
        tmp_path / "site",
        receipts_dir=receipts_dir,
        promotions_dir=promotions_dir,
        mutation_audit_file=mutation_audit_file,
    )
    index_html = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")

    assert "ops.contractor@example.com" not in index_html
    assert "alice@example.com" not in index_html
    assert "password=plaintext" not in index_html
    assert "10.10.10.20" not in index_html
    assert "docker-runtime-lv3" not in index_html
    assert "netbox-vm.lv3.internal" not in index_html
    assert "ops.contractor" in index_html
    assert "[redacted]" in index_html
    assert "docker-runtime" in index_html
    assert "netbox" in index_html
