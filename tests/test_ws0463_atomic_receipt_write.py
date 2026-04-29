"""Tests for ADR 0461 — atomic receipt write + dangling-receipt check.

Covers:
  - find_dangling_receipts() detects slugs with no JSON file.
  - find_dangling_receipts() returns empty when all receipts exist.
  - write_receipt_atomic() never leaves a partial file on disk.
  - write_receipt_atomic() is idempotent (rewrite over existing file).
  - --check-files exits 1 when dangling found, 0 when clean.
  - --check-files emits a remediation message naming the missing path.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_receipt_freshness.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_receipt_freshness_for_ws0463", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["check_receipt_freshness_for_ws0463"] = module
    spec.loader.exec_module(module)
    return module


# --- find_dangling_receipts -----------------------------------------------


def test_find_dangling_returns_empty_when_all_present(tmp_path):
    mod = _load_module()
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir()
    (receipt_dir / "alpha-2026-04-29-receipt.json").write_text("{}")
    (receipt_dir / "beta-2026-04-29-receipt.json").write_text("{}")
    receipts = {
        "alpha": "alpha-2026-04-29-receipt",
        "beta": "beta-2026-04-29-receipt",
    }
    assert mod.find_dangling_receipts(receipts, receipt_dir=receipt_dir) == []


def test_find_dangling_flags_missing_files(tmp_path):
    mod = _load_module()
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir()
    (receipt_dir / "alpha-receipt.json").write_text("{}")
    receipts = {"alpha": "alpha-receipt", "beta": "beta-missing-receipt"}
    dangling = mod.find_dangling_receipts(receipts, receipt_dir=receipt_dir)
    assert dangling == [("beta", "beta-missing-receipt")]


def test_find_dangling_skips_empty_slugs(tmp_path):
    mod = _load_module()
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir()
    receipts = {"alpha": "", "beta": "beta-receipt"}
    dangling = mod.find_dangling_receipts(receipts, receipt_dir=receipt_dir)
    # Only beta is checked; alpha has empty slug so is skipped.
    assert dangling == [("beta", "beta-receipt")]


# --- write_receipt_atomic -------------------------------------------------


def test_atomic_write_creates_file(tmp_path):
    mod = _load_module()
    target = tmp_path / "receipt.json"
    payload = {"service": "alpha", "applied_on": "2026-04-29"}
    mod.write_receipt_atomic(target, payload)
    assert target.is_file()
    assert json.loads(target.read_text()) == payload


def test_atomic_write_overwrites(tmp_path):
    mod = _load_module()
    target = tmp_path / "receipt.json"
    target.write_text('{"old": true}')
    mod.write_receipt_atomic(target, {"new": True})
    assert json.loads(target.read_text()) == {"new": True}


def test_atomic_write_leaves_no_tempfiles(tmp_path):
    mod = _load_module()
    target = tmp_path / "receipt.json"
    mod.write_receipt_atomic(target, {"k": "v"})
    # Only the final receipt should exist; no .tmp leftovers.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["receipt.json"]


def test_atomic_write_creates_parent_dirs(tmp_path):
    mod = _load_module()
    target = tmp_path / "deep" / "nested" / "receipt.json"
    mod.write_receipt_atomic(target, {"k": "v"})
    assert target.is_file()


def test_atomic_write_failure_cleans_up_temp(tmp_path, monkeypatch):
    """If json.dump raises, the temp file must not survive."""
    mod = _load_module()
    target = tmp_path / "receipt.json"

    class Unserialisable:
        pass

    with pytest.raises(TypeError):
        mod.write_receipt_atomic(target, {"k": Unserialisable()})

    # No .tmp leftovers and no real receipt either.
    leftover = list(tmp_path.iterdir())
    assert leftover == [], f"unexpected leftover: {leftover}"


# --- CLI integration -------------------------------------------------------


def _run_cli(tmp_path: Path, monkeypatch, *, receipts: dict, files: list[str]) -> int:
    """Run the CLI's main() against a synthetic stack.yaml and receipts/."""
    mod = _load_module()
    stack_yaml = tmp_path / "stack.yaml"
    stack_yaml.write_text(
        "schema_version: 1.0.0\n"
        "live_apply_evidence:\n"
        "  receipt_dir: receipts/live-applies\n"
        "  latest_receipts:\n"
        + "".join(f"    {k}: {v}\n" for k, v in receipts.items())
    )
    receipt_dir = tmp_path / "receipts" / "live-applies"
    receipt_dir.mkdir(parents=True)
    for name in files:
        (receipt_dir / f"{name}.json").write_text("{}")
    monkeypatch.setattr(mod, "RECEIPT_DIR", receipt_dir)
    return mod.main(["--stack-yaml", str(stack_yaml), "--check-files"])


def test_cli_check_files_exit_zero_when_clean(tmp_path, monkeypatch, capsys):
    rc = _run_cli(
        tmp_path,
        monkeypatch,
        receipts={"alpha": "2026-04-29-alpha-live-apply"},
        files=["2026-04-29-alpha-live-apply"],
    )
    assert rc == 0


def test_cli_check_files_exit_one_when_dangling(tmp_path, monkeypatch, capsys):
    rc = _run_cli(
        tmp_path,
        monkeypatch,
        receipts={"alpha": "2026-04-29-alpha-live-apply", "beta": "2026-04-29-beta-missing"},
        files=["2026-04-29-alpha-live-apply"],
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "DANGLING" in captured.err
    assert "beta" in captured.err
