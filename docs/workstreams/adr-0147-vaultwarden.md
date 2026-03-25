# Workstream ADR 0147: Vaultwarden for Operator Credential Management

- ADR: [ADR 0147](../adr/0147-vaultwarden-for-operator-credential-management.md)
- Title: Private Vaultwarden for operator credentials, TOTP recovery material, and break-glass access notes
- Status: in_progress
- Branch: `codex/adr-0147-vaultwarden`
- Worktree: `.worktrees/adr-0147`
- Owner: codex
- Depends On: `adr-0026-postgres-vm`, `adr-0042-step-ca`, `adr-0067-guest-network-policy`
- Conflicts With: none
- Shared Surfaces: `roles/vaultwarden_runtime`, `roles/vaultwarden_postgres`, `playbooks/vaultwarden.yml`, `inventory/host_vars/proxmox_florin.yml`, `config/service-capability-catalog.json`

## Scope

- add repo-managed Vaultwarden runtime and PostgreSQL roles
- pin the Vaultwarden image in `config/image-catalog.json`
- publish `vault.lv3.org` as a tailnet-only operator entrypoint through the Proxmox host
- manage the private TLS certificate with `step-ca` and a renewal timer
- bootstrap the admin token and invite the named operator account
- document deployment, trust bootstrap, and first-login steps in `docs/runbooks/configure-vaultwarden.md`

## Non-Goals

- publishing Vaultwarden on the public edge
- replacing OpenBao as the source of truth for infrastructure secrets
- automating migration of every existing external credential into the vault in this same change

## Expected Repo Surfaces

- `roles/vaultwarden_runtime/`
- `roles/vaultwarden_postgres/`
- `playbooks/vaultwarden.yml`
- `playbooks/services/vaultwarden.yml`
- `docs/runbooks/configure-vaultwarden.md`
- `docs/adr/0147-vaultwarden-for-operator-credential-management.md`
- `docs/workstreams/adr-0147-vaultwarden.md`

## Expected Live Surfaces

- `https://vault.lv3.org/alive` returns success over Tailscale with the LV3 internal CA root
- `docker-runtime-lv3` runs the repo-managed Vaultwarden container from `/opt/vaultwarden/docker-compose.yml`
- `postgres-lv3` hosts the `vaultwarden` database and login role
- the Vaultwarden admin API reports the invited `ops@lv3.org` bootstrap user

## Verification

- Run `uv run --with pytest python -m pytest tests/test_vaultwarden_runtime_role.py -q`
- Run `make syntax-check-vaultwarden`
- Run `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- Run the runtime and admin bootstrap checks from `docs/runbooks/configure-vaultwarden.md`

## Merge Criteria

- the Vaultwarden runtime converges repeatably from the repo
- the private TLS certificate is issued and renewed from `step-ca`
- the operator-only Tailscale proxy is live and private-only
- the named operator invite path is present and verifiable without opening signups
