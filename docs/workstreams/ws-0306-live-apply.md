# Workstream ws-0306-live-apply: Live Apply ADR 0306 From Latest `origin/main`

- ADR: [ADR 0306](../adr/0306-checkov-for-iac-policy-compliance-scanning-of-opentofu-compose-and-ansible.md)
- Title: Land the repo-managed Checkov IaC policy gate on the live validation automation path and verify it end to end
- Status: in_progress
- Branch-Local Receipt: `receipts/live-applies/2026-03-31-adr-0306-checkov-iac-policy-scan-live-apply.json`
- Branch: `codex/ws-0306-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0306-live-apply`
- Owner: codex
- Depends On: `adr-0083-docker-check-runner`, `adr-0087-validation-gate`, `adr-0264-failure-domain-isolated-validation-lanes`, `adr-0266-validation-runner-capability-contracts-and-environment-attestation`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0306-live-apply.md`, `docs/adr/0306-checkov-for-iac-policy-compliance-scanning-of-opentofu-compose-and-ansible.md`, `docs/adr/.index.yaml`, `.config-locations.yaml`, `.gitea/workflows/validate.yml`, `docs/runbooks/iac-policy-scanning.md`, `docs/runbooks/remote-build-gateway.md`, `docs/runbooks/validate-repository-automation.md`, `docs/runbooks/validation-gate.md`, `docs/diagrams/agent-coordination-map.excalidraw`, `docs/diagrams/service-dependency-graph.excalidraw`, `docs/site-generated/architecture/dependency-graph.md`, `config/checkov/`, `config/build-server.json`, `config/check-runner-manifest.json`, `config/validation-gate.json`, `config/validation-lanes.yaml`, `config/validation-runner-contracts.json`, `scripts/iac_policy_scan.py`, `tests/test_iac_policy_scan.py`, `tests/test_validation_lanes.py`, `receipts/checkov/`, `receipts/live-applies/2026-03-31-adr-0306-checkov-iac-policy-scan-live-apply.json`, `receipts/live-applies/evidence/2026-03-31-adr-0306-*`

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
- `uv run --with pytest --with pyyaml --with jsonschema --with checkov==3.2.469 pytest -q tests/test_iac_policy_scan.py tests/test_validation_lanes.py tests/test_validation_gate.py tests/test_validation_runner_contracts.py tests/test_remote_exec.py`
  returned `38 passed in 99.51s`
- `uv run --with checkov==3.2.469 --with pyyaml python scripts/iac_policy_scan.py`
  passed on the latest rebased branch tree and wrote
  `receipts/checkov/725158e3025de99777b4c1540b320a25bc47f5b2.json` plus
  `receipts/checkov/725158e3025de99777b4c1540b320a25bc47f5b2.sarif.json`
- `python3 scripts/parallel_check.py type-check iac-policy-scan`
  passed with `type-check` in `56.16s` and `iac-policy-scan` in `218.23s`
- `make remote-validate`
  passed end to end on the build-server path and is captured in
  `receipts/live-applies/evidence/2026-03-31-adr-0306-remote-validate.txt`
- `make pre-push-gate`
  exercised the full remote-first push gate and failed only at
  `generated-docs` because the canonical `README.md` truth on the branch is
  intentionally left untouched until the exact-main integration step
- the current branch-local baseline is `0` blocking errors, `2` warning-level
  `CKV_LV3_4` findings for `provider.proxmox insecure = true`, and `799`
  note-level upstream Ansible findings

## Remaining Verification Before Mainline Closeout

- push the branch and confirm the self-hosted `validate` workflow runs the new
  `iac-policy-scan` step successfully
- during the exact-main integration, update the protected `README.md`,
  `VERSION`, `changelog.md`, and `versions/stack.yaml` surfaces together so
  `make pre-push-gate` can pass without the current branch-local README
  exception
- after the exact-main integration, update ADR metadata and write the final
  live-apply receipt for the canonical merged state
