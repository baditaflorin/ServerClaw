# Workstream ws-0297-live-apply: Live Apply ADR 0297 From Latest `origin/main`

- ADR: [ADR 0297](../adr/0297-renovate-bot-as-the-automated-stack-version-upgrade-proposer.md)
- Title: Deploy the repo-managed Renovate proposal path through Gitea Actions, OpenBao, and Harbor
- Status: live_applied
- Included In Repo Version: 0.177.112
- Branch-Local Receipt: `receipts/live-applies/2026-03-31-adr-0297-renovate-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-31-adr-0297-renovate-mainline-live-apply.json`
- Follow-up Receipt: `receipts/live-applies/2026-03-31-adr-0297-renovate-followups-live-apply.json`
- Live Applied In Platform Version: 0.130.74
- Implemented On: 2026-03-31
- Live Applied On: 2026-03-31
- Branch: `codex/ws-0297-live-apply-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0297-live-apply-r2`
- Owner: codex
- Depends On: `adr-0068`, `adr-0077`, `adr-0083`, `adr-0087`, `adr-0119`, `adr-0143`, `adr-0229`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0297`, `docs/workstreams/ws-0297-live-apply.md`, `docs/runbooks/configure-gitea.md`, `docs/runbooks/configure-openbao.md`, `docs/runbooks/configure-renovate.md`, `docs/runbooks/configure-harbor.md`, `docs/runbooks/live-apply-receipts-and-verification-evidence.md`, `docs/runbooks/validate-repository-automation.md`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `.gitea/workflows/renovate.yml`, `.gitea/workflows/release-bundle.yml`, `.gitea/workflows/validate.yml`, `renovate.json`, `scripts/live_apply_receipts.py`, `scripts/parallel_check.py`, `scripts/validate_repo.sh`, `scripts/validate_renovate_contract.py`, `scripts/renovate_runtime_token.py`, `scripts/renovate_stack_digest_guard.py`, `scripts/sbom_scanner.py`, `platform/repo.py`, `README.md`, `build/platform-manifest.json`, `docs/diagrams/agent-coordination-map.excalidraw`, `collections/ansible_collections/lv3/platform/roles/common/`, `collections/ansible_collections/lv3/platform/roles/harbor_runtime/`, `collections/ansible_collections/lv3/platform/roles/openbao_runtime/`, `collections/ansible_collections/lv3/platform/roles/gitea_runtime/`, `collections/ansible_collections/lv3/platform/roles/gitea_runner/`, `tests/`, `tests/test_live_apply_receipts.py`, `tests/test_parallel_check.py`, `tests/test_sbom_scanner.py`, `receipts/live-applies/`, `workstreams.yaml`

## Scope

- add a root `renovate.json` contract that manages the currently supported stack image and version surfaces
- run Renovate as a scheduled/manual Gitea Actions workflow on `docker-build-lv3`
- deliver the Renovate bootstrap credential through OpenBao onto the runner host and mint a short-lived scoped Gitea token at workflow runtime
- pull the Renovate runtime image through Harbor and pin it to a digest in the workflow
- verify the live path end to end, including repo validation and workflow execution from the latest synchronized `origin/main` base

## Non-Goals

- updating protected release files on this workstream branch before an exact-main integration step
- widening Gitea or OpenBao publication beyond the current private-only control-plane model
- granting Renovate autonomous deploy or merge permissions

## Expected Repo Surfaces

- `docs/adr/0297-renovate-bot-as-the-automated-stack-version-upgrade-proposer.md`
- `docs/workstreams/ws-0297-live-apply.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/configure-gitea.md`
- `docs/runbooks/configure-openbao.md`
- `docs/runbooks/configure-renovate.md`
- `docs/runbooks/configure-harbor.md`
- `docs/runbooks/live-apply-receipts-and-verification-evidence.md`
- `docs/runbooks/validate-repository-automation.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `.gitea/workflows/renovate.yml`
- `.gitea/workflows/release-bundle.yml`
- `.gitea/workflows/validate.yml`
- `renovate.json`
- `scripts/live_apply_receipts.py`
- `scripts/parallel_check.py`
- `scripts/validate_repo.sh`
- `scripts/validate_renovate_contract.py`
- `scripts/renovate_runtime_token.py`
- `scripts/renovate_stack_digest_guard.py`
- `scripts/sbom_scanner.py`
- `platform/repo.py`
- `README.md`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `scripts/generate_platform_vars.py`
- `.ansible-lint-ignore`
- `config/ansible-role-idempotency.yml`
- `collections/ansible_collections/lv3/platform/roles/common/`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/`
- `collections/ansible_collections/lv3/platform/roles/harbor_runtime/`
- `collections/ansible_collections/lv3/platform/roles/openbao_runtime/`
- `collections/ansible_collections/lv3/platform/roles/openbao_postgres_backend/`
- `collections/ansible_collections/lv3/platform/roles/gitea_runtime/`
- `collections/ansible_collections/lv3/platform/roles/gitea_runner/`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`
- `collections/ansible_collections/lv3/platform/roles/mail_platform_runtime/`
- `collections/ansible_collections/lv3/platform/roles/postgres_vm/`
- `tests/`
- `tests/test_docker_runtime_role.py`
- `tests/test_generate_platform_vars.py`
- `tests/test_gitea_workflows.py`
- `tests/test_harbor_runtime_role.py`
- `tests/test_live_apply_receipts.py`
- `tests/test_keycloak_runtime_role.py`
- `tests/test_mail_platform_runtime_role.py`
- `tests/test_openbao_compose_env_helper.py`
- `tests/test_openbao_postgres_backend_role.py`
- `tests/test_parallel_check.py`
- `tests/test_sbom_scanner.py`
- `tests/test_postgres_vm_role.py`
- `receipts/live-applies/`
- `workstreams.yaml`

## Expected Live Surfaces

- `docker-runtime-lv3` publishes the private OpenBao HTTP listener on its guest IP only for `docker-build-lv3`
- `docker-runtime-lv3` runs the managed Gitea stack with a repo-managed `renovate-bot` identity
- `docker-build-lv3` runs the managed Gitea runner with a mounted OpenBao-rendered Renovate bootstrap env file
- a manual or scheduled Gitea Actions run executes Renovate successfully from the Harbor-pinned image using a short-lived token minted at job runtime

## Verification

- The integrated `0.177.112 / 0.130.74` tree passes the direct release-tree validation bundle: `uv run --with pytest --with pyyaml --with jsonschema --with jinja2 pytest -q tests/test_gitea_workflows.py tests/test_renovate_automation.py tests/test_gitea_runtime_role.py` returned `23 passed in 0.81s`, `uv run --with pyyaml python3 scripts/validate_renovate_contract.py` passed, `npx --yes --package renovate@42.76.4 renovate-config-validator renovate.json` reported `Config validated successfully`, `uv run --with pyyaml --with jsonschema python3 scripts/live_apply_receipts.py --validate` passed, `uv run --with pyyaml --with jsonschema python3 scripts/validate_repository_data_models.py --validate` passed after syncing `versions/stack.yaml.release_tracks.platform_versioning.current`, `./scripts/validate_repo.sh agent-standards` passed, and `git diff --check` stayed clean.
- The focused repo automation slice passed after the final hosted-runtime repairs: `uv run --with pytest --with pyyaml --with jsonschema --with jinja2 pytest -q tests/test_gitea_workflows.py tests/test_renovate_automation.py tests/test_gitea_runtime_role.py` returned `23 passed in 0.83s`, `uv run --with pyyaml python3 scripts/validate_renovate_contract.py` passed, and the pinned runtime validator `npx --yes --package renovate@42.76.4 renovate-config-validator renovate.json` reported `Config validated successfully`.
- The runner bootstrap and credential path remain live on production: the branch evidence proves `/opt/gitea-runner/credentials/renovate/renovate.env` is rendered on `docker-build-lv3`, the runner container sees `/var/run/lv3/renovate/renovate.env`, and the Gitea admin API returns an active `renovate-bot` identity.
- Branch-local hosted validation now succeeds from the latest `origin/main` lineage on the private Gitea branch snapshot: `release-bundle.yml` run `162` and `validate.yml` run `163` both concluded `success` on `codex/ws-0297-live-apply`.
- Branch-local hosted Renovate is now live end to end: `renovate.yml` run `165` / job `219` concluded `success`, created the `Renovate Dashboard` issue (`#3`), and opened governed PRs `#1` and `#2` against the private `ops/proxmox_florin_server` repo.
- The exact-main publication step then replayed the verified source tree onto the private Gitea `main` snapshot and re-verified the hosted mainline paths that matter for ADR 0297: `validate.yml` run `169` concluded `success`, `renovate.yml` run `170` concluded `success`, and the mainline replay kept the Renovate dashboard plus governed update PR creation live after the protected integration step.
- `make remote-validate` from the released tree passed every selected lane after the `versions/stack.yaml` release-track sync except the intentional `workstream-surfaces` guard, which rejects a branch once its owning workstream is terminal.
- `make pre-push-gate` from the released tree showed the same repo-content result on its remote primary-branch leg: every lane passed except the intentional `workstream-surfaces` guard. The local fallback then repeated that terminal-branch ownership failure and also timed out `ansible-lint` after `600` seconds on the local arm64 wrapper path.
- Follow-up remediation recovered docker-runtime capacity (`df -h /` shows 14G free), restarted the OpenBao, Gitea, and Harbor stacks, and verified OpenBao is unsealed, Gitea `/api/healthz` returns `pass`, and Harbor `/v2/` returns the expected 401 auth challenge.
- The SBOM scanner host-path update passed `pytest -q tests/test_sbom_scanner.py`, the Renovate automation slice remained green, `./scripts/validate_repo.sh agent-standards` passed, and `release-bundle.yml` run `190` concluded `success` on the private `main` snapshot.
- One stale Renovate PR-sync validation run still needs a fresh replay after mainline updates so the legacy PR branch checkout can be rebuilt.

## Results

- ADR 0297 is now implemented in repository version `0.177.112` and first verified live on platform version `0.130.74`.
- The private Gitea Actions path on `docker-build-lv3` now runs the Harbor-pinned Renovate runtime with a short-lived scoped token minted at job start from the OpenBao-rendered bootstrap bundle.
- The private Gitea `main` snapshot now has a verified Renovate dashboard plus governed update-PR creation path on top of the exact source tree that settled this ADR's workflow contract.
- The validation gate now maps SBOM paths through the runner host workspace, restoring grype scan success on pull request workflows.
- The branch-local receipt remains the pre-integration audit trail, while the canonical mainline receipt records the exact-main hosted verification that backs the protected release and canonical-truth updates.

## Mainline Closeout

- None for ADR 0297 itself. The protected release and canonical-truth surfaces are refreshed, and the canonical mainline receipt now records the first verified platform version for the ADR.
- Shared platform follow-up remains after merge: recycle stale Renovate PR branches so every `pull_request_sync` validation run starts from a complete checkout workspace.
