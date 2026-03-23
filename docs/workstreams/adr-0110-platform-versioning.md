# Workstream ADR 0110: Platform Versioning, Release Notes, and Upgrade Path

- ADR: [ADR 0110](../adr/0110-platform-versioning-and-upgrade-path.md)
- Title: Semantic versioning semantics definition, lv3 release command, structured RELEASE.md generation, and machine-checkable 1.0.0 readiness criteria
- Status: ready
- Branch: `codex/adr-0110-platform-versioning`
- Worktree: `../proxmox_florin_server-platform-versioning`
- Owner: codex
- Depends On: `adr-0008-versioning-model`, `adr-0017-adr-lifecycle`, `adr-0073-promotion-gate`, `adr-0081-changelog`, `adr-0090-platform-cli`, `adr-0094-developer-portal`
- Conflicts With: none
- Shared Surfaces: `VERSION`, `changelog.md`, `versions/stack.yaml`, `scripts/lv3_cli.py`

## Scope

- write `config/version-semantics.json` — documents the breaking change criteria and version bump rules (machine-readable companion to the ADR)
- write `scripts/release_manager.py` — implements `lv3 release --version`, `lv3 release --bump minor`, `lv3 release status`
- write `scripts/generate_release_notes.py` — extracts the `Unreleased` section from `changelog.md` and formats `RELEASE.md`
- write `docs/upgrade/v1.md` — upgrade guide for moving to v1.0.0 from any v0.x (no migration steps required; just lists what changed)
- update `scripts/lv3_cli.py` — add `release` and `release status` subcommands
- update `workstreams.yaml` release_policy section — add `breaking_change_criteria` reference to `config/version-semantics.json`
- add `lv3 release status` output to the ops portal (ADR 0093 integration: show 1.0.0 readiness as a panel)
- write `docs/release-notes/v0.93.0.md` — backfill the current version's release notes as a baseline

## Non-Goals

- Automated git tagging in CI (tagging is always an explicit operator action)
- Package publishing to PyPI or Docker registries (image publishing is managed per-service)
- Semantic release tooling (semantic-release, standard-version) — the lv3 CLI provides custom logic appropriate for this platform

## Expected Repo Surfaces

- `config/version-semantics.json`
- `scripts/release_manager.py`
- `scripts/generate_release_notes.py`
- `docs/upgrade/v1.md`
- `docs/release-notes/v0.93.0.md`
- `scripts/lv3_cli.py` (patched: `lv3 release` subcommand)
- `docs/adr/0110-platform-versioning-and-upgrade-path.md`
- `docs/workstreams/adr-0110-platform-versioning.md`

## Expected Live Surfaces

- `lv3 release status` runs without errors and produces a 1.0.0 readiness checklist
- `lv3 release --bump patch` updates VERSION, changelog.md, and creates a git tag
- Docs site shows upgrade guide at `https://docs.lv3.org/upgrade/v1/`

## Verification

- `lv3 release status` → shows readiness percentage for 1.0.0 criteria
- `lv3 release --bump patch --dry-run` → shows what VERSION and changelog.md would look like without changing them
- `lv3 release --bump patch` → updates VERSION, changelog.md; creates git tag (verify with `git tag -l`)
- `docs/upgrade/v1.md` renders correctly on the docs site

## Merge Criteria

- `lv3 release status` works and reports current 1.0.0 readiness based on implemented ADRs and live platform state
- `lv3 release --bump patch` works (test with a patch bump; then manually revert the tag if the bump was not intended to be permanent)
- Breaking change criteria defined in `config/version-semantics.json`
- Upgrade guide for v1.0.0 committed

## Notes For The Next Assistant

- `lv3 release status` needs to check: (1) count of ADRs with `Implementation Status: Implemented` vs. total; (2) current SLO error budget from Prometheus (via the API gateway); (3) last backup restore verification result from `receipts/restore-verifications/`; (4) whether ops portal, status page, and docs site are reachable; (5) whether a DR table-top review receipt exists
- Store the DR table-top review completion as a receipt in `receipts/dr-table-top-reviews/` with a date file; `lv3 release status` checks for the most recent one
- The `lv3 release --bump` command must use `python-semantic-release` conventions for changelog formatting, or follow the existing `changelog.md` format exactly (check what format the existing changelog uses before implementing)
- Git tag signing: if GPG signing is configured in `.gitconfig`, the tag creation should use `git tag -s`; if not, use `git tag -a`; check and match the user's git config
