# ADR 0420: CI Release-Readiness Checks

**Date:** 2026-04-16
**Status:** Implemented
**Related:** ADR 0419 (PR-Based Integration Flow), ADR 0418 (Receipt-to-Outline Auto-Publish)

---

## Context

The merge-to-main checklist (documented in `CLAUDE.md` section 4) requires
several generated artifacts to be up-to-date before a release commit lands
on main:

1. `VERSION` bumped
2. `changelog.md` has an entry under `## Unreleased`
3. Release notes generated (`docs/release-notes/X.Y.Z.md`)
4. Platform manifest regenerated (`build/platform-manifest.json`)
5. Discovery artifacts regenerated (`build/onboarding/`)
6. ADR index regenerated (`docs/adr/.index.yaml`)

When agents or operators forget a step, the existing CI (`make validate`)
catches stale generated files — but only after the code lands on main
(or in a PR with ADR 0419). The failure message is a generic
"stale generated file" error that does not tell the author which checklist
step they missed.

### Problems

1. **Opaque failure messages.** A stale `build/platform-manifest.json`
   produces `schema-validation failed` — not "you forgot to run
   `platform_manifest.py --write`."

2. **No VERSION/changelog validation.** The CI never checks whether
   `VERSION` was actually bumped or `changelog.md` was updated. These
   are convention-only, enforced by memory.

3. **Release notes not validated.** No check verifies that
   `docs/release-notes/X.Y.Z.md` exists for the VERSION in `VERSION`.

4. **Agents repeat the same mistakes.** Every agent session that pushes
   to main risks forgetting one of the 6 checklist steps. The feedback
   loop is slow (push → CI fails → fix → re-push).

---

## Decision

### Add a dedicated `release-readiness` CI job

Add a new GitHub Actions job that runs alongside the existing `validate`
job on PRs targeting `main`. This job performs fast, targeted checks:

| Check | What it validates | Fix hint |
|-------|-------------------|----------|
| `version-bump` | `VERSION` file changed vs. base branch | "Bump VERSION before merging to main" |
| `changelog-entry` | `changelog.md` has content under `## Unreleased` | "Add a changelog entry under ## Unreleased" |
| `release-notes` | `docs/release-notes/{VERSION}.md` exists | "Run `generate_release_notes.py --write`" |
| `adr-index` | `docs/adr/.index.yaml` is current | "Run `generate_adr_index.py --write`" |
| `platform-manifest` | `build/platform-manifest.json` is current | "Run `platform_manifest.py --write`" |
| `discovery-artifacts` | `build/onboarding/` files are current | "Run `generate_discovery_artifacts.py --write`" |

Each check produces a clear pass/fail with an actionable fix command.

### Non-blocking for non-release PRs

Not every PR is a release. Feature branches, documentation updates, and
work-in-progress PRs should not fail on missing VERSION bumps. The
release-readiness job:

- **Runs on all PRs** targeting main (for visibility)
- **Is required** as a status check (but individual checks within it
  are advisory until the PR title contains `[release]`)
- PRs with `[release]` in the title: all checks are enforced
- PRs without `[release]`: checks run but failures are warnings only

This lets agents work on feature branches freely, then add `[release]`
to the PR title when they're ready to merge with the full checklist.

### Implementation: shell script + GitHub Actions job

A new script `scripts/check_release_readiness.py` performs all checks
and outputs structured results. The GitHub Actions workflow calls it
as a separate job.

---

## Consequences

### Positive

- Agents get clear, actionable feedback on which release step they missed
- VERSION and changelog validation catch omissions before they land
- The release checklist is enforced by CI, not just by convention
- Non-release PRs are not penalized

### Negative / Trade-offs

- One more CI job to maintain
- The `[release]` title convention is a soft contract (can be forgotten)

### Not in scope

- Automatic VERSION bumping (agents should make this decision)
- Automatic changelog generation (too context-dependent)
- Automatic PR title tagging

---

## Implementation Checklist

- [x] Write this ADR
- [x] Create `scripts/check_release_readiness.py`
- [x] Add `release-readiness` job to `.github/workflows/validate.yml`
- [x] Document the `[release]` PR title convention in CLAUDE.md

---

## Artifacts

| Artifact | Path |
|----------|------|
| This ADR | `docs/adr/0420-ci-release-readiness-checks.md` |
| Readiness checker | `scripts/check_release_readiness.py` |
| CI workflow | `.github/workflows/validate.yml` |
