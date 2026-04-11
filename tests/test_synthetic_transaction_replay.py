from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import synthetic_transaction_replay as replay  # noqa: E402


def test_run_target_profile_counts_optional_failures_without_failing_suite(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "targets": {
                    "restore-docker-runtime": {
                        "name": "Restore target",
                        "validation_window": {
                            "name": "post_restore_recovery",
                            "detail": "Replay ran after restore boot.",
                        },
                        "queue_depth": {
                            "status": "not_applicable",
                            "detail": "No queue metrics.",
                        },
                        "scenarios": [
                            {
                                "id": "required-scenario",
                                "name": "Required scenario",
                                "kind": "http",
                                "required": True,
                                "iterations": 2,
                                "request": {"url": "http://127.0.0.1/ok"},
                            },
                            {
                                "id": "optional-scenario",
                                "name": "Optional scenario",
                                "kind": "http",
                                "required": False,
                                "iterations": 1,
                                "request": {"url": "http://127.0.0.1/maybe"},
                            },
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    outcomes = iter(
        [
            SimpleNamespace(returncode=0, stdout='{"status":200,"elapsed_ms":12,"body_excerpt":"ok"}', stderr=""),
            SimpleNamespace(returncode=0, stdout='{"status":200,"elapsed_ms":18,"body_excerpt":"ok"}', stderr=""),
            SimpleNamespace(returncode=1, stdout='{"status":503,"elapsed_ms":30,"error":"unavailable"}', stderr="boom"),
        ]
    )

    report = replay.run_target_profile(
        "restore-docker-runtime",
        catalog_path=catalog_path,
        execute_command=lambda _command: next(outcomes),
    )

    assert report["overall"] == "pass"
    assert report["success_count"] == 2
    assert report["request_count"] == 3
    assert report["latency_ms"] == {"count": 3, "p50": 18, "p95": 30, "max": 30}
    assert report["window_assessment"]["window"] == "post_restore_recovery"
    assert report["scenarios"][1]["overall"] == "fail"


def test_main_supports_dry_run(tmp_path: Path, capsys) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "targets": {
                    "restore-docker-runtime": {
                        "name": "Restore target",
                        "validation_window": {
                            "name": "post_restore_recovery",
                            "detail": "Replay ran after restore boot.",
                        },
                        "queue_depth": {"status": "not_applicable", "detail": "No queue metrics."},
                        "scenarios": [
                            {
                                "id": "required-scenario",
                                "kind": "http",
                                "request": {"url": "http://127.0.0.1/ok"},
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    exit_code = replay.main(["--target", "restore-docker-runtime", "--catalog", str(catalog_path), "--dry-run"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "required-scenario" in captured.out
