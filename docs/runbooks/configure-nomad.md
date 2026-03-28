# Configure Nomad

## Purpose

This runbook converges the private Nomad scheduler defined by ADR 0232 for
durable batch jobs and long-running internal services.

It covers:

- controller-local TLS and ACL bootstrap artifacts under `.local/nomad/`
- a single private Nomad server on `monitoring-lv3`
- Nomad clients on `docker-runtime-lv3` and `docker-build-lv3`
- a Proxmox-host Tailscale TCP proxy for private controller access
- repo-managed smoke jobs that verify both long-running service placement and
  dispatchable batch execution

## Preconditions

Before running the workflow, confirm:

1. the controller has the SSH key at `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519`
2. `monitoring-lv3`, `docker-runtime-lv3`, and `docker-build-lv3` are reachable through the Proxmox jump path
3. the Proxmox host is reachable on its Tailscale address `100.64.0.1`
4. the local workstation can write controller-local bootstrap artifacts under `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/nomad/`

## Entrypoints

- syntax check: `make syntax-check-nomad`
- direct converge: `make converge-nomad`
- guarded live apply: `make live-apply-service service=nomad env=production`

## Delivered Surfaces

The workflow manages these live surfaces:

- Nomad server on `monitoring-lv3` listening on private ports `4646`, `4647`, and `4648`
- Nomad clients on `docker-runtime-lv3` and `docker-build-lv3` with the Docker driver enabled
- controller access to the Nomad API at `https://100.64.0.1:8013`
- mirrored bootstrap management token at `/etc/lv3/nomad/bootstrap-management.token` on `monitoring-lv3`
- repo-managed smoke job specs under `/etc/lv3/nomad/jobs/`
- long-running smoke service job `lv3-nomad-smoke-service`
- dispatchable smoke batch job `lv3-nomad-smoke-batch`

## Generated Local Artifacts

After a successful converge, these controller-local files should exist:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/nomad/tls/nomad-agent-ca.pem`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/nomad/tls/server.pem`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/nomad/tls/server-key.pem`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/nomad/tls/client.pem`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/nomad/tls/client-key.pem`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/nomad/tokens/bootstrap-management.token`

## Verification

Run these checks after converge:

1. `make syntax-check-nomad`
2. `make live-apply-service service=nomad env=production`
3. `NOMAD_ADDR=https://100.64.0.1:8013 NOMAD_CACERT=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/nomad/tls/nomad-agent-ca.pem NOMAD_TOKEN="$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/nomad/tokens/bootstrap-management.token)" nomad node status`
4. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.40 'sudo systemctl status lv3-nomad --no-pager && sudo /usr/local/bin/lv3-nomad job status lv3-nomad-smoke-service'`
5. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.30 'curl -fsS http://127.0.0.1:18180/'`

## Notes

- Nomad remains private-only in this rollout. There is no public DNS record or public edge publication for the scheduler.
- The `lv3-nomad` systemd unit intentionally runs as `root` so the agent can read the root-owned TLS key and use the Docker driver reliably on the client nodes.
- The controller-local bootstrap token is the branch-safe source of truth; if the local token is missing but the mirrored server token still exists, rerun the playbook to restore it automatically.
- The smoke service is pinned to the build client and the dispatchable batch smoke job is pinned to the runtime client so both client classes are exercised on every live apply.
