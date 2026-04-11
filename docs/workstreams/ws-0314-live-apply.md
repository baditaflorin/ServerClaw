# Workstream ws-0314-live-apply: ADR 0314 Live Apply From Latest `origin/main`

- ADR: [ADR 0314](../adr/0314-resumable-multi-step-flows-and-return-to-task-reentry.md)
- Title: implement resumable multi-step flows and return-to-task reentry on the live operator surfaces
- Status: live_applied
- Mainline Receipt: `receipts/live-applies/2026-04-04-adr-0314-resumable-multi-step-flows-and-return-to-task-reentry-mainline-live-apply.json`
- Branch: `codex/ws-0314-mainline-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0314-live-apply`
- Owner: codex
- Depends On: `adr-0093`, `adr-0129`, `adr-0209`, `adr-0234`
- Conflicts With: none

## Scope

- extend the shared runbook use-case service with durable task summaries and resume-aware metadata instead of keeping reentry semantics in browser memory
- expose resumable runbook tasks through the API gateway and the interactive ops portal, including home-surface return-to-task entry, deep links, activity context, and human-action resume
- live-apply the updated `api_gateway` and `ops_portal` services from this worktree and capture branch-local evidence that another agent can safely merge
- carry any runtime-control migration unblockers needed to complete the governed mainline live apply end to end, even when that requires narrow fixes in shared OpenBao, PostgreSQL, network, or mail-platform verification surfaces

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0314-live-apply.md`
- `docs/adr/0314-resumable-multi-step-flows-and-return-to-task-reentry.md`
- `docs/adr/.index.yaml`
- `docs/adr/index/**/*.yaml`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `versions/stack.yaml`
- `docs/release-notes/README.md`
- `docs/release-notes/*.md`
- `docs/status/history/live-apply-evidence.md`
- `docs/status/history/merged-workstreams.md`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/site-generated/architecture/dependency-graph.md`
- `build/platform-manifest.json`
- `scripts/topology-snapshot.json`
- `docs/runbooks/validation-gate-task-review.yaml`
- `docs/runbooks/runbook-automation-executor.md`
- `docs/runbooks/platform-operations-portal.md`
- `docs/runbooks/configure-runtime-ai-pool.md`
- `docs/runbooks/configure-runtime-control-pool.md`
- `docs/runbooks/configure-runtime-general-pool.md`
- `docs/runbooks/configure-keycloak.md`
- `docs/runbooks/identity-taxonomy-and-managed-principals.md`
- `inventory/host_vars/proxmox-host.yml`
- `inventory/group_vars/postgres_guests.yml`
- `playbooks/ops-portal.yml`
- `playbooks/openbao.yml`
- `playbooks/runtime-ai-pool.yml`
- `playbooks/runtime-control-pool.yml`
- `playbooks/runtime-general-pool.yml`
- `platform/use_cases/runbooks.py`
- `scripts/api_gateway/main.py`
- `scripts/ops_portal/app.py`
- `scripts/ops_portal/static/portal.css`
- `scripts/ops_portal/static/portal.js`
- `scripts/ops_portal/templates/base.html`
- `scripts/ops_portal/templates/index.html`
- `scripts/ops_portal/templates/partials/action_result.html`
- `scripts/ops_portal/templates/partials/runbooks.html`
- `scripts/ops_portal/templates/partials/tasks.html`
- `scripts/ops_portal/templates/task_detail.html`
- `collections/ansible_collections/lv3/platform/roles/mail_platform_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/meta/argument_specs.yml`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/tasks/open_webui_client.yml`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/tasks/reconcile_admin_client.yml`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/tasks/reconcile_repo_managed_users.yml`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/tasks/serverclaw_client.yml`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/tasks/sync_tree.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/docker_bridge_chains.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/docker_bridge_chains_reset_connection.yml`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/molecule/default/verify.yml`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/linux_guest_firewall/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/openbao_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/openbao_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`
- `collections/ansible_collections/lv3/platform/roles/postgres_vm/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/proxmox_network/tasks/main.yml`
- `tests/test_runbook_executor.py`
- `tests/test_runbook_use_cases.py`
- `tests/test_api_gateway.py`
- `tests/test_interactive_ops_portal.py`
- `tests/test_mail_platform_runtime_role.py`
- `tests/test_keycloak_runtime_role.py`
- `tests/test_openbao_playbook.py`
- `tests/test_openbao_runtime_role.py`
- `tests/test_api_gateway_runtime_role.py`
- `tests/test_common_docker_bridge_chains_helper.py`
- `tests/test_docker_runtime_role.py`
- `tests/test_ops_portal_playbook.py`
- `tests/test_ops_portal_runtime_role.py`
- `tests/test_linux_guest_firewall_role.py`
- `tests/test_postgres_vm_access_policy.py`
- `tests/test_postgres_vm_config.py`
- `tests/test_proxmox_network_role.py`
- `tests/test_runtime_ai_pool_playbook.py`
- `tests/test_runtime_control_pool_playbook.py`
- `tests/test_runtime_general_pool_playbook.py`
- `tests/test_step_ca_runtime_role.py`
- `receipts/ops-portal-snapshot.html`
- `receipts/restic-snapshots-latest.json`
- `receipts/restic-backups/*.json`
- `receipts/sbom/host-docker-runtime-*.cdx.json`
- `receipts/sbom/host-runtime-control-*.cdx.json`
- `receipts/live-applies/`
- `receipts/live-applies/evidence/`

## Expected Live Surfaces

- `http://127.0.0.1:8083/v1/platform/runbook-tasks*` (or equivalent task-aware runbook gateway routes) respond on `docker-runtime`
- `https://ops.example.com` exposes a return-to-task entry on the home surface and a deep-linkable resumable-task detail page
- escalated runbook executions preserve their resume summary and can be resumed through the live portal without re-entering draft data from scratch

## Verification Plan

- focused pytest for the runbook engine, API gateway, and interactive ops portal surfaces
- `./scripts/validate_repo.sh workstream-surfaces agent-standards`
- repo automation and service syntax checks for `api_gateway` and `ops_portal`
- governed branch-local live applies for `api_gateway` and `ops_portal` from this exact worktree
- controller-side and guest-local probes proving task listing, task detail, and task resume end to end

## Live Evidence

- Latest verified `origin/main` base before integration: `d44bdbfc6` (`VERSION` `0.178.4`, `platform_version` `0.130.98`)
- Final integrated truth on `main`: repo version `0.178.5`, platform version `0.130.99`
- Keycloak exact-main replay green:
  `receipts/live-applies/evidence/2026-04-04-ws-0314-mainline-keycloak-live-apply-r4.txt`
- API gateway exact-main replay green after the runtime-control Docker bridge-chain recovery fix:
  `receipts/live-applies/evidence/2026-04-04-ws-0314-mainline-api-gateway-live-apply-r11.txt`
- Ops portal exact-main replay green:
  `receipts/live-applies/evidence/2026-04-04-ws-0314-mainline-ops-portal-live-apply-r18.txt`
- Live portal task reentry proved end to end with the repo-managed `validation-gate-task-review` runbook:
  `receipts/live-applies/evidence/2026-04-04-ws-0314-mainline-task-reentry-portal-r1.txt`
  `receipts/live-applies/evidence/2026-04-04-ws-0314-mainline-task-reentry-resume-r2.txt`
  `receipts/live-applies/evidence/2026-04-04-ws-0314-mainline-task-reentry-portal-after-resume-r2.txt`
- Canonical structured mainline receipt:
  `receipts/live-applies/2026-04-04-adr-0314-resumable-multi-step-flows-and-return-to-task-reentry-mainline-live-apply.json`
- Targeted regression sweep green:
  `receipts/live-applies/evidence/2026-04-04-ws-0314-mainline-targeted-validation-pytest-r4.txt`
- Repo automation validation passes from the exact-main worktree:
  `receipts/live-applies/evidence/2026-04-04-ws-0314-mainline-validate-repo-r6.txt`
- Generated and receipt consistency checks green:
  `receipts/live-applies/evidence/2026-04-04-ws-0314-mainline-generated-checks-r2.txt`

## Notes

- this thread became the final verified merge-to-`main` step, so protected integration files were updated only after the exact-main replays and validation passed
- the live apply must prefer repo-managed automation and capture explicit receipts over undocumented ad hoc container restarts
- the exact-main publish closeout added the structured mainline receipt so `versions/stack.yaml` can point at a governed live-apply record rather than raw evidence filenames
