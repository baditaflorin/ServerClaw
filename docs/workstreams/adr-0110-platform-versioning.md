# Workstream ADR 0110: Platform Versioning, Release Notes, and Upgrade Path

- ADR: [ADR 0110](../adr/0110-platform-versioning-and-upgrade-path.md)
- Title: Semantic versioning semantics definition, lv3 release command, structured RELEASE.md generation, and machine-checkable 1.0.0 readiness criteria
- Status: merged
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
- add `lv3 release status` output to the existing generated ops portal so the readiness signal is visible before ADR 0093 replaces the static portal
- align the implementation with the current mainline release layout (`docs/release-notes/<version>.md`, current repo version `0.103.0`, and explicit post-commit tagging)

## Non-Goals

- Automated git tagging in CI (tagging is always an explicit operator action)
- Package publishing to PyPI or Docker registries (image publishing is managed per-service)
- Semantic release tooling (semantic-release, standard-version) — the lv3 CLI provides custom logic appropriate for this platform

## Expected Repo Surfaces

- `config/version-semantics.json`
- `scripts/release_manager.py`
- `scripts/generate_release_notes.py`
- `docs/upgrade/v1.md`
- `docs/runbooks/platform-release-management.md`
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
- `lv3 release --bump patch` works in a disposable repository copy and updates the release artifacts consistently
- Breaking change criteria defined in `config/version-semantics.json`
- Upgrade guide for v1.0.0 committed

## Outcome

- implementation shipped in repo release `0.104.0`
- the current mainline release model is narrower than the original draft, so the implementation follows the existing changelog and release-note surfaces instead of inventing a second archive format
