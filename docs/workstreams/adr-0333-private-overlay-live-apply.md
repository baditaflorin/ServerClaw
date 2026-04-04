# Workstream ADR 0333: Private Overlay Live Apply

- ADR: [ADR 0333](../adr/0333-private-overlay-files-for-deployment-specific-secrets-and-identities.md)
- Title: finish the shared private-overlay bootstrap alias contract and verify it from a dedicated worktree
- Status: in_progress
- Included In Repo Version: not yet
- Branch-Local Receipt: pending
- Mainline Receipt: pending
- Implemented On: pending
- Live Applied On: pending
- Live Applied In Platform Version: pending verification
- Latest Verified Base: `origin/main@20a66bbf088d1aa456d34f173fd8e2c8664f4c20` (`repo 0.178.3`, `platform 0.130.98`)
- Branch: `codex/ws-0333-private-overlay`
- Worktree: `.worktrees/ws-0333-private-overlay`
- Owner: codex
- Depends On: `ADR 0034`, `ADR 0167`, `ADR 0268`, `ADR 0330`, `ADR 0333`
- Conflicts With: none

## Scope

- replace the remaining active controller-local bootstrap key contract with the
  generic shared-overlay alias under `.local/ssh/bootstrap.id_ed25519`
- make linked worktrees resolve and materialize shared `.local` files instead
  of creating shadow copies under `.worktrees/.../.local`
- verify the build-server validation path, controller preflight path, and the
  exact-main repo automation around this private-overlay contract

## Planned Verification

- focused regression coverage for the shared `.local` resolver, bootstrap alias
  materializer, preflight bootstrap manifests, remote exec, Windmill wrapper,
  provision-operator, and validation-runner contracts
- live controller proof that `python3 scripts/materialize_bootstrap_key_alias.py`
  and `make preflight WORKFLOW=configure-edge-publication` succeed from the
  dedicated worktree while resolving the shared overlay
- exact-main validation replay after merge, including the workstream registry,
  repository validation bundle, and remote validation or pre-push gate surfaces
