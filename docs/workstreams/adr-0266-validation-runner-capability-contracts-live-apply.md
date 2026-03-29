# Workstream ADR 0266: Validation Runner Capability Contracts Live Apply

- ADR: [ADR 0266](../adr/0266-validation-runner-capability-contracts-and-environment-attestation.md)
- Title: Make validation runners declare capability contracts and emit per-run environment attestations
- Status: in_progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0266-validation-runner-capability-contracts`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0266-validation-runner-capability-contracts`
- Owner: codex
- Depends On: `adr-0082-remote-build-execution-gateway`, `adr-0083-docker-based-check-runner`, `adr-0087-repository-validation-gate`, `adr-0156-agent-session-workspace-isolation`, `adr-0227-bounded-command-execution-via-systemd-run-and-approved-wrappers`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/adr/0266-validation-runner-capability-contracts-and-environment-attestation.md`, `docs/workstreams/adr-0266-validation-runner-capability-contracts-live-apply.md`, `docs/adr/.index.yaml`, `.config-locations.yaml`, `config/build-server.json`, `config/check-runner-manifest.json`, `config/validation-gate.json`, `config/validation-runner-contracts.json`, `docs/schema/validation-runner-contracts.schema.json`, `scripts/gate_status.py`, `scripts/parallel_check.py`, `scripts/policy_checks.py`, `scripts/remote_exec.sh`, `scripts/run_gate.py`, `scripts/validate_repository_data_models.py`, `scripts/validation_runner_contracts.py`, `config/windmill/scripts/post-merge-gate.py`, `policy/conftest/repository.rego`, `docs/runbooks/remote-build-gateway.md`, `docs/runbooks/validation-gate.md`, `receipts/live-applies/2026-03-29-adr-0266-validation-runner-capability-contracts-live-apply.json`, `receipts/live-applies/2026-03-29-adr-0266-validation-runner-capability-contracts-mainline-live-apply.json`, `receipts/live-applies/evidence/2026-03-29-adr-0266-*`, `tests/test_parallel_check.py`, `tests/test_policy_checks.py`, `tests/test_post_merge_gate.py`, `tests/test_remote_exec.py`, `tests/test_validation_gate.py`, `tests/test_validation_runner_contracts.py`

## Scope

- add one canonical validation-runner contract catalog that declares runner identity, architecture, tooling, network reachability class, scratch cleanup guarantees, and supported validation lanes
- make the build-server gateway, manifest-backed validation gate, and worker post-merge replay emit a per-run environment attestation alongside runner identity
- fail closed as `runner_unavailable` when a requested validation lane cannot run on the attested runner instead of misreporting a repository-content failure
- verify the remote build-server path, controller-local fallback path, and worker post-merge path end to end and record durable evidence in-repo

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/adr/0266-validation-runner-capability-contracts-and-environment-attestation.md`
- `docs/workstreams/adr-0266-validation-runner-capability-contracts-live-apply.md`
- `docs/adr/.index.yaml`
- `.config-locations.yaml`
- `config/build-server.json`
- `config/check-runner-manifest.json`
- `config/validation-gate.json`
- `config/validation-runner-contracts.json`
- `docs/schema/validation-runner-contracts.schema.json`
- `scripts/gate_status.py`
- `scripts/parallel_check.py`
- `scripts/policy_checks.py`
- `scripts/remote_exec.sh`
- `scripts/run_gate.py`
- `scripts/validate_repository_data_models.py`
- `scripts/validation_runner_contracts.py`
- `config/windmill/scripts/post-merge-gate.py`
- `policy/conftest/repository.rego`
- `docs/runbooks/remote-build-gateway.md`
- `docs/runbooks/validation-gate.md`
- `receipts/live-applies/2026-03-29-adr-0266-validation-runner-capability-contracts-live-apply.json`
- `receipts/live-applies/2026-03-29-adr-0266-validation-runner-capability-contracts-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-03-29-adr-0266-*`
- `tests/test_parallel_check.py`
- `tests/test_policy_checks.py`
- `tests/test_post_merge_gate.py`
- `tests/test_remote_exec.py`
- `tests/test_validation_gate.py`
- `tests/test_validation_runner_contracts.py`

## Expected Live Surfaces

- `make remote-validate` records a status payload that names the build-server runner, its declared contract, and its attested environment facts for the executed validation slice
- `make pre-push-gate` records the same runner identity and attestation data whether the gate runs on the build server or falls back locally
- the worker-side `post_merge_gate` replay records a runner identity and attestation for the live worker checkout
- an unavailable or mismatched runner fails as `runner_unavailable` before content checks are misreported as repository defects

## Verification Plan

- targeted pytest coverage for the new contract loader, remote gateway, gate orchestration, worker replay, and policy context
- `./scripts/validate_repo.sh data-models policy`
- `./scripts/validate_repo.sh workstream-surfaces agent-standards`
- build-server path verification with `make check-build-server` and `make remote-validate`
- local fallback verification by forcing the remote path unavailable and confirming the recorded runner/attestation changes
- worker post-merge verification from the live runtime checkout after the change lands on `main`

## Mainline Integration Notes

- do not touch `VERSION`, `changelog.md`, `README.md`, or `versions/stack.yaml` on this workstream branch
- once the branch proof is complete, merge to the latest `origin/main`, then update protected release truth and record the exact-main replay receipt
