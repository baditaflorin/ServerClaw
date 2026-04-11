# Compose Runtime Secrets Injection

This runbook documents the repository contract introduced by ADR 0077 for Compose-managed runtimes that consume secrets through an OpenBao Agent sidecar instead of static `.env` files under `/opt/<service>/`.

## Model

Each migrated stack now uses:

- a host `tmpfs` runtime env path under `/run/lv3-secrets/<service>/runtime.env`
- an OpenBao Agent sidecar mounted from `/opt/<service>/openbao/`
- a per-service AppRole with read-only access to `kv/data/services/<service>/runtime-env`

The service role still renders the initial runtime env file during converge, but it is written under `/run`, not into the compose directory. The sidecar then refreshes that file from OpenBao on its polling interval.

## Host Surfaces

For a migrated service:

- agent config: `/opt/<service>/openbao/agent.hcl`
- agent template: `/opt/<service>/openbao/runtime.env.ctmpl`
- AppRole material: `/opt/<service>/openbao/role_id` and `/opt/<service>/openbao/secret_id`
- runtime env: `/run/lv3-secrets/<service>/runtime.env`

Legacy compose-directory env files such as `/opt/<service>/<service>.env` or `/opt/mail-platform/gateway/gateway.env` should be absent after converge.

## Verification

For any migrated stack:

1. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'docker compose --file /opt/<service>/docker-compose.yml ps'`
2. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'sudo ls -l /opt/<service>/openbao /run/lv3-secrets/<service>'`
3. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'sudo test ! -e /opt/<service>/<service>.env'`

For the mail platform gateway, replace the legacy file check with:

`ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'sudo test ! -e /opt/mail-platform/gateway/gateway.env'`

## Rotation Behavior

The OpenBao Agent refreshes the runtime env file from OpenBao automatically. Services that only read environment variables at process start still need a controlled container recreate to pick up changed values. The secret-rotation playbooks remain responsible for that restart step.
