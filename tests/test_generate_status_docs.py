from __future__ import annotations

from pathlib import Path

import generate_status_docs
import platform.root_summary as root_summary


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_render_generated_docs_rolls_root_history_into_generated_ledgers(
    monkeypatch,
    tmp_path: Path,
) -> None:
    budget_path = tmp_path / "config" / "root-summary-budgets.yaml"
    write(
        budget_path,
        """schema_version: 1.0.0
readme:
  max_lines: 320
  live_apply_evidence:
    recent_entries: 2
    history_path: docs/status/history/live-apply-evidence.md
  merged_workstreams:
    recent_entries: 2
    history_path: docs/status/history/merged-workstreams.md
changelog:
  max_lines: 90
  previous_release_entries: 2
  archive_index_path: docs/release-notes/index/README.md
release_notes_index:
  max_lines: 90
  recent_entries: 2
  archive_index_path: docs/release-notes/index/README.md
""",
    )
    write(
        tmp_path / "README.md",
        """# Test README

<!-- BEGIN GENERATED: platform-status -->
stale
<!-- END GENERATED: platform-status -->

<!-- BEGIN GENERATED: control-plane-lanes -->
stale
<!-- END GENERATED: control-plane-lanes -->

<!-- BEGIN GENERATED: document-index -->
stale
<!-- END GENERATED: document-index -->

<!-- BEGIN GENERATED: version-summary -->
stale
<!-- END GENERATED: version-summary -->

<!-- BEGIN GENERATED: merged-workstreams -->
stale
<!-- END GENERATED: merged-workstreams -->
""",
    )
    write(
        tmp_path / "versions" / "stack.yaml",
        """
repo_version: 0.200.0
platform_version: 0.130.98
observed_state:
  checked_at: 2026-04-03
  os:
    major: 13
    kernel: 6.17.13-2-pve
  proxmox:
    installed: true
    version: 9.1.6
  guests:
    template:
      vmid: 9000
    instances:
      - running: true
      - running: false
live_apply_evidence:
  latest_receipts:
    docs: 2026-04-01-adr-0309-docs-live-apply
    auth: 2026-04-03-adr-0341-auth-live-apply
    registry: 20260402T101500Z-registry-live-apply
""".strip()
        + "\n",
    )
    write(
        tmp_path / "inventory" / "host_vars" / "proxmox_florin.yml",
        """
lv3_service_topology:
  docs_portal:
    public_hostname: docs.example.test
    exposure_model: edge-published
  api_gateway:
    exposure_model: private-only
""".strip()
        + "\n",
    )
    write(tmp_path / "changelog.md", "# Changelog\n")
    write(tmp_path / "docs" / "release-notes" / "README.md", "# Release Notes\n")
    write(tmp_path / "docs" / "repository-map.md", "# Repository Map\n")
    write(tmp_path / "docs" / "assistant-operator-guide.md", "# Assistant Guide\n")
    write(tmp_path / "docs" / "release-process.md", "# Release Process\n")
    write(tmp_path / "workstreams.yaml", "workstreams: []\n")
    write(tmp_path / "docs" / "workstreams" / "README.md", "# Workstreams Guide\n")
    write(tmp_path / "docs" / "runbooks" / "example.md", "# Example Runbook\n")
    write(tmp_path / "docs" / "adr" / ".index.yaml", "adrs: []\n")

    monkeypatch.setattr(root_summary, "ROOT_SUMMARY_BUDGETS_PATH", budget_path)
    monkeypatch.setattr(generate_status_docs, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(generate_status_docs, "README_PATH", tmp_path / "README.md")
    monkeypatch.setattr(generate_status_docs, "STACK_PATH", tmp_path / "versions" / "stack.yaml")
    monkeypatch.setattr(
        generate_status_docs, "HOST_VARS_PATH", tmp_path / "inventory" / "host_vars" / "proxmox_florin.yml"
    )
    monkeypatch.setattr(generate_status_docs, "WORKSTREAMS_PATH", tmp_path / "workstreams.yaml")
    monkeypatch.setattr(generate_status_docs, "RUNBOOKS_DIR", tmp_path / "docs" / "runbooks")
    monkeypatch.setattr(generate_status_docs, "ADR_DIR", tmp_path / "docs" / "adr")
    monkeypatch.setattr(generate_status_docs, "WORKSTREAM_DOCS_DIR", tmp_path / "docs" / "workstreams")
    monkeypatch.setattr(
        generate_status_docs,
        "CORE_DOCUMENTS",
        [
            ("Changelog", tmp_path / "changelog.md"),
            ("Release notes", tmp_path / "docs" / "release-notes" / "README.md"),
            ("Repository map", tmp_path / "docs" / "repository-map.md"),
            ("Assistant operator guide", tmp_path / "docs" / "assistant-operator-guide.md"),
            ("Release process", tmp_path / "docs" / "release-process.md"),
            ("Workstreams registry", tmp_path / "workstreams.yaml"),
            ("Workstreams guide", tmp_path / "docs" / "workstreams" / "README.md"),
        ],
    )
    monkeypatch.setattr(generate_status_docs, "ALLOWED_LANE_IDS", ["observe"])
    monkeypatch.setattr(generate_status_docs, "ALLOWED_PUBLICATION_TIERS", ["edge"])
    monkeypatch.setattr(
        generate_status_docs,
        "load_lane_catalog",
        lambda: (
            {},
            {
                "observe": {
                    "title": "Observe",
                    "transport": "https",
                    "current_surfaces": ["ops_portal"],
                    "steady_state_rules": ["Read-only by default."],
                }
            },
        ),
    )
    monkeypatch.setattr(
        generate_status_docs,
        "load_api_publication_catalog",
        lambda: (
            {},
            {"edge": {"title": "Edge", "summary": "Public edge ingress."}},
            [{"publication_tier": "edge"}],
        ),
    )
    monkeypatch.setattr(
        generate_status_docs,
        "load_workstreams",
        lambda repo_root, include_archive: [
            {
                "id": "ws-0334-auth",
                "adr": "0341",
                "title": "Auth convergence",
                "status": "live_applied",
                "doc": "docs/workstreams/ws-0334-auth.md",
                "canonical_truth": {"included_in_repo_version": None},
            },
            {
                "id": "ws-0326-registry",
                "adr": "0326",
                "title": "Registry shards",
                "status": "live_applied",
                "doc": "docs/workstreams/ws-0326-live-apply.md",
                "canonical_truth": {"included_in_repo_version": "0.178.3"},
            },
            {
                "id": "ws-0309-docs",
                "adr": "0309",
                "title": "Docs IA",
                "status": "live_applied",
                "doc": "docs/workstreams/ws-0309-live-apply.md",
                "canonical_truth": {"included_in_repo_version": "0.177.148"},
            },
        ],
    )

    rendered = generate_status_docs.render_generated_docs()
    readme = rendered[tmp_path / "README.md"]
    live_apply_history = rendered[tmp_path / "docs" / "status" / "history" / "live-apply-evidence.md"]
    merged_history = rendered[tmp_path / "docs" / "status" / "history" / "merged-workstreams.md"]

    assert "Showing 2 of 3 capability receipts." in readme
    assert "Showing 2 of 3 merged or live-applied workstreams." in readme
    assert "[live-apply evidence history](docs/status/history/live-apply-evidence.md)" in readme
    assert "[merged workstream history](docs/status/history/merged-workstreams.md)" in readme
    assert "2026-04-03-adr-0341-auth-live-apply" in live_apply_history
    assert "Registry shards" in merged_history
