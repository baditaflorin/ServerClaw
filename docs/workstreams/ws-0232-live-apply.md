# Workstream WS-0232: Nomad Live Apply

- ADR: [ADR 0232](../adr/0232-nomad-for-durable-batch-and-long-running-internal-jobs.md)
- Title: Live apply and end-to-end verification for the private Nomad scheduler
- Status: live_applied
- Implemented In Repo Version: 0.177.52
- Live Applied In Platform Version: 0.130.43
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0232-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0232-live-apply`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0179-service-redundancy-tier-matrix`, `adr-0184-failure-domain-labels-and-anti-affinity-policy`, `adr-0224-server-resident-operations-as-the-default-control-model`
- Conflicts With: none
- Shared Surfaces: `Makefile`, `docs/adr/0232-nomad-for-durable-batch-and-long-running-internal-jobs.md`, `docs/adr/.index.yaml`, `docs/runbooks/configure-nomad.md`, `docs/workstreams/ws-0232-live-apply.md`, `workstreams.yaml`, `playbooks/groups/automation.yml`, `playbooks/nomad.yml`, `playbooks/services/nomad.yml`, `collections/ansible_collections/lv3/platform/roles/nomad_cluster_member/`, `collections/ansible_collections/lv3/platform/roles/nomad_cluster_bootstrap/`, `collections/ansible_collections/lv3/platform/roles/proxmox_network/`, `config/nomad/jobs/`, `config/ansible-execution-scopes.yaml`, `config/ansible-role-idempotency.yml`, `config/command-catalog.json`, `config/service-capability-catalog.json`, `config/service-completeness.json`, `config/service-redundancy-catalog.json`, `config/health-probe-catalog.json`, `config/secret-catalog.json`, `config/controller-local-secrets.json`, `config/dependency-graph.json`, `config/workflow-catalog.json`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `tests/test_nomad_playbook.py`, `tests/test_nomad_cluster_roles.py`, `tests/test_generate_platform_vars.py`, `tests/test_proxmox_tailscale_proxy_role.py`, `receipts/live-applies/`

## Scope

- implement the repo-managed Nomad server, client, TLS, ACL, and smoke-job automation required by ADR 0232
- expose the private controller entrypoint for Nomad through the Proxmox host Tailscale TCP proxy catalog
- live-apply the scheduler from an isolated latest-`origin/main` worktree before carrying the protected integration files onto `main`
- verify both branch-local validation and the production automation path end to end
- record live evidence and leave the integrated repository in a merge-safe state

## Expected Repo Surfaces

- `playbooks/nomad.yml`
- `playbooks/groups/automation.yml`
- `playbooks/services/nomad.yml`
- `Makefile`
- `collections/ansible_collections/lv3/platform/roles/nomad_cluster_member/`
- `collections/ansible_collections/lv3/platform/roles/nomad_cluster_bootstrap/`
- `collections/ansible_collections/lv3/platform/roles/proxmox_network/`
- `config/nomad/jobs/lv3-nomad-smoke-service.nomad.hcl`
- `config/nomad/jobs/lv3-nomad-smoke-batch.nomad.hcl`
- `config/ansible-role-idempotency.yml`
- `config/command-catalog.json`
- `config/workflow-catalog.json`
- `docs/runbooks/configure-nomad.md`
- `docs/workstreams/ws-0232-live-apply.md`
- `docs/adr/0232-nomad-for-durable-batch-and-long-running-internal-jobs.md`
- `docs/adr/.index.yaml`
- `workstreams.yaml`
- `receipts/live-applies/2026-03-28-adr-0232-nomad-live-apply.json`
- `receipts/live-applies/2026-03-28-adr-0232-nomad-mainline-live-apply.json`

## Expected Live Surfaces

- `monitoring-lv3` runs the private Nomad server and mirrors the bootstrap management token
- `docker-runtime-lv3` and `docker-build-lv3` run Nomad clients with the Docker driver enabled
- the controller can reach the Nomad API at `https://100.64.0.1:8013`
- the repo-managed smoke service is running on `docker-build-lv3` and serves the expected verification page on `10.10.10.30:18180`
- the repo-managed smoke batch job can be dispatched on `docker-runtime-lv3` and writes its verification marker to `/var/lib/nomad/verification/lv3-nomad-smoke-batch/last-run.log`

## Verification

- `uv run --with pytest --with pyyaml pytest tests/test_nomad_playbook.py tests/test_nomad_cluster_roles.py tests/test_generate_platform_vars.py tests/test_proxmox_tailscale_proxy_role.py -q`
- `make syntax-check-nomad`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `./scripts/validate_repo.sh agent-standards`
- `./scripts/validate_repo.sh workstream-surfaces`
- `make immutable-guest-replacement-plan service=nomad`
- `make live-apply-service service=nomad env=production`
- `make live-apply-service service=nomad env=production ALLOW_IN_PLACE_MUTATION=true`
- controller-side `curl --cacert ... https://100.64.0.1:8013/v1/{status/leader,nodes}` through the Tailscale proxy plus guest-side smoke service and runtime marker checks on `monitoring-lv3`, `docker-build-lv3`, and `docker-runtime-lv3`

## Live Apply Outcome

- `make converge-nomad` completed successfully on `2026-03-28` with final recap `docker-build-lv3 ok=82 changed=5 failed=0`, `docker-runtime-lv3 ok=90 changed=1 failed=0`, `localhost ok=12 changed=0 failed=0`, `monitoring-lv3 ok=98 changed=6 failed=0`, and `proxmox_florin ok=50 changed=1 failed=0`
- the private controller entrypoint is live through `https://100.64.0.1:8013`; the proxy returned leader `"10.10.10.40:4647"` and `/v1/nodes` reported `docker-runtime-lv3 ready runtime` plus `docker-build-lv3 ready build`
- `lv3-nomad-smoke-service` remains `running` on `docker-build-lv3`, `curl -fsS http://10.10.10.30:18180/` returned `lv3 nomad smoke service`, and `lv3-nomad` is active on both clients
- the first durable batch verification completed successfully on `docker-runtime-lv3`, and `/var/lib/nomad/verification/lv3-nomad-smoke-batch/last-run.log` recorded `adr-0232-live-apply batch verification` plus timestamp `2026-03-28T20:06:51+00:00`
- the earlier live failures were resolved in repo code: `proxmox_network` is now part of the Nomad host play so the Proxmox VM firewall carries the Nomad RPC contract, the client wrapper now uses each node's advertised address for TLS, the smoke service uses `provider = "nomad"`, and batch verification now uses a durable runtime marker instead of ephemeral allocation logs
- the rebased latest-`origin/main` integration worktree proved the immutable guest replacement guard before mutation: `make live-apply-service service=nomad env=production` passed canonical-truth, interface-contract, capacity, and redundancy preflights, then failed closed because `nomad -> monitoring-lv3` is governed by ADR 0191 immutable guest replacement
- the documented narrow exception path succeeded from the integrated worktree: `make live-apply-service service=nomad env=production ALLOW_IN_PLACE_MUTATION=true` completed successfully with final recap `docker-build-lv3 ok=82 changed=5 failed=0`, `docker-runtime-lv3 ok=92 changed=3 failed=0`, `localhost ok=12 changed=0 failed=0`, `monitoring-lv3 ok=98 changed=2 failed=0`, and `proxmox_florin ok=52 changed=7 failed=0`
- post-replay direct verification on the integrated worktree re-confirmed leader `"10.10.10.40:4647"`, nodes `docker-runtime-lv3 ready runtime` and `docker-build-lv3 ready build`, the smoke service deployment as `successful`, and the durable batch marker timestamp `2026-03-28T21:07:33+00:00` on `docker-runtime-lv3`

## Mainline Integration Outcome

- merged to `main` in repository version `0.177.52`
- updated `VERSION`, `changelog.md`, `README.md`, `versions/stack.yaml`, `RELEASE.md`, `docs/release-notes/0.177.52.md`, and `docs/release-notes/README.md` during the final mainline integration step
- advanced the canonical platform version to `0.130.43` after the verified rebased latest-`origin/main` Nomad replay and promoted `2026-03-28-adr-0232-nomad-mainline-live-apply` into `versions/stack.yaml.live_apply_evidence.latest_receipts.nomad_scheduler`
- kept the earlier branch-local receipt as historical evidence for the first isolated-worktree replay while treating the mainline-equivalent receipt as the canonical source for release and platform truth

## Live Evidence

- branch-local receipt: `receipts/live-applies/2026-03-28-adr-0232-nomad-live-apply.json`
- canonical mainline receipt: `receipts/live-applies/2026-03-28-adr-0232-nomad-mainline-live-apply.json`
- controller-local Nomad trust root: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/nomad/tls/nomad-agent-ca.pem`
- controller-local management token: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/nomad/tokens/bootstrap-management.token`

## Merge-To-Main Notes

- remaining for merge to `main`: none

## Notes For The Next Assistant

- if the Nomad clients stop rejoining after an otherwise-idempotent replay, confirm both the guest nftables policy and the Proxmox per-VM firewall files still allow client-to-server RPC on `4647`
- the smoke service is verified through the build node's advertised address rather than loopback, and the batch proof now comes from the durable runtime marker file rather than `nomad alloc logs`
