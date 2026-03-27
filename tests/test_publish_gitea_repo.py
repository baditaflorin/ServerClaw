import importlib
import io
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def load_publish_module():
    import publish_gitea_repo

    return importlib.reload(publish_gitea_repo)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


def test_fetch_repo_tree_entry_returns_matching_path(monkeypatch: pytest.MonkeyPatch) -> None:
    publish_gitea_repo = load_publish_module()

    payload = {
        "sha": "tree-sha",
        "tree": [
            {"path": "README.md", "type": "blob", "sha": "readme-sha"},
            {"path": ".gitea/workflows/renovate.yml", "type": "blob", "sha": "workflow-sha"},
        ],
    }

    captured = {}

    def fake_urlopen(request):
        captured["url"] = request.full_url
        captured["auth"] = request.headers["Authorization"]
        return FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(publish_gitea_repo.urllib.request, "urlopen", fake_urlopen)

    result = publish_gitea_repo.fetch_repo_tree_entry(
        "http://gitea.example",
        "ops",
        "repo",
        ".gitea/workflows/renovate.yml",
        "main",
        "token-123",
    )

    assert result == {"path": ".gitea/workflows/renovate.yml", "type": "blob", "sha": "workflow-sha"}
    assert captured["url"] == "http://gitea.example/api/v1/repos/ops/repo/git/trees/main?recursive=1"
    assert captured["auth"] == "token token-123"


def test_fetch_repo_tree_entry_raises_when_path_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    publish_gitea_repo = load_publish_module()

    payload = {"tree": [{"path": "README.md", "type": "blob", "sha": "readme-sha"}]}

    def fake_urlopen(_request):
        return FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(publish_gitea_repo.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(FileNotFoundError, match="config/renovate.json"):
        publish_gitea_repo.fetch_repo_tree_entry(
            "http://gitea.example",
            "ops",
            "repo",
            "config/renovate.json",
            "main",
            "token-123",
        )
