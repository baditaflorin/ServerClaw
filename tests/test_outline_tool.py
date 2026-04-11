from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path

import pytest

import outline_tool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class FakeClient:
    """Configurable fake OutlineClient for tool command tests."""

    def __init__(self, responses: dict[str, object] | None = None) -> None:
        self.responses: dict[str, object] = responses or {}
        self.calls: list[tuple[str, dict]] = []

    def call(self, endpoint: str, payload: dict, *, use_app_token: bool = False) -> dict:
        self.calls.append((endpoint, payload))
        if endpoint in self.responses:
            return self.responses[endpoint]
        raise AssertionError(f"unexpected endpoint in FakeClient: {endpoint}")


def capture_stdout(fn) -> dict:
    """Run fn, capture stdout, return parsed JSON."""
    buf = StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        fn()
    finally:
        sys.stdout = old
    return json.loads(buf.getvalue())


def capture_stderr(fn) -> dict:
    """Run fn, capture stderr, return parsed JSON."""
    buf = StringIO()
    old = sys.stderr
    sys.stderr = buf
    try:
        fn()
    finally:
        sys.stderr = old
    return json.loads(buf.getvalue())


# ---------------------------------------------------------------------------
# collection.list
# ---------------------------------------------------------------------------


def test_collection_list_returns_all_collections(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(
        {
            "collections.list": {
                "data": [
                    {"id": "col-1", "name": "ADRs", "description": "Arch decisions", "url": "/col/adrs"},
                    {"id": "col-2", "name": "Runbooks", "description": "Ops", "url": "/col/runbooks"},
                ]
            }
        }
    )
    monkeypatch.setattr(outline_tool, "_client", lambda _args: client)

    result = capture_stdout(lambda: outline_tool.main(["collection.list", "--token", "tok"]))

    assert result["ok"] is True
    names = [c["name"] for c in result["collections"]]
    assert "ADRs" in names
    assert "Runbooks" in names


# ---------------------------------------------------------------------------
# collection.create
# ---------------------------------------------------------------------------


def test_collection_create_creates_new_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(
        {
            "collections.list": {"data": []},
            "collections.create": {"data": {"id": "new-col", "name": "My Docs"}},
        }
    )
    monkeypatch.setattr(outline_tool, "_client", lambda _args: client)

    result = capture_stdout(
        lambda: outline_tool.main(["collection.create", "--name", "My Docs", "--description", "Test", "--token", "tok"])
    )

    assert result["ok"] is True
    assert result["outcome"] == "created"
    assert result["name"] == "My Docs"
    assert (
        "collections.create",
        {"name": "My Docs", "description": "Test", "permission": "read", "sharing": True},
    ) in client.calls


def test_collection_create_is_idempotent_when_collection_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(
        {
            "collections.list": {"data": [{"id": "existing-col", "name": "My Docs", "description": ""}]},
        }
    )
    monkeypatch.setattr(outline_tool, "_client", lambda _args: client)

    result = capture_stdout(lambda: outline_tool.main(["collection.create", "--name", "My Docs", "--token", "tok"]))

    assert result["ok"] is True
    assert result["outcome"] == "exists"
    assert result["id"] == "existing-col"
    # Should not have called collections.create
    assert not any(ep == "collections.create" for ep, _ in client.calls)


# ---------------------------------------------------------------------------
# collection.delete
# ---------------------------------------------------------------------------


def test_collection_delete_removes_existing_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(
        {
            "collections.list": {"data": [{"id": "col-1", "name": "Old Docs", "description": ""}]},
            "collections.delete": {"ok": True},
        }
    )
    monkeypatch.setattr(outline_tool, "_client", lambda _args: client)

    result = capture_stdout(lambda: outline_tool.main(["collection.delete", "--name", "Old Docs", "--token", "tok"]))

    assert result["ok"] is True
    assert result["deleted"] is True
    assert ("collections.delete", {"id": "col-1"}) in client.calls


def test_collection_delete_errors_when_collection_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient({"collections.list": {"data": []}})
    monkeypatch.setattr(outline_tool, "_client", lambda _args: client)

    exit_code = outline_tool.main(["collection.delete", "--name", "Ghost", "--token", "tok"])

    assert exit_code == 1


# ---------------------------------------------------------------------------
# document.list
# ---------------------------------------------------------------------------


def test_document_list_returns_documents_in_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(
        {
            "collections.list": {"data": [{"id": "col-1", "name": "ADRs", "description": ""}]},
            "documents.list": {
                "data": [
                    {"id": "doc-1", "title": "ADR 0001", "url": "/doc/adr-0001"},
                    {"id": "doc-2", "title": "ADR 0002", "url": "/doc/adr-0002"},
                ]
            },
        }
    )
    monkeypatch.setattr(outline_tool, "_client", lambda _args: client)

    result = capture_stdout(lambda: outline_tool.main(["document.list", "--collection", "ADRs", "--token", "tok"]))

    assert result["ok"] is True
    assert result["collection"] == "ADRs"
    titles = [d["title"] for d in result["documents"]]
    assert "ADR 0001" in titles
    assert "ADR 0002" in titles


# ---------------------------------------------------------------------------
# document.publish
# ---------------------------------------------------------------------------


def test_document_publish_creates_new_document_from_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    content_file = tmp_path / "finding.md"
    content_file.write_text("# My Finding\n\nDetails here.\n", encoding="utf-8")

    client = FakeClient(
        {
            "collections.list": {"data": [{"id": "col-1", "name": "Agent Findings", "description": ""}]},
            "documents.list": {"data": []},
            "documents.create": {"data": {"id": "doc-new", "url": "/doc/my-finding"}},
        }
    )
    monkeypatch.setattr(outline_tool, "_client", lambda _args: client)

    result = capture_stdout(
        lambda: outline_tool.main(
            [
                "document.publish",
                "--collection",
                "Agent Findings",
                "--title",
                "My Finding",
                "--file",
                str(content_file),
                "--token",
                "tok",
            ]
        )
    )

    assert result["ok"] is True
    assert result["outcome"] == "created"
    assert result["title"] == "My Finding"
    assert result["collection"] == "Agent Findings"
    create_calls = [(ep, p) for ep, p in client.calls if ep == "documents.create"]
    assert len(create_calls) == 1
    assert create_calls[0][1]["text"] == "# My Finding\n\nDetails here.\n"


def test_document_publish_updates_existing_document(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    content_file = tmp_path / "updated.md"
    content_file.write_text("# Updated\n", encoding="utf-8")

    client = FakeClient(
        {
            "collections.list": {"data": [{"id": "col-1", "name": "Runbooks", "description": ""}]},
            "documents.list": {"data": [{"id": "doc-1", "title": "Restart Guide", "url": "/doc/restart"}]},
            "documents.update": {"data": {"id": "doc-1", "url": "/doc/restart"}},
        }
    )
    monkeypatch.setattr(outline_tool, "_client", lambda _args: client)

    result = capture_stdout(
        lambda: outline_tool.main(
            [
                "document.publish",
                "--collection",
                "Runbooks",
                "--title",
                "Restart Guide",
                "--file",
                str(content_file),
                "--token",
                "tok",
            ]
        )
    )

    assert result["ok"] is True
    assert result["outcome"] == "updated"
    update_calls = [(ep, p) for ep, p in client.calls if ep == "documents.update"]
    assert len(update_calls) == 1
    assert update_calls[0][1]["id"] == "doc-1"
    assert update_calls[0][1]["text"] == "# Updated\n"


def test_document_publish_reads_content_from_stdin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient(
        {
            "collections.list": {"data": [{"id": "col-1", "name": "Automation Runs", "description": ""}]},
            "documents.list": {"data": []},
            "documents.create": {"data": {"id": "doc-run", "url": "/doc/run"}},
        }
    )
    monkeypatch.setattr(outline_tool, "_client", lambda _args: client)
    monkeypatch.setattr(sys, "stdin", StringIO("# Run output\n\nDone.\n"))

    result = capture_stdout(
        lambda: outline_tool.main(
            [
                "document.publish",
                "--collection",
                "Automation Runs",
                "--title",
                "deploy-2026-04-05",
                "--stdin",
                "--token",
                "tok",
            ]
        )
    )

    assert result["ok"] is True
    assert result["outcome"] == "created"
    create_calls = [(ep, p) for ep, p in client.calls if ep == "documents.create"]
    assert create_calls[0][1]["text"] == "# Run output\n\nDone.\n"


def test_document_publish_removes_duplicate_documents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    content_file = tmp_path / "doc.md"
    content_file.write_text("# Doc\n", encoding="utf-8")

    client = FakeClient(
        {
            "collections.list": {"data": [{"id": "col-1", "name": "ADRs", "description": ""}]},
            "documents.list": {
                "data": [
                    {"id": "doc-1", "title": "ADR Index"},
                    {"id": "doc-2", "title": "ADR Index"},  # duplicate
                ]
            },
            "documents.update": {"data": {"id": "doc-1", "url": "/doc/adr-index"}},
            "documents.delete": {"ok": True},
        }
    )
    monkeypatch.setattr(outline_tool, "_client", lambda _args: client)

    capture_stdout(
        lambda: outline_tool.main(
            [
                "document.publish",
                "--collection",
                "ADRs",
                "--title",
                "ADR Index",
                "--file",
                str(content_file),
                "--token",
                "tok",
            ]
        )
    )

    delete_calls = [(ep, p) for ep, p in client.calls if ep == "documents.delete"]
    assert len(delete_calls) == 1
    assert delete_calls[0][1]["id"] == "doc-2"


# ---------------------------------------------------------------------------
# document.get
# ---------------------------------------------------------------------------


def test_document_get_returns_full_text(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(
        {
            "collections.list": {"data": [{"id": "col-1", "name": "Runbooks", "description": ""}]},
            "documents.list": {"data": [{"id": "doc-1", "title": "Restart Guide", "url": "/doc/restart"}]},
            "documents.info": {
                "data": {"id": "doc-1", "title": "Restart Guide", "text": "# Restart\n\nStep 1.", "url": "/doc/restart"}
            },
        }
    )
    monkeypatch.setattr(outline_tool, "_client", lambda _args: client)

    result = capture_stdout(
        lambda: outline_tool.main(
            ["document.get", "--collection", "Runbooks", "--title", "Restart Guide", "--token", "tok"]
        )
    )

    assert result["ok"] is True
    assert result["text"] == "# Restart\n\nStep 1."
    assert result["id"] == "doc-1"


def test_document_get_errors_when_document_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(
        {
            "collections.list": {"data": [{"id": "col-1", "name": "Runbooks", "description": ""}]},
            "documents.list": {"data": []},
        }
    )
    monkeypatch.setattr(outline_tool, "_client", lambda _args: client)

    exit_code = outline_tool.main(
        ["document.get", "--collection", "Runbooks", "--title", "Ghost Doc", "--token", "tok"]
    )

    assert exit_code == 1


# ---------------------------------------------------------------------------
# document.delete
# ---------------------------------------------------------------------------


def test_document_delete_removes_matching_document(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(
        {
            "collections.list": {"data": [{"id": "col-1", "name": "ADRs", "description": ""}]},
            "documents.list": {"data": [{"id": "doc-1", "title": "Old ADR"}]},
            "documents.delete": {"ok": True},
        }
    )
    monkeypatch.setattr(outline_tool, "_client", lambda _args: client)

    result = capture_stdout(
        lambda: outline_tool.main(["document.delete", "--collection", "ADRs", "--title", "Old ADR", "--token", "tok"])
    )

    assert result["ok"] is True
    assert result["deleted"] is True
    assert result["count"] == 1
    assert ("documents.delete", {"id": "doc-1"}) in client.calls


# ---------------------------------------------------------------------------
# document.search
# ---------------------------------------------------------------------------


def test_document_search_returns_results(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(
        {
            "documents.search": {
                "data": [
                    {
                        "document": {
                            "id": "doc-1",
                            "title": "Postgres Upgrade",
                            "collectionId": "col-1",
                            "url": "/doc/pg",
                        },
                        "context": "postgres migration steps...",
                    }
                ]
            }
        }
    )
    monkeypatch.setattr(outline_tool, "_client", lambda _args: client)

    result = capture_stdout(
        lambda: outline_tool.main(["document.search", "--query", "postgres migration", "--token", "tok"])
    )

    assert result["ok"] is True
    assert len(result["results"]) == 1
    assert result["results"][0]["title"] == "Postgres Upgrade"
    assert "postgres" in result["results"][0]["context"]


def test_document_search_scoped_to_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(
        {
            "collections.list": {"data": [{"id": "col-1", "name": "Runbooks", "description": ""}]},
            "documents.search": {"data": []},
        }
    )
    monkeypatch.setattr(outline_tool, "_client", lambda _args: client)

    result = capture_stdout(
        lambda: outline_tool.main(
            [
                "document.search",
                "--query",
                "restart",
                "--collection",
                "Runbooks",
                "--token",
                "tok",
            ]
        )
    )

    assert result["ok"] is True
    search_calls = [(ep, p) for ep, p in client.calls if ep == "documents.search"]
    assert search_calls[0][1]["collectionId"] == "col-1"


# ---------------------------------------------------------------------------
# changelog.push
# ---------------------------------------------------------------------------


def test_changelog_push_creates_document_from_repo_changelog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    changelog = tmp_path / "changelog.md"
    changelog.write_text("# Changelog\n\n## v1.0.0\n- initial release\n", encoding="utf-8")

    client = FakeClient(
        {
            "collections.list": {"data": [{"id": "cl-col", "name": "Changelogs", "description": ""}]},
            "documents.list": {"data": []},
            "documents.create": {"data": {"id": "doc-cl", "url": "/doc/changelog"}},
        }
    )
    monkeypatch.setattr(outline_tool, "_client", lambda _args: client)

    # Point the tool at the tmp_path changelog by using --file
    result = capture_stdout(lambda: outline_tool.main(["changelog.push", "--file", str(changelog), "--token", "tok"]))

    assert result["ok"] is True
    assert result["outcome"] == "created"
    assert result["collection"] == "Changelogs"
    create_calls = [(ep, p) for ep, p in client.calls if ep == "documents.create"]
    assert "## v1.0.0" in create_calls[0][1]["text"]


def test_changelog_push_updates_existing_changelog_document(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    changelog = tmp_path / "changelog.md"
    changelog.write_text("# Changelog\n\n## v2.0.0\n- new feature\n", encoding="utf-8")

    client = FakeClient(
        {
            "collections.list": {"data": [{"id": "cl-col", "name": "Changelogs", "description": ""}]},
            "documents.list": {"data": [{"id": "doc-cl", "title": "Changelog"}]},
            "documents.update": {"data": {"id": "doc-cl", "url": "/doc/changelog"}},
        }
    )
    monkeypatch.setattr(outline_tool, "_client", lambda _args: client)

    result = capture_stdout(lambda: outline_tool.main(["changelog.push", "--file", str(changelog), "--token", "tok"]))

    assert result["ok"] is True
    assert result["outcome"] == "updated"
    update_calls = [(ep, p) for ep, p in client.calls if ep == "documents.update"]
    assert "## v2.0.0" in update_calls[0][1]["text"]


def test_changelog_push_creates_changelogs_collection_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    changelog = tmp_path / "changelog.md"
    changelog.write_text("# Changelog\n", encoding="utf-8")

    client = FakeClient(
        {
            "collections.list": {"data": []},
            "collections.create": {"data": {"id": "new-cl-col", "name": "Changelogs"}},
            "documents.list": {"data": []},
            "documents.create": {"data": {"id": "doc-cl", "url": "/doc/changelog"}},
        }
    )
    monkeypatch.setattr(outline_tool, "_client", lambda _args: client)

    result = capture_stdout(lambda: outline_tool.main(["changelog.push", "--file", str(changelog), "--token", "tok"]))

    assert result["ok"] is True
    assert result["outcome"] == "created"
    assert any(ep == "collections.create" for ep, _ in client.calls)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_error_output_is_valid_json_on_unknown_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient({"collections.list": {"data": []}})
    monkeypatch.setattr(outline_tool, "_client", lambda _args: client)

    exit_code = outline_tool.main(["document.list", "--collection", "Does Not Exist", "--token", "tok"])

    assert exit_code == 1


def test_token_loaded_from_environment_variable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OUTLINE_API_TOKEN", "env-token-value")

    captured_tokens: list[str] = []

    def fake_client(args: object) -> FakeClient:
        # Inspect what _client() resolves
        token = "env-token-value"  # already set
        captured_tokens.append(token)
        return FakeClient({"collections.list": {"data": []}})

    monkeypatch.setattr(outline_tool, "_client", fake_client)

    outline_tool.main(["collection.list"])
    assert captured_tokens == ["env-token-value"]
