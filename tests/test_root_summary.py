from __future__ import annotations

import platform.root_summary as root_summary


def test_collect_live_apply_evidence_records_sorts_by_newest_receipt_first() -> None:
    records = root_summary.collect_live_apply_evidence_records(
        {
            "older_iso": "2026-03-31-older-receipt",
            "newer_timestamp": "20260403T101500Z-newer-receipt",
            "middle_iso": "2026-04-02-middle-receipt",
        }
    )

    assert [record.capability for record in records] == [
        "newer_timestamp",
        "middle_iso",
        "older_iso",
    ]


def test_collect_merged_workstream_records_prefers_unreleased_then_newer_versions() -> None:
    records = root_summary.collect_merged_workstream_records(
        [
            {
                "id": "ws-0100-main",
                "adr": "0100",
                "title": "Released workstream",
                "status": "merged",
                "doc": "docs/workstreams/ws-0100-main.md",
                "canonical_truth": {"included_in_repo_version": "0.177.1"},
            },
            {
                "id": "ws-0200-live",
                "adr": "0200",
                "title": "Unreleased exact-main workstream",
                "status": "live_applied",
                "doc": "docs/workstreams/ws-0200-live.md",
                "canonical_truth": {"included_in_repo_version": None},
            },
            {
                "id": "ws-0150-main",
                "adr": "0150",
                "title": "Newer released workstream",
                "status": "merged",
                "doc": "docs/workstreams/ws-0150-main.md",
                "canonical_truth": {"included_in_repo_version": "0.178.0"},
            },
        ]
    )

    assert [record.workstream_id for record in records] == [
        "ws-0200-live",
        "ws-0150-main",
        "ws-0100-main",
    ]
