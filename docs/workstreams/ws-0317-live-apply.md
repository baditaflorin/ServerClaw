# Workstream ws-0317-live-apply: Live Apply ADR 0317 From Latest `origin/main`

- ADR: [ADR 0317](../adr/0317-keycloak-direct-api-operator-provisioning-via-ssh-proxy.md)
- Title: Keycloak direct-API operator provisioning via SSH proxy
- Status: live_applied
- Included In Repo Version: 0.177.137
- Branch-Local Receipt: `receipts/live-applies/2026-04-02-adr-0317-keycloak-direct-api-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-02-adr-0317-keycloak-direct-api-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.86
- Implemented On: 2026-04-02
- Live Applied On: 2026-04-02
- Branch: `codex/ws-0317-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0317-main-integration`
- Owner: codex
- Depends On: `adr-0307-temporary-guest-operator-accounts-with-72-hour-expiry`, `adr-0308-llm-agent-execution-surface-and-connectivity-contracts-for-operator-provisioning`, `adr-0318-repeatable-operator-onboarding-with-cc-audit-trail`
- Conflicts With: `ws-0318-operator-onboarding-iac`
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0317-live-apply.md`, `docs/adr/0317-keycloak-direct-api-operator-provisioning-via-ssh-proxy.md`, `docs/adr/.index.yaml`, `docs/runbooks/operator-onboarding.md`, `scripts/provision_operator.py`, `tests/test_provision_operator.py`, `receipts/live-applies/2026-04-02-adr-0317-keycloak-direct-api-live-apply.json`, `receipts/live-applies/2026-04-02-adr-0317-keycloak-direct-api-mainline-live-apply.json`, `receipts/live-applies/evidence/2026-04-02-ws-0317-*`
- Ownership Manifest: `workstreams.yaml` `ownership_manifest`

## Scope

- restore and re-verify the live Keycloak direct-API provisioning path owned by ADR 0317
- make the repo-managed `scripts/provision_operator.py` fallback safe to run from a dedicated git worktree
- align the fallback role/group mapping with the live Keycloak realm and the canonical ADR 0108/operator-manager definitions
- capture live-apply and automation-validation evidence in a merge-safe branch state

## Non-Goals

- changing protected release surfaces on this workstream branch before the exact-main integration replay
- replacing the broader ADR 0108 roster-first onboarding flow owned by `scripts/operator_manager.py`
- rewriting unrelated generated surfaces already modified elsewhere in this worktree

## Expected Repo Surfaces

- `docs/adr/0317-keycloak-direct-api-operator-provisioning-via-ssh-proxy.md`
- `docs/runbooks/operator-onboarding.md`
- `docs/workstreams/ws-0317-live-apply.md`
- `docs/adr/.index.yaml`
- `scripts/provision_operator.py`
- `tests/test_provision_operator.py`
- `workstreams.yaml`
- `receipts/live-applies/`

## Expected Live Surfaces

- `https://sso.example.com`
- `https://sso.example.com/realms/master/protocol/openid-connect/token`
- `ops@100.64.0.1`
- Keycloak user `matei.busui-tmp`

## Ownership Notes

- this workstream owns the direct-API fallback replay proof, the worktree-safe provisioning script behavior, and the branch-local evidence bundle
- `scripts/provision_operator.py` overlaps the older ADR 0318 authoring workstream, so this live-apply branch explicitly records that conflict instead of silently racing it
- the final exact-main replay must refresh from current `origin/main`, rerun the no-email provisioning verification, and only then stamp the protected release and platform-truth surfaces

## Verification

- `make syntax-check-keycloak` recovered the governed Keycloak syntax path before any live mutation
- `make converge-keycloak` restored the absent Keycloak/OpenBao runtime and its shared publications on the live platform
- direct API verification confirmed fresh admin-token issuance plus the expected `matei.busui-tmp` user, groups, and realm roles after recovery
- `python3 scripts/provision_operator.py ... --skip-email` succeeded from the dedicated git worktree and reused the shared `.local/` password state instead of a worktree-local shadow copy
- `uv run --with pytest python -m pytest -q tests/test_provision_operator.py` passed after the worktree-safe provisioning changes landed
- `make validate` reached the workstream-surface gate on the updated branch and only failed because this worktree already carried unrelated local churn in `docs/site-generated/architecture/dependency-graph.md` and `receipts/ops-portal-snapshot.html`; the exact-main replay therefore needs a clean integration worktree rather than this dirty one
- the clean exact-main integration tree then passed `make validate`, `make remote-validate`, and `make pre-push-gate` after the release cut and canonical-truth refresh

## Merge Criteria

- branch-local receipt records the recovery and direct-API verification evidence
- `scripts/provision_operator.py` succeeds from the dedicated worktree with `--skip-email`
- ADR metadata and `docs/adr/.index.yaml` are updated with the final repo/platform versions from the exact-main replay
- the integrated `main` replay reruns validation from the clean tree and records the canonical mainline receipt

## Notes For The Next Assistant

- Keycloak was down when this workstream started; the first governed recovery was `make converge-keycloak`, not a manual Docker intervention
- this worktree already had unrelated local churn in `docs/site-generated/architecture/dependency-graph.md` and `receipts/ops-portal-snapshot.html`; keep those out of the ADR 0317 commits unless the exact-main integration explicitly regenerates them
