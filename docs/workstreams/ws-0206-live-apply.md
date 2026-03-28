# Workstream WS-0206: Ports And Adapters Live Apply

- ADR: [ADR 0206](../adr/0206-ports-and-adapters-for-external-integrations.md)
- Title: Live apply the ports-and-adapters architecture on the repo-managed operator access workflow
- Status: in-progress
- Branch: `codex/ws-0206-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0206-live-apply`
- Owner: codex
- Depends On: `adr-0108-operator-onboarding-and-offboarding`, `adr-0122-windmill-operator-access-admin`, `adr-0208-dependency-direction-and-composition-roots`
- Conflicts With: none
- Shared Surfaces: `scripts/operator_manager.py`, `platform/operator_access/`, `docs/adr/0206-ports-and-adapters-for-external-integrations.md`, `docs/runbooks/operator-onboarding.md`, `docs/runbooks/operator-offboarding.md`, `tests/test_operator_manager.py`, `tests/test_operator_access_adapters.py`, `receipts/live-applies/2026-03-28-adr-0206-ports-and-adapters-live-apply.json`, `workstreams.yaml`

## Scope

- extract the critical operator-access integrations behind explicit ports and product adapters
- keep `scripts/operator_manager.py` as the composition root and orchestration layer rather than a provider-specific implementation bundle
- verify the controller-side live ADR 0108 path against the existing production Keycloak and OpenBao state from this isolated worktree
- leave protected release and canonical-truth files for the final main integration step unless and until this branch becomes that step

## Expected Repo Surfaces

- `scripts/operator_manager.py`
- `platform/operator_access/__init__.py`
- `platform/operator_access/http.py`
- `platform/operator_access/ports.py`
- `platform/operator_access/adapters.py`
- `tests/test_operator_manager.py`
- `tests/test_operator_access_adapters.py`
- `docs/adr/0206-ports-and-adapters-for-external-integrations.md`
- `docs/workstreams/ws-0206-live-apply.md`
- `workstreams.yaml`

## Expected Live Surfaces

- controller-local ADR 0108 sync and inventory against live Keycloak and OpenBao
- optional Tailscale, step-ca, and Mattermost hooks remaining graceful when their runtime configuration is absent

## Verification

- in progress

## Notes For The Next Assistant

- this workstream intentionally avoids `VERSION`, release sections in `changelog.md`, `versions/stack.yaml`, and the top-level integrated `README.md` status summary until a final main integration step is performed
