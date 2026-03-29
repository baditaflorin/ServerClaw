# Workstream WS-0232: Nomad Live Apply

- ADR: [ADR 0232](../adr/0232-nomad-for-durable-batch-and-long-running-internal-jobs.md)
- Title: Live apply and end-to-end verification for the private Nomad scheduler
- Status: live_applied
- Implemented In Repo Version: 0.177.65
- Live Applied In Platform Version: 0.130.44
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0232-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0232-live-apply`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0179-service-redundancy-tier-matrix`, `adr-0184-failure-domain-labels-and-anti-affinity-policy`, `adr-0224-server-resident-operations-as-the-default-control-model`
- Conflicts With: none

## Scope

- implement the repo-managed Nomad server, client, TLS, ACL, proxy, and smoke
  job automation required by ADR 0232
- expose the private controller entrypoint through the Proxmox Tailscale TCP
  proxy catalog and the Proxmox plus guest firewall contracts
- prove the immutable guest replacement guard blocks in-place mutation unless
  the ADR 0191 narrow exception is documented explicitly
- record both the first isolated-worktree live apply and the final exact-main
  replay evidence needed for safe merge-to-main

## Verification

- `uv run --with pytest --with pyyaml pytest tests/test_nomad_playbook.py tests/test_nomad_cluster_roles.py tests/test_generate_platform_vars.py tests/test_proxmox_tailscale_proxy_role.py -q`
- `make syntax-check-nomad`
- `make immutable-guest-replacement-plan service=nomad`
- `make live-apply-service service=nomad env=production`
- `make live-apply-service service=nomad env=production ALLOW_IN_PLACE_MUTATION=true`
- controller-side `curl --cacert ... https://100.64.0.1:8013/v1/{status/leader,nodes}`
- guest-side `systemctl is-active lv3-nomad`, smoke service verification on
  `docker-build-lv3`, and durable batch marker verification on
  `docker-runtime-lv3`

## Live Apply Outcome

- the first isolated-worktree replay on `2026-03-28` established the repo
  managed Nomad server, client, TLS, ACL, and smoke-job path and preserved its
  receipt as historical evidence in
  `receipts/live-applies/2026-03-28-adr-0232-nomad-live-apply.json`
- the final exact-main replay from the rebased `0.177.63` worktree first
  failed closed at the immutable guest replacement guard, then succeeded with
  `ALLOW_IN_PLACE_MUTATION=true` as the documented ADR 0191 narrow exception
- the final exact-main recap was `docker-build-lv3 ok=83 changed=5 failed=0`,
  `docker-runtime-lv3 ok=95 changed=5 failed=0`,
  `localhost ok=12 changed=0 failed=0`,
  `monitoring-lv3 ok=98 changed=2 failed=0`, and
  `proxmox_florin ok=51 changed=4 failed=0`
- post-replay verification re-confirmed leader `"10.10.10.40:4647"`, nodes
  `docker-runtime-lv3 ready runtime` and `docker-build-lv3 ready build`, the
  smoke service deployment as `successful`, and the durable batch marker
  timestamp `2026-03-29T02:19:07+00:00`

## Mainline Integration Outcome

- recorded in repository version `0.177.65`
- kept the platform baseline at `0.130.44` because the verified replay was
  performed from the current live `origin/main` base
- promoted canonical receipt
  `receipts/live-applies/2026-03-29-adr-0232-nomad-mainline-live-apply.json`
  into `versions/stack.yaml.live_apply_evidence.latest_receipts.nomad_scheduler`

## Live Evidence

- branch-local receipt:
  `receipts/live-applies/2026-03-28-adr-0232-nomad-live-apply.json`
- canonical mainline receipt:
  `receipts/live-applies/2026-03-29-adr-0232-nomad-mainline-live-apply.json`
- controller-local Nomad trust root:
  `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/nomad/tls/nomad-agent-ca.pem`
- controller-local management token:
  `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/nomad/tokens/bootstrap-management.token`

## Notes For The Next Assistant

- if the Nomad clients stop rejoining after an otherwise-idempotent replay,
  check both the guest nftables rules and the Proxmox per-VM firewall files for
  TCP `4647`
- the durable batch proof now comes from
  `/var/lib/nomad/verification/lv3-nomad-smoke-batch/last-run.log`, not from
  transient allocation logs
