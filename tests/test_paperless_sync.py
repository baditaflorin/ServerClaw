from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import paperless_sync  # noqa: E402


class FakeTaxonomyClient:
    def __init__(self, correspondents: list[dict], document_types: list[dict], tags: list[dict]) -> None:
        self.items = {
            "correspondents": list(correspondents),
            "document_types": list(document_types),
            "tags": list(tags),
        }
        self.calls: list[tuple[str, str, Any]] = []

    def list_taxonomy(self, kind: str) -> list[dict]:
        return [dict(item) for item in self.items[kind]]

    def create_taxonomy_item(self, kind: str, payload: dict) -> dict:
        new_id = len(self.items[kind]) + 1
        item = dict(payload, id=new_id)
        self.items[kind].append(item)
        self.calls.append(("create", kind, payload))
        return item

    def update_taxonomy_item(self, kind: str, item_id: int, payload: dict) -> dict:
        for item in self.items[kind]:
            if item["id"] == item_id:
                item.update(payload)
                break
        self.calls.append(("update", kind, payload))
        return dict(payload, id=item_id)


def desired_state() -> dict:
    return {
        "schema_version": "1.0.0",
        "correspondents": [
            {"id": "lv3-platform", "name": "LV3 Platform"},
            {"id": "external-vendor", "name": "External Vendor"},
        ],
        "document_types": [
            {"id": "invoice", "name": "Invoice"},
            {"id": "report", "name": "Report"},
        ],
        "tags": [
            {"id": "finance", "name": "finance"},
            {"id": "knowledge", "name": "knowledge"},
        ],
    }


def test_sync_creates_missing_taxonomy_items() -> None:
    client = FakeTaxonomyClient(correspondents=[], document_types=[], tags=[])

    report = paperless_sync.sync_taxonomy(client=client, desired_state=desired_state(), check_only=False)

    assert report["changed"] is True
    assert report["summary"]["correspondents_created"] == 2
    assert report["summary"]["document_types_created"] == 2
    assert report["summary"]["tags_created"] == 2
    assert any(call[0] == "create" for call in client.calls)


def test_sync_updates_drifted_taxonomy_items() -> None:
    client = FakeTaxonomyClient(
        correspondents=[{"id": 1, "name": "LV3 Platform", "matching_algorithm": 1}],
        document_types=[{"id": 1, "name": "Invoice", "matching_algorithm": 1}],
        tags=[{"id": 1, "name": "finance", "color": "#000000"}],
    )
    desired = desired_state()
    desired["correspondents"][0]["matching_algorithm"] = 6
    desired["document_types"][0]["matching_algorithm"] = 6
    desired["tags"][0]["color"] = "#ffffff"

    report = paperless_sync.sync_taxonomy(client=client, desired_state=desired, check_only=False)

    assert report["summary"]["correspondents_updated"] == 1
    assert report["summary"]["document_types_updated"] == 1
    assert report["summary"]["tags_updated"] == 1
    assert any(call[0] == "update" for call in client.calls)


def test_sync_check_only_reports_drift_without_mutating() -> None:
    client = FakeTaxonomyClient(correspondents=[], document_types=[], tags=[])

    report = paperless_sync.sync_taxonomy(client=client, desired_state=desired_state(), check_only=True)

    assert report["changed"] is True
    assert report["summary"]["correspondents_created"] == 2
    assert client.calls == []


def test_bootstrap_token_writes_file_when_missing(tmp_path: Path, monkeypatch) -> None:
    class StubClient:
        def __init__(self, base_url: str) -> None:
            self.base_url = base_url

        def create_token(self, username: str, password: str) -> str:
            assert username == "admin"
            assert password == "secret"
            return "paperless-token"

    monkeypatch.setattr(paperless_sync, "PaperlessClient", StubClient)
    password_file = tmp_path / "password.txt"
    token_file = tmp_path / "token.txt"
    password_file.write_text("secret\n", encoding="utf-8")

    report = paperless_sync.bootstrap_token("https://paperless.example", "admin", password_file, token_file)

    assert report["changed"] is True
    assert token_file.read_text(encoding="utf-8").strip() == "paperless-token"


def test_smoke_upload_creates_then_cleans_up_document(monkeypatch) -> None:
    class StubClient:
        def __init__(self, base_url: str, api_token: str | None = None) -> None:
            self.base_url = base_url
            self.api_token = api_token
            self.deleted: list[int] = []

        def upload_document(self, **kwargs):
            return {"task_id": "task-1"}

        def list_tasks(self, task_id: str):
            return [{"task_id": task_id, "related_document": 42}]

        def get_document(self, document_id: int):
            return {"id": document_id, "archive_serial_number": "test"}

        def list_documents(self, *, query: str | None = None):
            return []

        def delete_document(self, document_id: int) -> None:
            self.deleted.append(document_id)

    monkeypatch.setattr(paperless_sync, "PaperlessClient", StubClient)
    report = paperless_sync.smoke_upload("https://paperless.example", "token", cleanup=True)

    assert report["document_id"] == 42
    assert report["cleanup"] is True


def test_main_reads_api_token_file_and_writes_report(tmp_path: Path, monkeypatch) -> None:
    desired_file = tmp_path / "desired.json"
    api_token_file = tmp_path / "api-token.txt"
    report_file = tmp_path / "report.json"
    desired_file.write_text(json.dumps(desired_state()) + "\n", encoding="utf-8")
    api_token_file.write_text("secret\n", encoding="utf-8")

    captured: dict[str, str] = {}

    class StubClient:
        def __init__(self, base_url: str, api_token: str | None = None) -> None:
            captured["base_url"] = base_url
            captured["api_token"] = api_token or ""

    monkeypatch.setattr(paperless_sync, "PaperlessClient", StubClient)
    monkeypatch.setattr(
        paperless_sync,
        "sync_taxonomy",
        lambda **kwargs: {  # type: ignore[arg-type]
            "changed": False,
            "check_only": True,
            "summary": {},
            "actions": [],
            "unmanaged_live_items": {},
        },
    )

    exit_code = paperless_sync.main(
        [
            "verify",
            "--base-url",
            "http://127.0.0.1:8018",
            "--api-token-file",
            str(api_token_file),
            "--desired-state-file",
            str(desired_file),
            "--report-file",
            str(report_file),
        ]
    )

    assert exit_code == 0
    assert captured == {"base_url": "http://127.0.0.1:8018", "api_token": "secret"}
    assert json.loads(report_file.read_text(encoding="utf-8"))["changed"] is False
