from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import changedetection_sync  # noqa: E402


class FakeClient:
    def __init__(self, tags: dict[str, dict], watches: dict[str, dict]) -> None:
        self.tags = dict(tags)
        self.watches = dict(watches)
        self.calls: list[tuple[str, str, dict | None]] = []
        self._tag_counter = 1
        self._watch_counter = 1

    def list_tags(self) -> dict[str, dict]:
        return dict(self.tags)

    def get_tag(self, uuid: str) -> dict:
        return dict(self.tags[uuid])

    def create_tag(self, payload: dict) -> str:
        uuid = f"tag-{self._tag_counter}"
        self._tag_counter += 1
        self.tags[uuid] = dict(payload, uuid=uuid)
        self.calls.append(("create_tag", uuid, payload))
        return uuid

    def update_tag(self, uuid: str, payload: dict) -> None:
        self.tags[uuid] = dict(self.tags[uuid], **payload)
        self.calls.append(("update_tag", uuid, payload))

    def delete_tag(self, uuid: str) -> None:
        self.calls.append(("delete_tag", uuid, None))
        self.tags.pop(uuid)

    def list_watches(self) -> dict[str, dict]:
        return dict(self.watches)

    def get_watch(self, uuid: str) -> dict:
        return dict(self.watches[uuid])

    def create_watch(self, payload: dict) -> str:
        uuid = f"watch-{self._watch_counter}"
        self._watch_counter += 1
        self.watches[uuid] = dict(payload, uuid=uuid)
        self.calls.append(("create_watch", uuid, payload))
        return uuid

    def update_watch(self, uuid: str, payload: dict) -> None:
        self.watches[uuid] = dict(self.watches[uuid], **payload)
        self.calls.append(("update_watch", uuid, payload))

    def delete_watch(self, uuid: str) -> None:
        self.calls.append(("delete_watch", uuid, None))
        self.watches.pop(uuid)


def desired_state() -> dict:
    return {
        "schema_version": "1.0.0",
        "tags": [
            {
                "id": "upstream-releases",
                "title": "upstream-releases",
                "notification_urls": ["mmost://10.10.10.20:8065/token"],
                "notification_muted": False,
                "overrides_watch": True,
            },
            {
                "id": "security-advisories",
                "title": "security-advisories",
                "notification_urls": ["ntfy://changedetection:secret@10.10.10.20:2586/platform-security-warn?priority=high"],
                "notification_muted": False,
                "overrides_watch": True,
            },
        ],
        "watches": [
            {
                "id": "coolify-releases",
                "title": "Coolify Releases",
                "url": "https://github.com/coollabsio/coolify/releases.atom",
                "group": "upstream-releases",
                "interval_hours": 6,
                "notification_channel": "platform-ops",
                "reason": "Watch Coolify releases.",
            }
        ],
    }


def test_sync_creates_missing_tags_and_watches() -> None:
    client = FakeClient(tags={}, watches={})

    report = changedetection_sync.sync_changedetection(
        client=client,
        desired_state=desired_state(),
        check_only=False,
    )

    assert report["changed"] is True
    assert report["summary"]["tags_created"] == 2
    assert report["summary"]["watches_created"] == 1
    assert any(call[0] == "create_tag" for call in client.calls)
    assert any(call[0] == "create_watch" for call in client.calls)


def test_sync_updates_drifted_tags_and_watches() -> None:
    client = FakeClient(
        tags={
            "tag-1": {
                "uuid": "tag-1",
                "title": "upstream-releases",
                "notification_urls": [],
                "notification_muted": False,
                "overrides_watch": False,
            },
            "tag-2": {
                "uuid": "tag-2",
                "title": "security-advisories",
                "notification_urls": ["ntfy://wrong"],
                "notification_muted": False,
                "overrides_watch": True,
            },
        },
        watches={
            "watch-1": {
                "uuid": "watch-1",
                "url": "https://github.com/coollabsio/coolify/releases.atom",
                "title": "Old Coolify",
                "tags": ["tag-2"],
                "paused": False,
                "time_between_check_use_default": False,
                "time_between_check": {"hours": 1, "days": 0, "weeks": 0, "minutes": 0, "seconds": 0},
            }
        },
    )

    report = changedetection_sync.sync_changedetection(
        client=client,
        desired_state=desired_state(),
        check_only=False,
    )

    assert report["summary"]["tags_updated"] == 2
    assert report["summary"]["watches_updated"] == 1
    assert any(call[0] == "update_tag" for call in client.calls)
    assert any(call[0] == "update_watch" for call in client.calls)


def test_sync_deletes_unmanaged_tags_and_watches() -> None:
    client = FakeClient(
        tags={
            "tag-1": {
                "uuid": "tag-1",
                "title": "upstream-releases",
                "notification_urls": ["mmost://10.10.10.20:8065/token"],
                "notification_muted": False,
                "overrides_watch": True,
            },
            "tag-2": {
                "uuid": "tag-2",
                "title": "security-advisories",
                "notification_urls": ["ntfy://changedetection:secret@10.10.10.20:2586/platform-security-warn?priority=high"],
                "notification_muted": False,
                "overrides_watch": True,
            },
            "tag-3": {
                "uuid": "tag-3",
                "title": "manual-ui-tag",
            },
        },
        watches={
            "watch-1": {
                "uuid": "watch-1",
                "url": "https://github.com/coollabsio/coolify/releases.atom",
                "title": "Coolify Releases",
                "tags": ["tag-1"],
                "paused": False,
                "time_between_check_use_default": False,
                "time_between_check": {"hours": 6, "days": 0, "weeks": 0, "minutes": 0, "seconds": 0},
            },
            "watch-2": {
                "uuid": "watch-2",
                "url": "https://example.com/manual",
                "title": "Manual UI Watch",
                "tags": ["tag-3"],
                "paused": False,
                "time_between_check_use_default": False,
                "time_between_check": {"hours": 12, "days": 0, "weeks": 0, "minutes": 0, "seconds": 0},
            },
        },
    )

    report = changedetection_sync.sync_changedetection(
        client=client,
        desired_state=desired_state(),
        check_only=False,
    )

    assert report["summary"]["watches_deleted"] == 1
    assert report["summary"]["tags_deleted"] == 1
    assert ("delete_watch", "watch-2", None) in client.calls
    assert ("delete_tag", "tag-3", None) in client.calls


def test_sync_check_only_reports_drift_without_mutating() -> None:
    client = FakeClient(tags={}, watches={})

    report = changedetection_sync.sync_changedetection(
        client=client,
        desired_state=desired_state(),
        check_only=True,
    )

    assert report["changed"] is True
    assert report["summary"]["tags_created"] == 2
    assert report["summary"]["watches_created"] == 1
    assert client.calls == []


def test_sync_ignores_live_watch_defaults_not_declared_in_desired_state() -> None:
    client = FakeClient(
        tags={
            "tag-1": {
                "uuid": "tag-1",
                "title": "upstream-releases",
                "notification_urls": ["mmost://10.10.10.20:8065/token"],
                "notification_muted": False,
                "overrides_watch": True,
            },
            "tag-2": {
                "uuid": "tag-2",
                "title": "security-advisories",
                "notification_urls": ["ntfy://changedetection:secret@10.10.10.20:2586/platform-security-warn?priority=high"],
                "notification_muted": False,
                "overrides_watch": True,
            },
        },
        watches={
            "watch-1": {
                "uuid": "watch-1",
                "url": "https://github.com/coollabsio/coolify/releases.atom",
                "title": "Coolify Releases",
                "tags": ["tag-1"],
                "paused": False,
                "time_between_check_use_default": False,
                "time_between_check": {"hours": 6, "days": 0, "weeks": 0, "minutes": 0, "seconds": 0},
                "method": "GET",
                "fetch_backend": "system",
                "headers": {},
                "body": None,
                "notification_urls": [],
                "notification_title": None,
                "notification_body": None,
            }
        },
    )

    report = changedetection_sync.sync_changedetection(
        client=client,
        desired_state=desired_state(),
        check_only=True,
    )

    assert report["changed"] is False
    assert report["summary"]["watches_updated"] == 0
    assert client.calls == []


def test_main_reads_api_key_file_and_writes_report(tmp_path: Path) -> None:
    desired_file = tmp_path / "desired.json"
    api_key_file = tmp_path / "api-key.txt"
    report_file = tmp_path / "report.json"
    desired_file.write_text(json.dumps(desired_state()) + "\n", encoding="utf-8")
    api_key_file.write_text("secret\n", encoding="utf-8")

    captured: dict[str, str] = {}

    class StubClient:
        def __init__(self, base_url: str, api_key: str) -> None:
            captured["base_url"] = base_url
            captured["api_key"] = api_key

    original_client = changedetection_sync.ChangedetectionClient
    original_sync = changedetection_sync.sync_changedetection
    changedetection_sync.ChangedetectionClient = StubClient  # type: ignore[assignment]
    changedetection_sync.sync_changedetection = lambda **kwargs: {  # type: ignore[assignment]
        "changed": False,
        "check_only": True,
        "summary": {},
        "actions": [],
    }
    try:
        exit_code = changedetection_sync.main(
            [
                "--base-url",
                "http://127.0.0.1:5000",
                "--api-key-file",
                str(api_key_file),
                "--desired-state-file",
                str(desired_file),
                "--report-file",
                str(report_file),
                "--check-only",
            ]
        )
    finally:
        changedetection_sync.ChangedetectionClient = original_client  # type: ignore[assignment]
        changedetection_sync.sync_changedetection = original_sync  # type: ignore[assignment]

    assert exit_code == 0
    assert captured == {"base_url": "http://127.0.0.1:5000", "api_key": "secret"}
    assert json.loads(report_file.read_text(encoding="utf-8"))["changed"] is False
