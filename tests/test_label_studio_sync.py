import importlib.util
import json
from pathlib import Path
from urllib import error


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "label_studio_sync.py"
SPEC = importlib.util.spec_from_file_location("label_studio_sync", SCRIPT_PATH)
label_studio_sync = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(label_studio_sync)


def test_load_catalog_accepts_dict_payload_and_normalizes_ids(tmp_path: Path) -> None:
    catalog_path = tmp_path / "projects.json"
    catalog_path.write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "title": "Example",
                        "description": " Example description ",
                        "label_config": " <View></View> ",
                    }
                ]
            }
        )
    )

    catalog = label_studio_sync.load_catalog(catalog_path)

    assert catalog == [
        {
            "id": "Example",
            "title": "Example",
            "description": "Example description",
            "label_config": "<View></View>",
        }
    ]


def test_build_sync_plan_detects_creates_updates_and_unmanaged_projects() -> None:
    desired = [
        {"id": "alpha", "title": "Alpha", "description": "New", "label_config": "<View>A</View>"},
        {"id": "beta", "title": "Beta", "description": "Wanted", "label_config": "<View>B</View>"},
    ]
    existing = [
        {"id": 7, "title": "Beta", "description": "Old", "label_config": "<View>B</View>"},
        {"id": 8, "title": "Gamma", "description": "Keep", "label_config": "<View>G</View>"},
    ]

    plan = label_studio_sync.build_sync_plan(desired, existing)

    assert [item["catalog_id"] for item in plan["updates"]] == ["beta"]
    assert [item["id"] for item in plan["creates"]] == ["alpha"]
    assert plan["unmanaged"] == ["Gamma"]
    assert plan["changed"] is True


def test_apply_sync_plan_issues_post_and_patch_requests(monkeypatch) -> None:
    calls: list[tuple[str, str, dict]] = []

    def fake_request_json(method: str, url: str, token: str, body=None, expected_status=(200,)):
        calls.append((method, url, body))
        return {"ok": True, "url": url}

    monkeypatch.setattr(label_studio_sync, "request_json", fake_request_json)
    plan = {
        "creates": [{"id": "alpha", "payload": {"title": "Alpha", "description": "Create", "label_config": "<View/>"}}],
        "updates": [{"id": 17, "catalog_id": "beta", "payload": {"description": "Update"}}],
    }

    applied = label_studio_sync.apply_sync_plan("http://label-studio.internal", "token", plan)

    assert calls == [
        (
            "POST",
            "http://label-studio.internal/api/projects",
            {"title": "Alpha", "description": "Create", "label_config": "<View/>"},
        ),
        (
            "PATCH",
            "http://label-studio.internal/api/projects/17",
            {"description": "Update"},
        ),
    ]
    assert applied == {
        "created": [{"ok": True, "url": "http://label-studio.internal/api/projects"}],
        "updated": [{"ok": True, "url": "http://label-studio.internal/api/projects/17"}],
    }


def test_wait_for_version_retries_until_verify_version_succeeds(monkeypatch) -> None:
    attempts: list[int] = []
    sleeps: list[float] = []

    def fake_verify_version(base_url: str) -> dict[str, str]:
        attempts.append(1)
        if len(attempts) < 3:
            raise error.URLError("connection refused")
        return {"release": "1.0.0"}

    monkeypatch.setattr(label_studio_sync, "verify_version", fake_verify_version)
    monkeypatch.setattr(label_studio_sync.time, "sleep", lambda delay: sleeps.append(delay))

    version = label_studio_sync.wait_for_version("http://label-studio.internal", attempts=4, delay=0.25)

    assert version == {"release": "1.0.0"}
    assert len(attempts) == 3
    assert sleeps == [0.25, 0.25]


def test_wait_for_version_raises_after_exhausting_retries(monkeypatch) -> None:
    monkeypatch.setattr(
        label_studio_sync,
        "verify_version",
        lambda base_url: (_ for _ in ()).throw(RuntimeError("not ready")),
    )
    monkeypatch.setattr(label_studio_sync.time, "sleep", lambda delay: None)

    try:
        label_studio_sync.wait_for_version("http://label-studio.internal", attempts=2, delay=0)
    except RuntimeError as exc:
        assert str(exc) == "not ready"
    else:  # pragma: no cover - defensive
        raise AssertionError("wait_for_version should raise after exhausting retries")
