# Workstream ws-0306-live-apply: Live Apply ADR 0306 From Latest `origin/main`

- ADR: [ADR 0306](../adr/0306-checkov-for-iac-policy-compliance-scanning-of-opentofu-compose-and-ansible.md)
- Title: Land the repo-managed Checkov IaC policy gate on the live validation automation path and verify it end to end
- Status: live_applied
- Included In Repo Version: 0.177.115
- Branch-Local Receipt: `receipts/live-applies/2026-03-31-adr-0306-checkov-iac-policy-scan-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-31-adr-0306-checkov-iac-policy-scan-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.75
- Implemented On: 2026-03-31
- Live Applied On: 2026-03-31
- Branch: `codex/ws-0306-mainline-v2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0306-mainline-v2`
- Owner: codex
- Depends On: `adr-0083-docker-check-runner`, `adr-0087-validation-gate`, `adr-0264-failure-domain-isolated-validation-lanes`, `adr-0266-validation-runner-capability-contracts-and-environment-attestation`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0306-live-apply.md`, `docs/adr/0306-checkov-for-iac-policy-compliance-scanning-of-opentofu-compose-and-ansible.md`, `docs/adr/.index.yaml`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/*.md`, `versions/stack.yaml`, `build/platform-manifest.json`, `.config-locations.yaml`, `.gitea/workflows/validate.yml`, `docs/runbooks/iac-policy-scanning.md`, `docs/runbooks/remote-build-gateway.md`, `docs/runbooks/validate-repository-automation.md`, `docs/runbooks/validation-gate.md`, `docs/diagrams/agent-coordination-map.excalidraw`, `docs/diagrams/service-dependency-graph.excalidraw`, `docs/site-generated/architecture/dependency-graph.md`, `config/checkov/`, `config/build-server.json`, `config/check-runner-manifest.json`, `config/validation-gate.json`, `config/validation-lanes.yaml`, `config/validation-runner-contracts.json`, `scripts/iac_policy_scan.py`, `scripts/remote_exec.sh`, `tests/test_iac_policy_scan.py`, `tests/test_validate_repo_cache.py`, `tests/test_validation_lanes.py`, `receipts/checkov/`, `receipts/live-applies/2026-03-31-adr-0306-checkov-iac-policy-scan-live-apply.json`, `receipts/live-applies/2026-03-31-adr-0306-checkov-iac-policy-scan-mainline-live-apply.json`, `receipts/live-applies/evidence/2026-03-31-adr-0306-*`, `receipts/live-applies/evidence/2026-03-31-ws-0306-*`

## Purpose

Implement ADR 0306 by making IaC policy scanning a governed first-class
validation gate check, wiring it through the runner-backed build surfaces and
the self-hosted workflow, and recording the real limits of the pinned offline
Checkov toolchain instead of pretending the repo has native Compose coverage it
does not yet have.

## Scope

- add a repo-managed IaC policy wrapper that emits JSON and SARIF receipts
- enforce blocking Proxmox OpenTofu invariants that upstream Checkov does not
  currently model for this provider
- wire the new `iac-policy-scan` into the validation gate, validation lanes,
  runner contracts, build-server `remote-validate`, and the self-hosted
  workflow
- document the current bounded Compose-template gap and the current warning-only
  `provider "proxmox" { insecure = true }` baseline

## Expected Repo Surfaces

- `docs/adr/0306-checkov-for-iac-policy-compliance-scanning-of-opentofu-compose-and-ansible.md`
- `docs/workstreams/ws-0306-live-apply.md`
- `docs/runbooks/iac-policy-scanning.md`
- `docs/runbooks/remote-build-gateway.md`
- `docs/runbooks/validate-repository-automation.md`
- `docs/runbooks/validation-gate.md`
- `.config-locations.yaml`
- `.gitea/workflows/validate.yml`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/diagrams/service-dependency-graph.excalidraw`
- `docs/site-generated/architecture/dependency-graph.md`
- `config/checkov/policy-gate.yaml`
- `config/checkov/skip-checks.yaml`
- `config/checkov/checks/terraform/lv3_proxmox_checks.py`
- `config/build-server.json`
- `config/check-runner-manifest.json`
- `config/validation-gate.json`
- `config/validation-lanes.yaml`
- `config/validation-runner-contracts.json`
- `scripts/iac_policy_scan.py`
- `scripts/remote_exec.sh`
- `tests/test_iac_policy_scan.py`
- `tests/test_validate_repo_cache.py`
- `tests/test_validation_lanes.py`
- `receipts/checkov/.gitignore`
- `workstreams.yaml`

## Branch-Local Delivery

- added `scripts/iac_policy_scan.py` as the repo-managed wrapper that runs
  Checkov on the governed OpenTofu and Ansible surfaces, emits JSON plus SARIF
  under `receipts/checkov/`, applies path-scoped suppressions, and records the
  current Compose-template gap explicitly
- added `config/checkov/policy-gate.yaml` and `config/checkov/skip-checks.yaml`
  as the ADR 0306 control plane for scan groups, gate levels, and suppressions
- preserved the custom Proxmox rule ids `CKV_LV3_1` through `CKV_LV3_4`; the
  live wrapper currently enforces those through direct HCL inspection because
  offline Checkov does not emit `bpg/proxmox` resources into its native graph
- wired `iac-policy-scan` into the validation gate, the runner manifest, the
  build-server `remote-validate` path, the validation-lane catalog, the runner
  capability contracts, and the self-hosted `validate` workflow

## Verification

- `python3 -m py_compile scripts/iac_policy_scan.py config/checkov/checks/terraform/lv3_proxmox_checks.py`
  passed
- `bash -n scripts/remote_exec.sh`
  passed after replacing the Bash-4-only `mapfile` usage with the repo's
  portable `while read` array loader
- `uv run --with pytest --with pyyaml --with jsonschema --with checkov==3.2.469 pytest -q tests/test_iac_policy_scan.py tests/test_validation_lanes.py tests/test_validation_gate.py tests/test_validation_runner_contracts.py tests/test_remote_exec.py tests/test_validate_repo_cache.py`
  returned `58 passed in 309.49s` and is captured in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-targeted-pytest-r3-0.177.114.txt`
- `uv run --with checkov==3.2.469 --with pyyaml python3 scripts/iac_policy_scan.py`
  passed on the release candidate tree with `0 error, 2 warning, 876 note, 0 suppressed`
  and is captured in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-checkov-scan-r3-0.177.114.txt`
- `python3 scripts/parallel_check.py type-check iac-policy-scan`
  passed earlier on the exact-main candidate in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-parallel-check-r1-0.177.114.txt`;
  a later controller-local refresh timed out the `iac-policy-scan` container at
  the manifest's `300s` cap on the Apple Silicon controller while the direct
  scan plus the build-server validation path below remained green
- `make check-build-server`
  passed on retry, including the immutable snapshot dry-run upload, and is
  captured in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-check-build-server-r2-0.177.114.txt`
- `make remote-validate`
  passed end to end on the remote build-server path with
  `.local/validation-gate/remote-validate-last-run.json` recording
  `"source": "build-server-validate"` and is captured in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-remote-validate-r3-0.177.115.txt`;
  the first `0.177.115` retries exposed active-workstream ownership overlaps on
  `.gitea/workflows/validate.yml` and `.config-locations.yaml`, which were then
  moved under shared contracts before the clean remote pass
- `make pre-push-gate`
  passed end to end on the remote build-server path with
  `.local/validation-gate/last-run.json` recording `"source": "build-server"`
  and is captured in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-pre-push-gate-r1-0.177.115.txt`
- Branch-local hosted validation now succeeds on the private Gitea branch
  snapshot: the branch publish completed in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-gitea-branch-push-r1-0.177.115.txt`,
  `validate.yml` run `177` / job `234` concluded `success`, and the hosted run
  metadata is preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-gitea-validate-run-r1-0.177.115.json`
  and
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-gitea-validate-jobs-r1-0.177.115.json`.
- A shared Gitea runtime outage was recovered through the repo-managed path:
  host evidence in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-gitea-proxy-recovery-r1-0.177.115.txt`
  captured the host proxy serving connection refusals, the runtime converge in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-gitea-runtime-converge-r1-0.177.115.txt`
  restored the private Gitea listener on `10.10.10.20:3003`, and the runner
  converge in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-gitea-runner-converge-r2-0.177.115.txt`
  reasserted the `lv3-gitea-runner` container on `docker-build-lv3` before both
  plays hit the shared non-blocking SBOM tail.
- The exact-main hosted replay is now complete on the private `main` snapshot.
  Source commit `ef2803b3830cf05bb22128dcfa7860f9002b75b0` was published as
  snapshot commit `8d17ace04285790b0eca9de5415b75967cdfecf8` on top of prior
  private-main head `a10101240780d755f27988ee7352ac4f7cc74a7c`, preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-origin-main-candidate-source-r2.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0306-gitea-main-head-before-r2.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0306-gitea-main-snapshot-commit-r2.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0306-gitea-main-push-r2.txt`,
  and
  `receipts/live-applies/evidence/2026-03-31-ws-0306-gitea-main-head-after-r2.txt`.
- Hosted private-main verification then completed cleanly: `release-bundle.yml`
  run `178` / jobs `235` and `236` concluded `success`, and `validate.yml` run
  `179` / job `237` concluded `success`, preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-main-gitea-runs-r1.json`,
  `receipts/live-applies/evidence/2026-03-31-ws-0306-main-run-178-status-r1.json`,
  `receipts/live-applies/evidence/2026-03-31-ws-0306-main-run-178-jobs-r1.json`,
  `receipts/live-applies/evidence/2026-03-31-ws-0306-main-run-179-status-r1.json`,
  and
  `receipts/live-applies/evidence/2026-03-31-ws-0306-main-run-179-jobs-r1.json`.
- The canonical-truth refresh is now validated on the settled branch: `uv run
  --with pyyaml --with jsonschema python3 scripts/live_apply_receipts.py --validate`,
  `uv run --with pyyaml --with jsonschema python3 scripts/validate_repository_data_models.py --validate`,
  `uvx --from pyyaml python3 scripts/canonical_truth.py --check`,
  `uv run --with pyyaml --with jsonschema python3 scripts/platform_manifest.py --check`,
  `git diff --check`, and
  `LV3_SNAPSHOT_BRANCH=main ./scripts/validate_repo.sh agent-standards generated-docs generated-portals`
  all passed after refreshing stale diagrams with
  `uvx --from pyyaml python3 scripts/generate_diagrams.py --write`, preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-live-apply-receipts-validate-r1-0.177.115.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-data-models-r1-0.177.115.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-canonical-truth-check-r1-0.177.115.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-platform-manifest-check-r1-0.177.115.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-git-diff-check-r1-0.177.115.txt`,
  and
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-agent-standards-generated-r2-0.177.115.txt`.
- the current release-candidate baseline is `0` blocking errors, `2`
  warning-level `CKV_LV3_4` findings for `provider.proxmox insecure = true`,
  and `876` note-level upstream Ansible findings at repo version `0.177.115`

## Results

- ADR 0306 is now implemented in repository version `0.177.115` and first
  verified live on platform version `0.130.75`.
- The branch-local receipt remains the pre-integration audit trail for the live
  replay from the latest `origin/main` lineage, while the canonical mainline
  receipt records the exact-main hosted success boundary and the protected
  canonical-truth updates for merge to `main`.
- No merge-to-main follow-up remains for ADR 0306 itself; the settled exact-main
  replay, receipts, and canonical-truth surfaces are now ready to be carried
  onto `origin/main`.
