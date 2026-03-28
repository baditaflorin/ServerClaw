# Workstream WS-0206: Ports And Adapters Live Apply

- ADR: [ADR 0206](../adr/0206-ports-and-adapters-for-external-integrations.md)
- Title: Live apply the ports-and-adapters architecture on the repo-managed operator access workflow
- Status: live_applied
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: 0.130.35
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
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

- `python3 -m py_compile scripts/operator_manager.py platform/operator_access/__init__.py platform/operator_access/http.py platform/operator_access/ports.py platform/operator_access/adapters.py tests/test_operator_manager.py tests/test_operator_access_adapters.py` passed
- `uv run --with pytest --with pyyaml pytest -q tests/test_operator_manager.py tests/test_operator_access_adapters.py` passed with `15 passed in 0.16s`
- `uv run --with pyyaml python scripts/operator_manager.py validate`, `make workflow-info WORKFLOW=operator-onboard`, `make workflow-info WORKFLOW=operator-offboard`, `make workflow-info WORKFLOW=sync-operators`, `make workflow-info WORKFLOW=quarterly-access-review`, `./scripts/validate_repo.sh agent-standards`, `uv run --with pyyaml python scripts/operator_manager.py --emit-json quarterly-review --dry-run`, and `git diff --check` all passed
- The controller-side live replay used `LV3_OPENBAO_URL=http://127.0.0.1:18201` plus the shared controller-local Keycloak and OpenBao bootstrap secrets from the main checkout, and `curl -fsS http://127.0.0.1:18201/v1/sys/health` returned `initialized: true` and `sealed: false`
- `LiveBackend.ensure_prerequisites()` from commit `74cc510ddd7629793d8e41bbb4bbfce015e2c61f` upserted the repo-managed OpenBao policies and confirmed the governed Keycloak roles and groups exist
- The first live inventory showed Keycloak `active` but OpenBao `missing` for `florin.badita`; running `backend.secret_authority.ensure_entity()` created OpenBao entity `125fb8b1-c72c-a320-a537-3d415dda752e`, and the follow-up inventory returned Keycloak `active`, OpenBao `active`, Tailscale `unavailable` because `TAILSCALE_TAILNET` is unset, and step-ca `unknown` because no controller-local state has been recorded yet

## Outcome

- the repo now exposes explicit ports and adapters for the critical ADR 0108 integrations with Keycloak, OpenBao, Tailscale, Mattermost, and step-ca under `platform/operator_access/`
- `scripts/operator_manager.py` is now a composition root and orchestration layer instead of a provider-specific implementation bundle
- the workstream repaired pre-existing live drift by recreating the missing OpenBao entity for `florin.badita` and verifying the repaired state through the new port-backed inventory path

## Mainline Integration

- protected integration files remain intentionally unchanged on this workstream branch: `VERSION`, release sections in `changelog.md`, canonical observed state in `versions/stack.yaml`, and the top-level README integrated status summary
- merge-to-main still needs the official repo-version attribution for ADR 0206 plus any canonical-truth updates that the final integrated replay decides to record
- the structured live receipt for this branch replay is `2026-03-28-adr-0206-ports-and-adapters-live-apply`

## Notes For The Next Assistant

- this workstream intentionally avoids `VERSION`, release sections in `changelog.md`, `versions/stack.yaml`, and the top-level integrated `README.md` status summary until a final main integration step is performed
