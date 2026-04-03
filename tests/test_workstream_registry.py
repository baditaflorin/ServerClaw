from __future__ import annotations

from pathlib import Path

import platform.workstream_registry as workstream_registry


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_migrate_registry_creates_shards_and_active_only_compatibility(tmp_path: Path) -> None:
    compatibility_path = tmp_path / "workstreams.yaml"
    write(
        compatibility_path,
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
workstreams:
  - id: ws-1000-active
    adr: "1000"
    title: Active workstream
    status: ready_for_merge
    owner: codex
    branch: codex/ws-1000-active
    worktree_path: .worktrees/ws-1000-active
    doc: docs/workstreams/ws-1000-active.md
    depends_on: []
    conflicts_with: []
    shared_surfaces:
      - workstreams.yaml
    ready_to_merge: true
    live_applied: false
    canonical_truth:
      changelog_entry: implement the active workstream
      release_bump: patch
      included_in_repo_version: null
      latest_receipts: {}
  - id: ws-0999-archived
    adr: "0999"
    title: Archived workstream
    status: live_applied
    owner: codex
    branch: codex/ws-0999-archived
    worktree_path: .worktrees/ws-0999-archived
    doc: docs/workstreams/ws-0999-archived.md
    depends_on: []
    conflicts_with: []
    shared_surfaces:
      - workstreams.yaml
    ready_to_merge: true
    live_applied: true
    canonical_truth:
      changelog_entry: implement the archived workstream
      release_bump: patch
      included_in_repo_version: 0.10.0
      latest_receipts: {}
""".strip()
        + "\n",
    )

    result = workstream_registry.migrate_from_compatibility(
        repo_root=tmp_path,
        compatibility_path=compatibility_path,
        source_registry_path=compatibility_path,
        archive_year="2026",
    )

    assert result["active_count"] == 1
    assert result["archive_count"] == 1
    assert (tmp_path / "workstreams" / "active" / "ws-1000-active.yaml").exists()
    assert (tmp_path / "workstreams" / "archive" / "2026" / "ws-0999-archived.yaml").exists()

    compatibility = workstream_registry.load_registry(repo_root=tmp_path, include_archive=False)
    assert [item["id"] for item in compatibility["workstreams"]] == ["ws-1000-active"]
    assert compatibility["archive_summary"]["by_year"] == {"2026": 1}

    all_workstreams = workstream_registry.load_workstreams(repo_root=tmp_path, include_archive=True)
    assert [item["id"] for item in all_workstreams] == ["ws-1000-active", "ws-0999-archived"]
    assert workstream_registry.compatibility_matches_source(repo_root=tmp_path)
