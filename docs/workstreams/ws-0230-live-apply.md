# Workstream WS-0230: Policy Decisions Via Open Policy Agent And Conftest Live Apply

- ADR: [ADR 0230](../adr/0230-policy-decisions-via-open-policy-agent-and-conftest.md)
- Title: Live apply shared OPA and Conftest policy decisions across command approval, promotion gating, and validation automation
- Status: live_applied
- Implemented In Repo Version: 0.177.49
- Live Applied In Platform Version: 0.130.42
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0230-live-apply-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0230-live-apply-r2`
- Owner: codex
- Depends On: `adr-0048-command-catalog`, `adr-0073-promotion-pipeline`, `adr-0087-repository-validation-gate`, `adr-0211-shared-policy-packs-and-rule-registries`, `adr-0224-server-resident-operations-as-the-default-control-model`
- Conflicts With: none
- Shared Surfaces: `policy/**`, `platform/policy/**`, `scripts/policy_checks.py`, `scripts/policy_toolchain.py`, `scripts/command_catalog.py`, `scripts/promotion_pipeline.py`, `config/build-server.json`, `config/check-runner-manifest.json`, `config/validation-gate.json`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/`, `docs/runbooks/command-catalog-and-approval-gates.md`, `docs/runbooks/environment-promotion-pipeline.md`, `docs/runbooks/validation-gate.md`, `docs/runbooks/configure-windmill.md`, `docs/adr/0230-policy-decisions-via-open-policy-agent-and-conftest.md`, `docs/adr/.index.yaml`, `receipts/live-applies/2026-03-28-adr-0230-policy-decisions-live-apply.json`, `workstreams.yaml`

## Scope

- move command approval and promotion eligibility decisions into shared Rego evaluated through one OPA or Conftest toolchain
- wire the shared policy engine into the controller validation gate, build-server remote validation, and Windmill worker gate-status path
- ensure the Windmill worker mirror carries the policy bundle and policy helpers from a non-primary git worktree without macOS metadata drift
- replay the live Windmill converge from the rebased latest-`origin/main` worktree and verify the worker-side policy surfaces directly on `docker-runtime`
- complete the protected integration files only during the final merge-to-main step

## Expected Repo Surfaces

- `policy/conftest/repository.rego`
- `policy/decisions/command_approval.rego`
- `policy/decisions/release_promotion.rego`
- `policy/tests/command_approval_test.rego`
- `policy/tests/release_promotion_test.rego`
- `platform/policy/engine.py`
- `platform/policy/toolchain.py`
- `scripts/policy_checks.py`
- `scripts/policy_toolchain.py`
- `scripts/command_catalog.py`
- `scripts/parallel_check.py`
- `scripts/promotion_pipeline.py`
- `config/build-server.json`
- `config/check-runner-manifest.json`
- `config/validation-gate.json`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- `docs/runbooks/command-catalog-and-approval-gates.md`
- `docs/runbooks/environment-promotion-pipeline.md`
- `docs/runbooks/validation-gate.md`
- `docs/runbooks/configure-windmill.md`
- `docs/adr/0230-policy-decisions-via-open-policy-agent-and-conftest.md`
- `docs/workstreams/ws-0230-live-apply.md`
- `docs/adr/.index.yaml`
- `receipts/live-applies/2026-03-28-adr-0230-policy-decisions-live-apply.json`
- `workstreams.yaml`

## Expected Live Surfaces

- `/srv/proxmox-host_server/policy` on `docker-runtime` carries the rebased ADR 0230 policy bundle with no `._*` or `.DS_Store` metadata files
- worker-local approval and gate-status wrappers on `docker-runtime` evaluate the same policy bundle as the controller checkout
- the governed promotion gate path rejects from shared policy reasons instead of duplicating command and release logic in separate caller-specific code

## Verification

- `python3 scripts/policy_checks.py --validate`
- `make syntax-check-windmill`
- `uv run --with pytest --with pyyaml pytest -q tests/test_windmill_operator_admin_app.py tests/test_policy_checks.py tests/test_command_catalog.py tests/test_promotion_pipeline.py tests/test_parallel_check.py tests/test_validation_gate.py tests/test_validation_gate_windmill.py`
- `make converge-windmill`
- `ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml docker-runtime -m shell -a 'cd /srv/proxmox-host_server && python3 scripts/policy_checks.py --validate' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
- `ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml docker-runtime -m shell -a 'cd /srv/proxmox-host_server && python3 scripts/command_catalog.py --check-approval --command converge-windmill --requester-class human_operator --approver-classes human_operator --validation-passed --preflight-passed --receipt-planned && python3 config/windmill/scripts/gate-status.py --repo-path /srv/proxmox-host_server' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
- `PROMOTION_PROMETHEUS_URL=http://127.0.0.1:9 uv run --with pyyaml python3 scripts/promotion_pipeline.py --check-gate --service grafana --staging-receipt receipts/live-applies/staging/2026-03-27-adr-0183-staging-live-apply.json`

## Live Apply Outcome

- `make converge-windmill` completed successfully from the rebased latest-`origin/main` worktree with final recap `docker-runtime ok=229 changed=38 failed=0`, `postgres ok=63 changed=1 failed=0`, and `proxmox-host ok=36 changed=4 failed=0`
- direct worker verification confirmed `ADR 0230 policy checks OK: /srv/proxmox-host_server/policy` and no macOS metadata files under `/srv/proxmox-host_server/policy`
- the worker-local approval and gate-status replay returned `Command approval OK: converge-windmill` and showed `policy-validation` among the enabled validation-gate checks on `docker-runtime`
- a deterministic promotion-gate probe using `PROMOTION_PROMETHEUS_URL=http://127.0.0.1:9` rejected through the shared OPA path for concrete policy reasons: the staging receipt was older than 24 hours, projected vCPU commitment exceeded target, and the SLO gate could not evaluate because Prometheus was unreachable

## Mainline Integration Outcome

- merged to `main` in repository version `0.177.49`
- updated `VERSION`, `changelog.md`, `RELEASE.md`, versioned release notes, `versions/stack.yaml`, `README.md`, and `build/platform-manifest.json` only during the final mainline integration step
- preserved the current platform version `0.130.42` because the verified live replay already ran from the rebased latest-`origin/main` worktree and this workstream did not perform a second literal-`main` replay after merge

## Live Evidence

- live-apply receipt: `receipts/live-applies/2026-03-28-adr-0230-policy-decisions-live-apply.json`
- worker checkout path: `/srv/proxmox-host_server`
- worker gate-status manifest: `/srv/proxmox-host_server/config/validation-gate.json`

## Merge-To-Main Notes

- remaining for merge to `main`: none
