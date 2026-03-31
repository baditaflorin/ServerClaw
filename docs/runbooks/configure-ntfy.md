# Configure Ntfy

## Purpose

This runbook converges the private `ntfy` push gateway used by ADR 0097 for critical platform paging.

It delivers:

- a repo-managed `ntfy` container on `docker-runtime-lv3`
- basic-auth protection for the publish and subscribe topics used by
  Alertmanager and SBOM verification
- controller-local secret material mirrored under `.local/ntfy/`

## Entrypoints

- syntax check: `make syntax-check-ntfy`
- converge: `make converge-ntfy`

## Managed Artifacts

- runtime directory: `/opt/ntfy`
- server config: `/opt/ntfy/server.yml`
- data directory: `/var/lib/ntfy`
- controller-local secret: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ntfy/alertmanager-password.txt`

## Verification

1. `make syntax-check-ntfy`
2. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'docker compose --file /opt/ntfy/docker-compose.yml ps'`
3. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'curl -fsS http://127.0.0.1:2586/v1/health'`

## Authorized Topics

- `platform-alerts` is the production topic used by Alertmanager and the ADR 0298
  SBOM refresh workflow.
- `platform-alerts-sbom-verify` is a dedicated verification topic that uses the
  same `alertmanager` credential without publishing test traffic into the
  production paging stream.

## Notes

- The first iteration uses one repo-managed username and password for both Alertmanager publishing and operator subscription.
- Treat `.local/ntfy/` as secret material and keep it outside git.
