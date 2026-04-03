# Workstream ws-0318-live-apply: Live Apply ADR 0318 From Latest `origin/main`

- ADR: [ADR 0318](../adr/0318-repeatable-operator-onboarding-with-cc-audit-trail.md)
- Title: Live apply repeatable operator onboarding from a dedicated git worktree and verify the Keycloak, Headscale, and requester-CC audit trail end to end
- Status: live_applied
- Branch: `codex/ws-0318-live-apply`
- Worktree: `.worktrees/ws-0318-live-apply`
- Owner: codex
- Depends On: `adr-0317-keycloak-direct-api-operator-provisioning-via-ssh-proxy`, `adr-0318-repeatable-operator-onboarding-with-cc-audit-trail`
- Conflicts With: `ws-0318-operator-onboarding-iac`, `ws-0318-provision-operator-v2`
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0318-live-apply.md`, `docs/adr/0318-repeatable-operator-onboarding-with-cc-audit-trail.md`, `docs/runbooks/operator-onboarding.md`, `docs/adr/.index.yaml`, `scripts/provision_operator.py`, `tests/test_provision_operator.py`, `receipts/live-applies/`, `receipts/live-applies/evidence/`

## Purpose

Replay ADR 0318 from a clean worktree off the latest `origin/main`, make the
repo-managed fallback onboarding script genuinely safe to run from that
worktree, and verify the live Keycloak, Headscale, and requester-CC audit-trail
mail path without relying on unpublished branch state.

## Scope

- make `scripts/provision_operator.py` resolve `.local/` from the shared
  checkout when invoked from `.worktrees/`
- align the fallback role/group mappings with the canonical
  `scripts/operator_manager.py` contract
- verify the Keycloak-only replay path with `--skip-email`
- perform a full live replay against a temporary operator target under
  operator-controlled mailboxes so Headscale authkey creation and transactional
  email delivery are exercised safely
- capture branch-local live-apply evidence and leave exact merge-to-main follow
  up explicit if protected release surfaces must wait

## Non-Goals

- replacing the roster-first Windmill or `scripts/operator_manager.py` path
- changing unrelated operator identities or access-policy contracts
- updating protected release or platform-truth surfaces before the exact-main
  replay is verified

## Outcome

The dedicated-worktree live apply succeeded on 2026-04-03 after two real drift
repairs were folded back into the repo-managed fallback path:

- `scripts/provision_operator.py` now resolves shared `.local/` state correctly
  from linked worktrees, derives role/group assignments from the canonical
  `scripts/operator_manager.py` contract, and supports exact-main
  re-verification with `--skip-email`.
- The fallback path now accepts `LV3_KEYCLOAK_URL`,
  `LV3_KEYCLOAK_BOOTSTRAP_PASSWORD`, and `LV3_PLATFORM_SMTP_PASSWORD`
  overrides so a live recovery can use runtime secrets ephemerally when the
  controller-local files are stale.
- The temporary admin operator `florin-tmp-002` was fully provisioned and
  verified end to end: Keycloak user `florin.badita-tmp-002`, realm role
  `platform-admin`, groups `lv3-platform-admins` and `grafana-admins`,
  Headscale user `florin-badita-tmp-002`, and the requester-CC onboarding
  email to `baditaflorin+tmp002@gmail.com` and `baditaflorin@gmail.com`.

The public `sso.lv3.org` edge was still degraded during the replay, so the live
apply used the documented ADR 0317 fallback lane through `docker-runtime-lv3`
instead of silently taking over the separate runtime-control migration work.

## Verification

- `python3 -m pytest -q tests/test_provision_operator.py`
- `./scripts/validate_repo.sh agent-standards`
- exact-main dry-run and `--skip-email` verification from this dedicated
  worktree
- full live replay against Keycloak, Headscale, and the SMTP relay using
  shared `.local/` controller artifacts
- final validation, pre-push gate, and canonical receipt capture after the
  exact-main replay succeeds

## Evidence

- `receipts/live-applies/evidence/2026-04-03-ws-0318-keycloak-precheck-r1.txt`
- `receipts/live-applies/evidence/2026-04-03-ws-0318-keycloak-converge-r1.txt`
- `receipts/live-applies/evidence/2026-04-03-ws-0318-openbao-precheck-r1.txt`
- `receipts/live-applies/evidence/2026-04-03-ws-0318-openbao-converge-r1.txt`
- `receipts/live-applies/evidence/2026-04-03-ws-0318-provision-operator-r1.txt`
- `receipts/live-applies/evidence/2026-04-03-ws-0318-provision-operator-r2.txt`
- `receipts/live-applies/evidence/2026-04-03-ws-0318-provision-operator-r3.txt`
- `receipts/live-applies/evidence/2026-04-03-ws-0318-provision-operator-r4.txt`
- `receipts/live-applies/evidence/2026-04-03-ws-0318-provision-operator-r5.txt`
- `receipts/live-applies/evidence/2026-04-03-ws-0318-provision-operator-r6.txt`
- `receipts/live-applies/evidence/2026-04-03-ws-0318-provision-operator-r7.txt`

## Remaining Mainline Integration

- rebase this worktree onto the latest `origin/main` before cutting protected
  release surfaces
- stamp the canonical live-apply receipt, ADR repo/platform metadata, and any
  exact-main release truth only after the integrated branch is clean
- rerun the broader validation and pre-push automation gates from the
  integrated tree before pushing to `origin/main`
