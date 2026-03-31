# Workstream ws-0306-live-apply: Live Apply ADR 0306 From Latest `origin/main`

- ADR: [ADR 0306](../adr/0306-checkov-for-iac-policy-compliance-scanning-of-opentofu-compose-and-ansible.md)
- Title: Land the repo-managed Checkov IaC policy gate on the live validation automation path and verify it end to end
- Status: live_applied
- Included In Repo Version: 0.177.119
- Branch-Local Receipt: `receipts/live-applies/2026-03-31-adr-0306-checkov-iac-policy-scan-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-31-adr-0306-checkov-iac-policy-scan-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.75
- Implemented On: 2026-03-31
- Live Applied On: 2026-03-31
- Branch: `codex/ws-0306-mainline-final-r3`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0306-main-context-v2`
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
- The rebased mainline integration cut now lands on latest `origin/main` commit
  `2411a7cd428e0eba17168aa5eed66f04c4ed48dd`: `uv run --with pyyaml python3
  scripts/release_manager.py status --json`, the patch dry run, and the actual
  `--bump patch` release write all completed cleanly and cut repository version
  `0.177.119`, preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-final-r3-release-status-r1-0.177.118.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-final-r3-release-dry-run-r1-0.177.118.txt`,
  and
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-final-r3-release-write-r1-0.177.119.txt`.
- The rebased `0.177.119` branch candidate passed `make check-build-server` in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-final-r3-check-build-server-r1-0.177.119.txt`;
  `make remote-validate` then proved every substantive ADR 0306 lane, and the
  only remaining non-pass was the designed terminal-workstream
  `workstream-surfaces` guard on branch `codex/ws-0306-mainline-final-r3`,
  preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-mainline-final-r3-remote-validate-r1-0.177.119.txt`.
- To keep the build-server validation path healthy, inactive ADR 0306 session
  roots were removed only after confirming no active process still referenced
  them; that bounded manual cleanup is preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-build-server-session-cleanup-r1-0.177.115.txt`
  and the runbook now records the same safety rule.
- The committed `0.177.119` candidate was then replayed from detached `HEAD`
  commit `56fd6422c43789a68660150baaf0e7d0b0376b99`, where the branch guard no
  longer applies: `make check-build-server` and `make remote-validate` both
  passed and are preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-exact-main-verify-check-build-server-r1-0.177.119.txt`
  and
  `receipts/live-applies/evidence/2026-03-31-ws-0306-exact-main-verify-remote-validate-r1-0.177.119.txt`.
- The detached exact-head `pre-push-gate` wrapper was exercised twice. Both
  replays passed every remote blocking check except `packer-validate` and
  `tofu-validate` when `registry.lv3.org/check-runner/infra:2026.03.23`
  returned transient `502 Bad Gateway` responses, preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-exact-main-verify-pre-push-gate-r1-0.177.119.txt`
  and
  `receipts/live-applies/evidence/2026-03-31-ws-0306-exact-main-verify-pre-push-gate-r2-0.177.119.txt`.
  The second replay also proved controller-local `packer-validate` and
  `tofu-validate`, but the wrapper still stayed non-green because the fallback
  reran already-green heavy checks under fixed controller timeouts.
- The remaining fallback-only timeout victims were rechecked directly on the
  detached exact head: the governed `ansible-lint` surface passed with warnings
  only in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-exact-main-verify-ansible-lint-r1-0.177.119.txt`,
  and the direct Trivy filesystem `security-scan` passed in
  `receipts/live-applies/evidence/2026-03-31-ws-0306-exact-main-verify-security-scan-r1-0.177.119.txt`.
- The canonical-truth refresh remains validated on the settled tree: `uv run
  --with pyyaml --with jsonschema python3 scripts/live_apply_receipts.py --validate`,
  `uv run --with pyyaml --with jsonschema python3 scripts/validate_repository_data_models.py --validate`,
  `uvx --from pyyaml python3 scripts/canonical_truth.py --check`,
  `uv run --with pyyaml --with jsonschema python3 scripts/platform_manifest.py --check`,
  `git diff --check`, and
  `LV3_SNAPSHOT_BRANCH=main ./scripts/validate_repo.sh agent-standards generated-docs generated-portals`
  all passed on the final branch tree after the release cut.

## Results

- ADR 0306 is now implemented in repository version `0.177.119` and first
  verified live on platform version `0.130.75`; the integrated mainline
  baseline remains platform version `0.130.77`.
- The branch-local receipt remains the pre-integration audit trail for the live
  replay from the latest `origin/main` lineage, while the canonical mainline
  receipt records the `0.177.119` integration cut on top of latest
  `origin/main`, the earlier hosted private-main success boundary, and the
  detached exact-head verification bundle.
- No merge-to-main follow-up remains for ADR 0306 itself. The only residual
  caveat observed on 2026-03-31 is external to the ADR 0306 code path: exact
  detached `pre-push-gate` replays still depend on
  `registry.lv3.org/check-runner/infra:2026.03.23`, which returned transient
  `502 Bad Gateway` responses during both detached replays.
