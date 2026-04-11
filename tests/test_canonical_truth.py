from __future__ import annotations

from pathlib import Path

import pytest

import canonical_truth
from platform.workstream_registry import write_assembled_registry


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture()
def canonical_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    write(tmp_path / "VERSION", "0.10.0\n")
    write(
        tmp_path / "changelog.md",
        """# Changelog

## Unreleased

## Latest Release

- [0.10.0 release notes](/repo/docs/release-notes/0.10.0.md)

## Previous Releases
""",
    )
    write(
        tmp_path / "versions" / "stack.yaml",
        """
schema_version: 1.0.0
repo_version: 0.10.0
platform_version: 0.9.0

live_apply_evidence:
  receipt_dir: receipts/live-applies
  latest_receipts:
    api_gateway: old-api-receipt
    homepage: old-homepage-receipt

release_tracks:
  delivery_model:
    mode: parallel_workstreams
    branch_prefix: codex/
  repo_versioning:
    current: 0.10.0
    meaning: repo
  platform_versioning:
    current: 0.9.0
    meaning: platform
""".strip()
        + "\n",
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
        tmp_path / "inventory" / "host_vars" / "proxmox_florin.yml",
        """
lv3_service_topology:
  api:
    public_hostname: api.lv3.org
    service_name: api_gateway
    exposure_model: public
    owning_vm: docker-runtime-lv3
""".strip()
        + "\n",
    )
    write(tmp_path / "docs" / "runbooks" / "example.md", "# Example Runbook\n")
    write(
        tmp_path / "docs" / "workstreams" / "adr-0174-canonical-truth-assembly.md",
        "# Workstream ADR 0174: Canonical Truth\n",
    )
    write(
        tmp_path / "docs" / "adr" / "0174-integration-only-canonical-truth-assembly.md",
        """# ADR 0174: Integration Only Canonical Truth Assembly

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
""",
    )
    write(
        tmp_path / "workstreams.yaml",
        """
schema_version: 1.0.0
release_policy:
  breaking_change_criteria: /tmp/repo/config/version-semantics.json
workstreams:
  - id: adr-0174-canonical-truth-assembly
    adr: "0174"
    title: Integration-only canonical truth assembly
    status: merged
    branch: codex/adr-0174-canonical-truth
    worktree_path: ../worktree-adr-0174-canonical-truth
    doc: /tmp/repo/docs/workstreams/adr-0174-canonical-truth-assembly.md
    canonical_truth:
      changelog_entry: implemented ADR 0174 integration-only canonical truth assembly, release-note derivation, and live-apply canonical truth preflight
      release_bump: patch
      included_in_repo_version: null
      latest_receipts: {}
  - id: adr-0152-homepage
    adr: "0152"
    title: Homepage
    status: live_applied
    branch: codex/adr-0152-homepage
    worktree_path: ../homepage
    doc: /tmp/repo/docs/workstreams/adr-0152-homepage.md
    canonical_truth:
      latest_receipts:
        homepage: 2026-03-26-adr-0152-homepage-live-apply
  - id: adr-0163-retry-taxonomy
    adr: "0163"
    title: Retry taxonomy
    status: live_applied
    branch: codex/adr-0163-retry-taxonomy
    worktree_path: ../retry
    doc: /tmp/repo/docs/workstreams/adr-0163-retry-taxonomy.md
    canonical_truth:
      latest_receipts:
        api_gateway: 2026-03-26-adr-0163-retry-taxonomy-live-apply
""".strip()
        + "\n",
    )

    monkeypatch.setattr(canonical_truth, "VERSION_PATH", tmp_path / "VERSION")
    monkeypatch.setattr(canonical_truth, "CHANGELOG_PATH", tmp_path / "changelog.md")
    monkeypatch.setattr(canonical_truth, "STACK_PATH", tmp_path / "versions" / "stack.yaml")
    monkeypatch.setattr(canonical_truth, "WORKSTREAMS_PATH", tmp_path / "workstreams.yaml")
    monkeypatch.setattr(canonical_truth, "README_PATH", tmp_path / "README.md")
    return tmp_path


def test_assemble_changelog_from_pending_workstreams(canonical_repo: Path) -> None:
    updated = canonical_truth.assemble_changelog_text((canonical_repo / "changelog.md").read_text(encoding="utf-8"))

    expected_entry = (
        "implemented ADR 0174 integration-only canonical truth assembly, "
        "release-note derivation, and live-apply canonical truth preflight"
    )
    assert f"- {expected_entry}" in updated
    assert updated.count(expected_entry) == 1


def test_infer_release_bump_uses_highest_pending_bump(canonical_repo: Path) -> None:
    workstreams = canonical_truth.load_workstream_canonical_truth()

    assert canonical_truth.infer_release_bump(workstreams) == "patch"


def test_assemble_stack_updates_repo_version_and_latest_receipts(canonical_repo: Path) -> None:
    write(canonical_repo / "VERSION", "0.10.1\n")

    updated = canonical_truth.assemble_stack_text(
        (canonical_repo / "versions" / "stack.yaml").read_text(encoding="utf-8"),
        version="0.10.1",
    )

    assert "repo_version: 0.10.1" in updated
    assert "current: 0.10.1" in updated
    assert "homepage: 2026-03-26-adr-0152-homepage-live-apply" in updated
    assert "api_gateway: 2026-03-26-adr-0163-retry-taxonomy-live-apply" in updated


def test_assemble_latest_receipts_prefers_newer_repo_version_over_higher_adr(canonical_repo: Path) -> None:
    items = [
        canonical_truth.WorkstreamCanonicalTruth(
            workstream_id="ws-0273-mainline",
            adr="0273",
            title="Older integrated edge receipt",
            status="live_applied",
            changelog_entry=None,
            release_bump=None,
            included_in_repo_version="0.177.77",
            latest_receipts={"public_edge_publication": "older-edge-receipt"},
        ),
        canonical_truth.WorkstreamCanonicalTruth(
            workstream_id="ws-0268-mainline",
            adr="0268",
            title="Newer integrated edge receipt",
            status="live_applied",
            changelog_entry=None,
            release_bump=None,
            included_in_repo_version="0.177.81",
            latest_receipts={"public_edge_publication": "newer-edge-receipt"},
        ),
    ]

    latest = canonical_truth.assemble_latest_receipts(
        items,
        stack_path=canonical_repo / "versions" / "stack.yaml",
    )

    assert latest["public_edge_publication"] == "newer-edge-receipt"


def test_mark_pending_workstreams_released_sets_repo_version(canonical_repo: Path) -> None:
    changed = canonical_truth.mark_pending_workstreams_released("0.10.1")

    assert changed == ["adr-0174-canonical-truth-assembly"]
    workstreams_text = (canonical_repo / "workstreams.yaml").read_text(encoding="utf-8")
    assert "included_in_repo_version: 0.10.1" in workstreams_text
    assert "included_in_repo_version: null" not in workstreams_text


def test_mark_pending_workstreams_released_inserts_version_without_touching_next_block(canonical_repo: Path) -> None:
    workstreams_path = canonical_repo / "workstreams.yaml"
    workstreams_text = workstreams_path.read_text(encoding="utf-8").replace(
        "      included_in_repo_version: null\n",
        "",
        1,
    )
    workstreams_text += """
  - id: adr-0200-following-workstream
    adr: "0200"
    title: Following workstream
    status: merged
    branch: codex/adr-0200-following-workstream
    worktree_path: ../following
    doc: /tmp/repo/docs/workstreams/adr-0200-following-workstream.md
    canonical_truth:
      changelog_entry: implemented ADR 0200 following workstream
      release_bump: patch
      included_in_repo_version: 9.9.9
      latest_receipts: {}
"""
    write(workstreams_path, workstreams_text)

    changed = canonical_truth.mark_pending_workstreams_released("0.10.1")

    assert changed == ["adr-0174-canonical-truth-assembly"]
    updated = workstreams_path.read_text(encoding="utf-8")
    assert "id: adr-0174-canonical-truth-assembly" in updated
    assert "release_bump: patch\n      included_in_repo_version: 0.10.1\n" in updated
    assert "id: adr-0200-following-workstream" in updated
    assert "included_in_repo_version: 9.9.9" in updated


def test_invalid_release_bump_is_rejected(canonical_repo: Path) -> None:
    broken = (
        (canonical_repo / "workstreams.yaml")
        .read_text(encoding="utf-8")
        .replace(
            "release_bump: patch",
            "release_bump: hotfix",
        )
    )
    write(canonical_repo / "workstreams.yaml", broken)

    with pytest.raises(ValueError, match="release_bump must be one of"):
        canonical_truth.load_workstream_canonical_truth()


def test_mark_pending_workstreams_released_moves_sharded_workstream_to_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(
        tmp_path / "workstreams" / "policy.yaml",
        """
schema_version: 1.0.0
delivery_model:
  mode: parallel_workstreams
  branch_prefix: codex/
  workstream_doc_root: docs/workstreams
  registry_owner: main
release_policy:
  repo_version_bump_on: merge_to_main
  platform_version_bump_on: live_apply_from_main
  changelog_working_section: Unreleased
  versions_stack_branch_policy: main_only
  breaking_change_criteria: config/version-semantics.json
""".strip()
        + "\n",
    )
    (tmp_path / "workstreams" / "archive").mkdir(parents=True, exist_ok=True)
    write(
        tmp_path / "workstreams" / "active" / "adr-0174-canonical-truth-assembly.yaml",
        """
id: adr-0174-canonical-truth-assembly
adr: "0174"
title: Integration-only canonical truth assembly
status: merged
branch: codex/adr-0174-canonical-truth
worktree_path: .worktrees/adr-0174-canonical-truth
doc: docs/workstreams/adr-0174-canonical-truth-assembly.md
canonical_truth:
  changelog_entry: implemented ADR 0174 integration-only canonical truth assembly
  release_bump: patch
  included_in_repo_version: null
  latest_receipts: {}
""".strip()
        + "\n",
    )
    write_assembled_registry(repo_root=tmp_path, compatibility_path=tmp_path / "workstreams.yaml")

    monkeypatch.setattr(canonical_truth, "WORKSTREAMS_PATH", tmp_path / "workstreams.yaml")

    changed = canonical_truth.mark_pending_workstreams_released(
        "0.10.1", workstreams_path=tmp_path / "workstreams.yaml"
    )

    assert changed == ["adr-0174-canonical-truth-assembly"]
    assert not (tmp_path / "workstreams" / "active" / "adr-0174-canonical-truth-assembly.yaml").exists()
    archived = next((tmp_path / "workstreams" / "archive").rglob("adr-0174-canonical-truth-assembly.yaml"))
    assert "included_in_repo_version: 0.10.1" in archived.read_text(encoding="utf-8")
    compatibility = (tmp_path / "workstreams.yaml").read_text(encoding="utf-8")
    assert "adr-0174-canonical-truth-assembly" not in compatibility
