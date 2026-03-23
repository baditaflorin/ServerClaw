import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "fixture-expiry-reaper.py"
SPEC = importlib.util.spec_from_file_location("fixture_expiry_reaper", SCRIPT_PATH)
fixture_expiry_reaper = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(fixture_expiry_reaper)


def test_reaper_blocks_when_repo_checkout_is_missing(tmp_path: Path) -> None:
    payload = fixture_expiry_reaper.main(repo_path=str(tmp_path / "missing"))
    assert payload["status"] == "blocked"


def test_reaper_uses_fixture_manager_for_existing_repo(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "inventory" / "group_vars").mkdir(parents=True)
    (tmp_path / "inventory" / "host_vars").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures").mkdir(parents=True)
    (tmp_path / "receipts" / "fixtures").mkdir(parents=True)

    monkeypatch.setattr(
        fixture_expiry_reaper.fixture_manager,
        "reap_expired",
        lambda: {"run_at": "2026-03-23T12:00:00Z", "expired_receipts": [], "skipped_receipts": []},
    )

    payload = fixture_expiry_reaper.main(repo_path=str(tmp_path))
    assert payload["run_at"] == "2026-03-23T12:00:00Z"
