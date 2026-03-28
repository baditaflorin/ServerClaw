from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import sync_docs_to_outline as outline_sync


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_repo(root: Path) -> None:
    write(root / "README.md", "# Repo\n")
    write(root / "AGENTS.md", "# Agents\n")
    write(root / ".repo-structure.yaml", "root: {}\n")
    write(root / ".config-locations.yaml", "config: {}\n")
    write(root / "docs" / "adr" / ".index.yaml", "adr_index: []\n")
    write(root / "workstreams.yaml", "workstreams: []\n")
    write(
        root / "docs" / "adr" / "0001-example.md",
        """# ADR 0001: Example

- Status: Accepted
- Implementation Status: Implemented
""",
    )
    write(root / "docs" / "runbooks" / "restart-service.md", "# Restart Service\n")


class FakeResponse:
    def __init__(self, body: str, url: str) -> None:
        self._body = body
        self._url = url

    def read(self) -> bytes:
        return self._body.encode("utf-8")

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FakeOpener:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[object] = []

    def open(self, request, timeout: int = 60):
        self.calls.append(request)
        return self.responses.pop(0)


def test_outline_client_uses_urlopen_when_bearer_token_auth_is_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout: int = 60):
        captured["request"] = req
        captured["timeout"] = timeout
        return FakeResponse('{"ok": true}', req.full_url)

    monkeypatch.setattr(outline_sync.request, "urlopen", fake_urlopen)

    client = outline_sync.OutlineClient("https://wiki.example", api_token="outline-api-token")
    response = client.call("collections.list", {})

    assert response == {"ok": True}
    assert captured["timeout"] == 60
    req = captured["request"]
    assert req.full_url == "https://wiki.example/api/collections.list"
    assert req.get_header("Authorization") == "Bearer outline-api-token"


def test_bootstrap_token_uses_oidc_session_cookie_to_create_an_api_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    password_file = tmp_path / "operator-password.txt"
    token_file = tmp_path / "api-token.txt"
    password_file.write_text("super-secret\n", encoding="utf-8")
    opener = FakeOpener(
        [
            FakeResponse(
                '<form id="kc-form-login" action="https://sso.example/login"><input name="session_code" value="abc"></form>',
                "https://sso.example/login",
            ),
            FakeResponse("", "https://wiki.example/auth/oidc.callback"),
        ]
    )
    jar = [SimpleNamespace(name="csrfToken", value="csrf-cookie-value")]
    calls: list[tuple[str, dict[str, object], bool, object, object]] = []

    monkeypatch.setattr(outline_sync, "build_opener", lambda: (opener, jar))

    def fake_call(self, endpoint: str, payload: dict[str, object], *, use_app_token: bool = False):
        calls.append((endpoint, payload, use_app_token, self.opener, self.csrf_token))
        return {"data": {"value": "outline-api-token"}}

    monkeypatch.setattr(outline_sync.OutlineClient, "call", fake_call)

    exit_code = outline_sync.bootstrap_token(
        "https://wiki.example",
        "florin.badita",
        password_file,
        "lv3-outline-sync",
        token_file,
        ["collections.create"],
    )

    assert exit_code == 0
    assert token_file.read_text(encoding="utf-8").strip() == "outline-api-token"
    assert len(opener.calls) == 2
    assert calls == [
        (
            "apiKeys.create",
            {"name": "lv3-outline-sync", "scope": ["collections.create"]},
            True,
            opener,
            "csrf-cookie-value",
        )
    ]


def test_landing_docs_render_repo_indexes_from_canonical_files(tmp_path: Path) -> None:
    build_repo(tmp_path)

    landing = {spec.slug: markdown for spec, markdown in outline_sync.landing_docs(tmp_path)}

    assert "docs/adr/0001-example.md" in landing["adrs"]
    assert "Status: `Accepted`" in landing["adrs"]
    assert "docs/runbooks/restart-service.md" in landing["runbooks"]
    assert "README.md" in landing["architecture"]


def test_verify_confirms_expected_collections_and_titles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_repo(tmp_path)
    token_file = tmp_path / ".local" / "outline" / "api-token.txt"
    write(token_file, "outline-api-token\n")

    class FakeClient:
        def __init__(
            self,
            base_url: str,
            *,
            api_token: str | None = None,
            app_token: str | None = None,
            opener=None,
            csrf_token: str | None = None,
        ) -> None:
            self.base_url = base_url
            self.api_token = api_token
            self.app_token = app_token
            self.opener = opener
            self.csrf_token = csrf_token

        def call(self, endpoint: str, payload: dict[str, object], *, use_app_token: bool = False):
            if endpoint == "collections.list":
                return {"data": [{"name": spec.name, "id": spec.slug} for spec in outline_sync.COLLECTION_SPECS]}
            if endpoint == "documents.list":
                return {
                    "data": [
                        {
                            "id": f"{payload['collectionId']}-landing",
                            "title": next(
                                spec.landing_title
                                for spec in outline_sync.COLLECTION_SPECS
                                if spec.slug == payload["collectionId"]
                            ),
                        }
                    ]
                }
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(outline_sync, "OutlineClient", FakeClient)

    assert outline_sync.verify(tmp_path, "https://wiki.example", token_file) == 0


def test_ensure_document_updates_existing_collection_landing_page() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeClient:
        def call(self, endpoint: str, payload: dict[str, object], *, use_app_token: bool = False):
            calls.append((endpoint, payload))
            if endpoint == "documents.list":
                return {
                    "data": [
                        {"id": "doc-1", "title": "ADR Index"},
                        {"id": "doc-2", "title": "ADR Index"},
                    ]
                }
            if endpoint == "documents.update":
                return {"ok": True}
            if endpoint == "documents.delete":
                return {"ok": True}
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    outcome = outline_sync.ensure_document(
        FakeClient(),
        collection_id="collection-1",
        title="ADR Index",
        markdown="# ADR Index\n",
        dry_run=False,
    )

    assert outcome == "updated"
    assert calls == [
        ("documents.list", {"collectionId": "collection-1"}),
        (
            "documents.update",
            {
                "id": "doc-1",
                "title": "ADR Index",
                "text": "# ADR Index\n",
                "publish": True,
                "done": True,
            },
        ),
        ("documents.delete", {"id": "doc-2"}),
    ]


def test_sync_dry_run_skips_document_lookup_for_new_collections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_repo(tmp_path)
    token_file = tmp_path / ".local" / "outline" / "api-token.txt"
    write(token_file, "outline-api-token\n")
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeClient:
        def __init__(
            self,
            base_url: str,
            *,
            api_token: str | None = None,
            app_token: str | None = None,
            opener=None,
            csrf_token: str | None = None,
        ) -> None:
            self.base_url = base_url
            self.api_token = api_token
            self.app_token = app_token
            self.opener = opener
            self.csrf_token = csrf_token

        def call(self, endpoint: str, payload: dict[str, object], *, use_app_token: bool = False):
            calls.append((endpoint, payload))
            if endpoint == "collections.list":
                return {"data": []}
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(outline_sync, "OutlineClient", FakeClient)

    assert outline_sync.sync(tmp_path, "https://wiki.example", token_file, dry_run=True) == 0
    assert calls == [("collections.list", {}) for _ in outline_sync.COLLECTION_SPECS]


def test_cleanup_bootstrap_collections_removes_default_welcome_collection() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeClient:
        def call(self, endpoint: str, payload: dict[str, object], *, use_app_token: bool = False):
            calls.append((endpoint, payload))
            if endpoint == "collections.list":
                return {"data": [{"id": "welcome-1", "name": "Welcome"}]}
            if endpoint == "collections.delete":
                return {"ok": True}
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    assert outline_sync.cleanup_bootstrap_collections(FakeClient()) == ["Welcome collection deleted"]
    assert calls == [
        ("collections.list", {}),
        ("collections.delete", {"id": "welcome-1"}),
    ]
