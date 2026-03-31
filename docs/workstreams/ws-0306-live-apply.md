# Workstream ws-0306-live-apply: Live Apply ADR 0306 From Latest `origin/main`

- ADR: [ADR 0306](../adr/0306-checkov-for-iac-policy-compliance-scanning-of-opentofu-compose-and-ansible.md)
- Title: Land the repo-managed Checkov IaC policy gate on the live validation automation path and verify it end to end
- Status: ready_for_merge
- Branch-Local Receipt: `receipts/live-applies/2026-03-30-adr-0306-checkov-iac-policy-scan-live-apply.json`
- Branch: `codex/ws-0306-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0306-live-apply`
- Owner: codex
- Depends On: `adr-0083-docker-check-runner`, `adr-0087-validation-gate`, `adr-0264-failure-domain-isolated-validation-lanes`, `adr-0266-validation-runner-capability-contracts-and-environment-attestation`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0306-live-apply.md`, `docs/adr/0306-checkov-for-iac-policy-compliance-scanning-of-opentofu-compose-and-ansible.md`, `docs/adr/.index.yaml`, `.config-locations.yaml`, `.gitea/workflows/validate.yml`, `docs/runbooks/iac-policy-scanning.md`, `docs/runbooks/remote-build-gateway.md`, `docs/runbooks/validate-repository-automation.md`, `docs/runbooks/validation-gate.md`, `config/checkov/`, `config/build-server.json`, `config/check-runner-manifest.json`, `config/validation-gate.json`, `config/validation-lanes.yaml`, `config/validation-runner-contracts.json`, `scripts/iac_policy_scan.py`, `tests/test_iac_policy_scan.py`, `tests/test_validation_lanes.py`, `receipts/checkov/`, `receipts/live-applies/2026-03-30-adr-0306-checkov-iac-policy-scan-live-apply.json`, `receipts/live-applies/evidence/2026-03-30-adr-0306-*`

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
- `config/checkov/policy-gate.yaml`
- `config/checkov/skip-checks.yaml`
- `config/checkov/checks/terraform/lv3_proxmox_checks.py`
- `config/build-server.json`
- `config/check-runner-manifest.json`
- `config/validation-gate.json`
- `config/validation-lanes.yaml`
- `config/validation-runner-contracts.json`
- `scripts/iac_policy_scan.py`
- `tests/test_iac_policy_scan.py`
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

## Current Verification

- `python3 -m py_compile scripts/iac_policy_scan.py config/checkov/checks/terraform/lv3_proxmox_checks.py`
  passed
- `uv run --with pytest --with pyyaml --with checkov==3.2.469 pytest -q tests/test_iac_policy_scan.py tests/test_validation_lanes.py`
  returned `10 passed in 10.40s`
- `uv run --with checkov==3.2.469 --with pyyaml python scripts/iac_policy_scan.py`
  passed on the latest rebased branch tree and wrote
  `receipts/checkov/9ce18e9c35cd4c8e97411c92e6dada5c3a2c3dd7.json` plus
  `receipts/checkov/9ce18e9c35cd4c8e97411c92e6dada5c3a2c3dd7.sarif.json`
- the current branch-local baseline is `0` blocking errors, `2` warning-level
  `CKV_LV3_4` findings for `provider.proxmox insecure = true`, and `799`
  note-level upstream Ansible findings

## Remaining Verification Before Mainline Closeout

- run the contract validators and the focused gate test slice with the final
  workstream registration and ADR index updates in place
- run `make remote-validate` and `make pre-push-gate` from this worktree so the
  build-server and controller-local fallback paths both prove the new check
- push the branch and confirm the self-hosted `validate` workflow runs the new
  `iac-policy-scan` step successfully
- after the exact-main integration, update ADR metadata, protected release
  surfaces, and the final live-apply receipt for the canonical merged state
