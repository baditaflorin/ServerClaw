# WS-0514: Retire GitHub Actions validation

## Status

`ready_for_merge` — the GitHub Actions Validate workflow is absent from both
current source and public baselines. This branch completes the canonical
workflow-catalog cleanup by replacing the stale `.github` path with the current
`.woodpecker.yml` path. The separate self-hosted Gitea validator is retained.

## Decision

Use the repository's existing Woodpecker workflow and required Woodpecker
status checks for GitHub-hosted PR admission. Remove the redundant
`.github/workflows` validation workflow rather than maintaining a GitHub-hosted
runner. Preserve the separate self-hosted Gitea validation workflow and keep
both current CI entrypoints represented in the workflow catalog. Keep release
readiness as a local/governed release operation; it is not an ordinary PR CI
gate and currently reports repository-wide release blockers.

## Evidence

- The public snapshot's GitHub Actions `validate` and `release-readiness` jobs
  failed in 2–3 seconds with no job steps; the Woodpecker PR and push checks
  both completed successfully.
- Repo settings now disable the sole `Validate` workflow in both source and
  mirror, preventing another GitHub-hosted run during transition.
- The source `.woodpecker.yml` remains present and configured for push and PR
  events. The ServerClaw main ruleset requires the Woodpecker push context, not
  the disabled GitHub Actions checks.
- After rebasing on current `origin/main`, the changed-service completeness
  gate reports no affected services; the broad legacy audit is not used to
  block this unrelated workflow metadata update.

## Verification

- Confirm no tracked files remain under `.github/workflows/`.
- Confirm the canonical workflow catalog references `.woodpecker.yml` and no
  longer references the removed GitHub Actions workflow.
- Validate workstream ownership and generated documentation after the source
  deletion.
- Push through the normal repository pre-push gate and wait for both Woodpecker
  PR and push contexts.
- Regenerate the sanitized ServerClaw snapshot, confirm its leak scan passes,
  and merge the mirror PR only after required Woodpecker checks pass.

## Ownership coordination

The workflow catalog path was also listed in WS-0424's exclusive schema-catalog
claim, although its recorded branch/worktree is absent and there is no remote
branch or open PR. This change transfers only that path to a narrow additive
`workflow-catalog-entry-v1` contract shared with WS-0424; structural changes to
its other catalog and platform-data surfaces remain exclusive there. The
WS-0424 active shard is shared solely to record this ownership transfer.
