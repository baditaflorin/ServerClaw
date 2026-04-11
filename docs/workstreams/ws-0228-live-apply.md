# Workstream WS-0228: Windmill Default Operations Surface Live Apply

- ADR: [ADR 0228](../adr/0228-windmill-as-the-default-browser-and-api-operations-surface.md)
- Title: Make Windmill the default browser-first and API-first surface for repo-managed operations
- Status: live_applied
- Implemented In Repo Version: 0.177.70
- Live Applied In Platform Version: 0.130.48
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0228-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0228-live-apply`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0087-validation-gate`, `adr-0091-continuous-drift-detection`, `adr-0105-capacity-model`, `adr-0111-end-to-end-integration-test-suite`, `adr-0129-runbook-automation-executor`, `adr-0141-token-lifecycle-management`, `adr-0142-public-surface-security-scanning`
- Conflicts With: none
- Shared Surfaces: `collections/.../windmill_runtime/defaults/main.yml`, `collections/.../windmill_runtime/tasks/verify.yml`, `config/windmill/scripts/*.py`, `docs/runbooks/`, `docs/adr/0228-*.md`, `docs/adr/.index.yaml`, `tests/`, `workstreams.yaml`, `receipts/live-applies/`

## Scope

- seed every workflow-catalog Windmill wrapper into the `lv3` workspace so Windmill becomes the default browser and API operations surface for those governed tasks
- harden the remaining wrapper scripts that still assume controller-local import resolution or CLI-only output
- add a verification contract in the Windmill runtime role for the default operations surface
- document the default browser/API path and the representative live verification routes
- record workstream-local live-apply evidence without touching protected integration files unless this branch becomes the final mainline integration step

## Non-Goals

- publishing Windmill on the public edge
- enabling every possible schedule in one workstream
- redesigning the scheduler, command catalog, or API gateway contracts that already call into Windmill
- changing the protected release files before this branch explicitly becomes the final verified merge-to-main step

## Expected Repo Surfaces

- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/verify.yml`
- `config/windmill/scripts/nightly-integration-tests.py`
- `config/windmill/scripts/weekly-capacity-report.py`
- `config/windmill/scripts/collection-publish.py`
- `config/windmill/scripts/audit-token-inventory.py`
- `config/windmill/scripts/token-exposure-response.py`
- `docs/runbooks/windmill-default-operations-surface.md`
- `docs/runbooks/configure-windmill.md`
- `docs/runbooks/validation-gate.md`
- `docs/runbooks/drift-detection.md`
- `docs/runbooks/capacity-model.md`
- `docs/runbooks/integration-test-suite.md`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/adr/0228-windmill-as-the-default-browser-and-api-operations-surface.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/ws-0228-live-apply.md`
- `tests/test_ansible_collection_packaging.py`
- `tests/test_nightly_integration_tests.py`
- `tests/test_weekly_capacity_report_windmill.py`
- `tests/test_windmill_default_operations_surface.py`
- `tests/test_token_lifecycle_windmill.py`

## Expected Live Surfaces

- the private Windmill workspace `lv3` exposes the workflow-catalog wrappers as seeded scripts instead of leaving them repo-only
- operators and agents can discover those operations through Windmill script metadata and execute representative safe workflows through the standard API routes
- the Windmill runtime converge verifies the default operations surface metadata in addition to the base healthcheck and validation-gate status scripts

## Verification

- `uv run --with pytest --with pyyaml pytest tests/test_nightly_integration_tests.py tests/test_weekly_capacity_report_windmill.py tests/test_ansible_collection_packaging.py tests/test_windmill_default_operations_surface.py -q`
- `uv run --with pytest --with pyyaml pytest tests/test_nightly_integration_tests.py tests/test_weekly_capacity_report_windmill.py tests/test_ansible_collection_packaging.py tests/test_windmill_default_operations_surface.py tests/test_token_lifecycle_windmill.py -q`
- `python3 -m py_compile config/windmill/scripts/nightly-integration-tests.py config/windmill/scripts/weekly-capacity-report.py config/windmill/scripts/collection-publish.py config/windmill/scripts/audit-token-inventory.py config/windmill/scripts/token-exposure-response.py`
- `make syntax-check-windmill`
- `./scripts/validate_repo.sh agent-standards`
- `./scripts/validate_repo.sh data-models`
- `make converge-windmill`
- live verification:
  - `curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/windmill/superadmin-secret.txt)" http://100.64.0.1:8005/api/w/lv3/scripts/get/p/f%2Flv3%2Fweekly_capacity_report`
  - `WINDMILL_TOKEN="$(tr -d '\n' < /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/windmill/superadmin-secret.txt)" python3 scripts/windmill_run_wait_result.py --base-url http://100.64.0.1:8005 --workspace lv3 --path f/lv3/weekly_capacity_report --payload-json '{"no_live_metrics":true}'`
  - `WINDMILL_TOKEN="$(tr -d '\n' < /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/windmill/superadmin-secret.txt)" python3 scripts/windmill_run_wait_result.py --base-url http://100.64.0.1:8005 --workspace lv3 --path f/lv3/audit_token_inventory --payload-json '{"dry_run":true}'`
  - `WINDMILL_TOKEN="$(tr -d '\n' < /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/windmill/superadmin-secret.txt)" python3 scripts/windmill_run_wait_result.py --base-url http://100.64.0.1:8005 --workspace lv3 --path f/lv3/token_exposure_response --payload-json '{"token_id":"local-platform-cli","exposure_source":"validation-dry-run","notes":"ws-0228 live verification","dry_run":true}'`

## Merge Criteria

- replay `make converge-windmill` successfully from the latest `origin/main` base in the dedicated worktree
- prove the seeded default-operations metadata exists on the live Windmill API
- execute safe representative workflows through the standard Windmill API routes and record the evidence in-branch
- leave protected integration files untouched on this branch, while naming exactly what the final main merge must still update

## Live Apply Outcome

- the rebased workstream now sits on repo version context `0.177.48`, and the final branch-local live replay came from branch head `a3de885c577399408e7d485595806ea3d0531281` after rebasing onto `origin/main` commit `cc80b12d`
- the seeded default operations surface is complete on this branch: the earlier workflow-catalog completeness check found `34` wrapper-backed workflows and `0` missing seeded Windmill paths
- the first rebased replay and representative API checks surfaced three real worker/runtime gaps on the branch: `weekly_capacity_report` still needed a PyYAML fallback on the worker, token lifecycle receipts still failed when concurrent checkout churn left repo-backed paths read-only, and the worker checkout archive staging path needed to stop using a shared remote filename
- branch commits `8d9b6c10` and `a3de885c` repaired those gaps by switching the worker checkout staging paths to per-run tempfiles, keeping repo-backed token lifecycle paths writable, teaching `weekly_capacity_report` to fall back through `uv run --with pyyaml`, and making the token lifecycle Windmill wrappers self-heal their receipt and incident directories at runtime
- the final replay log at `.local/ws-0228/converge-windmill-token-wrapper.log` completed successfully with `docker-runtime ok=236 changed=43`, `postgres ok=63 changed=1`, and `proxmox-host ok=37 changed=7`, and it included both `Verify the Windmill default operations scripts are seeded` and `Assert the Windmill default operations scripts exist`
- the proxied Windmill API on `http://100.64.0.1:8005` returned `CE v1.662.0`, the seeded metadata GETs for `f/lv3/post_merge_gate` and `f/lv3/maintenance_window` succeeded, `f/lv3/weekly_capacity_report` succeeded with `metrics_source: disabled`, `f/lv3/audit_token_inventory` succeeded with `7` healthy tokens, and dry-run `f/lv3/token_exposure_response` succeeded for `local-platform-cli`
- the canonical branch-local evidence for this replay is receipt `2026-03-28-adr-0228-windmill-default-operations-surface-live-apply`
- the later latest-main merge replay on 2026-03-29 surfaced three additional runtime truths that now belong to the same ADR trail: the live CE v1.662.0 control plane no longer resolves the older path-based `jobs/run_wait_result/p/...` route reliably for these seeded scripts, the worker mirror needed one more prune pass for stale empty directories so `f/lv3/post_merge_gate` would stop only on the expected protected-file canonical-truth holdback, and the worker-local `generated-portals` fallback required Python `3.11`-compatible empty-state rendering in `scripts/generate_ops_portal.py`
- the full repo validation path was also exercised from this worktree with `make validate`; it progressed through syntax, lint, data-model, dependency, and status-document checks before stopping at the expected protected canonical-truth guard for stale `README.md`
- the first branch push attempt also surfaced one generated-surface dependency from the remote pre-push gate: `docs/diagrams/agent-coordination-map.excalidraw` needed regeneration after the `workstreams.yaml` updates, so the workstream now includes that generated coordination map in its declared surface

## Mainline Integration

- the exact-main integration branch finishes ADR 0228 as repository version `0.177.71` and platform version `0.130.49`
- commit `afb96649` is the canonical merged-main replay source for that result; it keeps the Windmill raw-app and worker-sync hardening from the earlier branch work and adds the Python `3.11` compatibility fix for `scripts/generate_ops_portal.py`
- replay `r25` completed successfully from that exact merged candidate, the worker-local validation subset passed directly on `docker-runtime`, and receipt `2026-03-29-adr-0228-windmill-default-operations-surface-mainline-live-apply` now records the integrated proof
- the live `post_merge_gate` result is now green on mainline, with the expected nuance that the primary Docker-runner path still degrades to the worker-local fallback because the worker receives `502 Bad Gateway` while pulling `registry.example.com/check-runner/*`

## Notes For The Next Assistant

- the isolated branch is complete; the canonical exact-main follow-up now lives in `ws-0228-main-merge` and receipt `2026-03-29-adr-0228-windmill-default-operations-surface-mainline-live-apply`
- `docs/runbooks/windmill-default-operations-surface.md` is the central place for the representative seeded-script and API routes; avoid copying the whole catalog into every feature-specific runbook
- maintenance-window execution should stay documented as present-but-constrained until the live NATS publish authorization gap in `docs/runbooks/maintenance-windows.md` is closed
- long-running unrelated Windmill playbooks were still visible on the controller during this workstream; the final token lifecycle wrapper hardening is intentionally defensive against those concurrent repo-checkout permission resets
- the exact-main receipt leaves one non-blocking follow-up for the next rotation cycle: `audit_token_inventory` reports `local-platform-cli` as `rotation_due_soon` because it expires on `2026-03-31T00:00:00Z`
