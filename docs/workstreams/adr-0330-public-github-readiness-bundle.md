# Workstream ADR 0330: Public GitHub Readiness Bundle

- ADR: [ADR 0330](../adr/0330-public-github-readiness-as-a-first-class-repository-lifecycle.md)
- Bundle ADRs: `0330`, `0331`, `0332`, `0333`, `0334`, `0335`, `0336`, `0337`, `0338`, `0339`
- Title: Prepare the repository for public GitHub publication as a generic, forkable reference platform
- Status: merged
- Included In Repo Version: 0.177.143
- Live Applied In Platform Version: N/A
- Implemented On: 2026-04-02
- Branch: `codex/ws-0327-public-github-readiness`
- Worktree: `.worktrees/ws-0327-public-github-readiness`
- Owner: codex
- Depends On: `adr-0038-generated-status-documents-from-canonical-state`, `adr-0163-repository-structure-index-for-agent-discovery`, `adr-0167-agent-handoff-and-context-preservation`, `adr-0168-automated-enforcement-of-agent-standards`
- Conflicts With: none
- Shared Surfaces: `README.md`, `AGENTS.md`, `.repo-structure.yaml`, `workstreams.yaml`, `changelog.md`, `docs/release-notes/README.md`, `docs/adr/.index.yaml`, `scripts/generate_status_docs.py`, `scripts/generate_release_notes.py`, `scripts/validate_repo.sh`, `scripts/validate_repository_data_models.py`, `scripts/workstream_surface_ownership.py`, `scripts/validate_public_entrypoints.py`

## Scope

- add the public-readiness ADR bundle that defines how the repo becomes safe to
  publish and easy to fork
- convert governed root metadata and generated release/status surfaces to
  repository-relative links and worktree paths
- rewrite onboarding entrypoints so they describe a reusable reference platform
  instead of one operator's environment
- add validation that rejects workstation home paths and deployment-specific
  identifiers in public onboarding surfaces

## Non-Goals

- rewriting every historical ADR, runbook, receipt, or workstream document in
  one integration
- pretending the existing deployment-specific history never existed
- removing private overlays or ignored `.local/` state needed for real operations

## Expected Repo Surfaces

- `docs/adr/0330-public-github-readiness-as-a-first-class-repository-lifecycle.md`
- `docs/adr/0331-repository-relative-paths-for-public-metadata-and-generated-docs.md`
- `docs/adr/0332-relative-release-and-status-links-in-generated-root-surfaces.md`
- `docs/adr/0333-private-overlay-files-for-deployment-specific-secrets-and-identities.md`
- `docs/adr/0334-example-first-inventory-and-service-identity-catalogs.md`
- `docs/adr/0335-public-safe-agent-onboarding-entrypoints.md`
- `docs/adr/0336-public-entrypoint-leakage-validation.md`
- `docs/adr/0337-fork-first-workstream-and-worktree-metadata.md`
- `docs/adr/0338-public-documentation-tiers-and-private-history-boundaries.md`
- `docs/adr/0339-reference-deployment-samples-and-replaceable-provider-profiles.md`
- `docs/workstreams/adr-0330-public-github-readiness-bundle.md`
- `README.md`
- `AGENTS.md`
- `.repo-structure.yaml`
- `workstreams.yaml`
- `changelog.md`
- `docs/release-notes/README.md`
- `scripts/generate_status_docs.py`
- `scripts/generate_release_notes.py`
- `scripts/validate_repo.sh`
- `scripts/validate_repository_data_models.py`
- `scripts/workstream_surface_ownership.py`
- `scripts/validate_public_entrypoints.py`

## Verification

- regenerate root status and release surfaces after the generator changes
- regenerate the ADR index after adding the ten ADRs
- run `./scripts/validate_repo.sh agent-standards`
- run `./scripts/validate_repo.sh generated-docs`
- run `python3 scripts/validate_repository_data_models.py --validate`
- run `git diff --check`

## Notes

- this merge intentionally prioritizes public entrypoints and governed
  generators; deeper historical docs remain follow-up cleanup work under ADR
  0333, ADR 0334, ADR 0338, and ADR 0339
- the result is a safer public mainline now, plus explicit ADRs that keep the
  repo moving toward a true example-first template instead of drifting back into
  one-environment assumptions
