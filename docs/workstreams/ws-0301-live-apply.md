# Workstream ws-0301-live-apply: Live Apply ADR 0301 From Latest `origin/main`

- ADR: [ADR 0301](../adr/0301-semgrep-for-sast-and-application-code-security-scanning-in-the-ci-gate.md)
- Title: Wire Semgrep SAST into the shared validation gate and verify the CI and build-server paths end to end from latest `origin/main`
- Status: in_progress
- Branch: `codex/ws-0301-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0301-live-apply`
- Owner: codex
- Depends On: `adr-0083-docker-based-check-runners`, `adr-0087-repository-validation-gate`, `adr-0229-gitea-actions-runners`, `adr-0264-failure-domain-isolated-validation-lanes`, `adr-0266-validation-runner-capability-contracts`, `adr-0267-expiring-gate-bypass-waivers-with-structured-reason-codes`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0301-live-apply.md`, `docs/adr/0301-semgrep-for-sast-and-application-code-security-scanning-in-the-ci-gate.md`, `docs/runbooks/validation-gate.md`, `docs/runbooks/validate-repository-automation.md`, `docs/runbooks/docker-check-runners.md`, `docs/adr/.index.yaml`, `Makefile`, `.config-locations.yaml`, `.gitea/workflows/validate.yml`, `.github/workflows/validate.yml`, `config/semgrep/`, `config/validation-gate.json`, `config/check-runner-manifest.json`, `config/validation-lanes.yaml`, `config/validation-runner-contracts.json`, `config/workflow-catalog.json`, `docker/check-runners/security/`, `docs/diagrams/agent-coordination-map.excalidraw`, `platform/repo.py`, `scripts/run_gate.py`, `scripts/semgrep_gate.py`, `scripts/validate_repo.sh`, `scripts/validation_runner_contracts.py`, `tests/test_parallel_check.py`, `tests/test_semgrep_gate.py`, `tests/test_validation_gate.py`, `tests/test_validation_lanes.py`, `tests/test_validation_runner_contracts.py`, `receipts/live-applies/`

## Scope

- add the repo-managed Semgrep wrapper, rule packs, and SARIF receipt path
- wire the Semgrep check into `make validate`, the lane-aware validation gate, and both hosted CI workflows
- keep the published security runner on its existing tag while proving Semgrep runs through the Python runner on the remote build-server gate
- verify the private Gitea workflow path against the pushed branch and capture live-apply evidence for merge-to-main

## Non-Goals

- changing unrelated validation lanes or protected release files before the final exact-main integration step
- replacing Trivy, Gitleaks, or Checkov; ADR 0301 complements those checks rather than superseding them
- widening Semgrep rule coverage beyond the initial repo-managed Python, Dockerfile, and governed executable-surface scope needed to land the ADR safely

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0301-live-apply.md`
- `docs/adr/0301-semgrep-for-sast-and-application-code-security-scanning-in-the-ci-gate.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/validation-gate.md`
- `docs/runbooks/validate-repository-automation.md`
- `docs/runbooks/docker-check-runners.md`
- `.config-locations.yaml`
- `.gitea/workflows/validate.yml`
- `.github/workflows/validate.yml`
- `Makefile`
- `config/semgrep/`
- `config/validation-gate.json`
- `config/check-runner-manifest.json`
- `config/validation-lanes.yaml`
- `config/validation-runner-contracts.json`
- `config/workflow-catalog.json`
- `docker/check-runners/security/`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `platform/repo.py`
- `scripts/run_gate.py`
- `scripts/semgrep_gate.py`
- `scripts/validate_repo.sh`
- `scripts/validation_runner_contracts.py`
- `tests/test_parallel_check.py`
- `tests/test_semgrep_gate.py`
- `tests/test_validation_gate.py`
- `tests/test_validation_lanes.py`
- `tests/test_validation_runner_contracts.py`
- `receipts/live-applies/`

## Expected Live Surfaces

- `semgrep-sast` runs successfully from `registry.lv3.org/check-runner/python:3.12.10` with an in-container install of `semgrep==1.155.0`
- the remote pre-push gate succeeds with the new `semgrep-sast` check enabled
- branch validation on the private Gitea runner executes `.gitea/workflows/validate.yml` and archives the Semgrep SARIF artifact

## Verification

- In progress. This section will be replaced with the exact local, remote, and CI verification results captured during the live apply.

## Remaining For Merge-To-Main

- In progress. This workstream is expected to perform the final exact-main integration step itself once the branch-local and live gate proofs are complete.
