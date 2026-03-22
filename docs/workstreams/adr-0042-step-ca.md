# Workstream ADR 0042: step-ca For SSH And Internal TLS

- ADR: [ADR 0042](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0042-step-ca-for-ssh-and-internal-tls.md)
- Title: Internal certificate authority for SSH and private TLS
- Status: live_applied
- Branch: `codex/adr-0042-step-ca`
- Worktree: `../proxmox_florin_server-step-ca`
- Owner: codex
- Depends On: `adr-0014-tailscale`
- Conflicts With: none
- Shared Surfaces: `docker-runtime-lv3`, SSH trust, internal TLS

## Scope

- choose the internal CA app and trust model
- define SSH and X.509 boundaries for humans, agents, services, and hosts
- document the private-only publication and bootstrap expectations

## Non-Goals

- replacing the current public Let's Encrypt edge

## Expected Repo Surfaces

- `docs/adr/0042-step-ca-for-ssh-and-internal-tls.md`
- `docs/workstreams/adr-0042-step-ca.md`
- `docs/runbooks/configure-step-ca.md`
- `docs/runbooks/plan-agentic-control-plane.md`
- `playbooks/step-ca.yml`
- `roles/step_ca_runtime/`
- `roles/step_ca_ssh_trust/`
- `config/controller-local-secrets.json`
- `config/workflow-catalog.json`
- `workstreams.yaml`

## Expected Live Surfaces

- Compose-managed `step-ca` runtime on `docker-runtime-lv3`
- Tailscale-published CA API on `https://100.118.189.95:9443`
- controller-local trust bootstrap artifacts under `.local/step-ca/`
- CA-backed SSH host trust on the Proxmox host and managed guests
- verified human SSH certificate login through the host and guest jump path

## Verification

- `make syntax-check-step-ca`
- `make converge-step-ca`
- `curl --cacert /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/certs/root_ca.crt https://100.118.189.95:9443/health`
- local `step` CLI issuance plus SSH certificate login to `ops@100.118.189.95` and `ops@10.10.10.20`

## Merge Criteria

- the repo has a coherent `step-ca` converge path with documented bootstrap artifacts and trust boundaries
- the live CA runtime is healthy and reachable through the host Tailscale path
- SSH host trust and X.509 issuance are verified end to end
- a live-apply receipt is recorded before final push

## Notes For The Next Assistant

- Live apply completed on `2026-03-22` through `make converge-step-ca` from `main`.
- Verification confirmed `curl --cacert ... https://100.118.189.95:9443/health` returned `{\"status\":\"ok\"}` through the Proxmox host Tailscale proxy.
- Verification confirmed a locally issued `ops` SSH certificate reached both `ops@100.118.189.95` and `ops@10.10.10.20` using the mirrored CA trust material under `.local/step-ca/`.
- Verification confirmed local X.509 issuance through the proxied controller URL with the `services` provisioner.
