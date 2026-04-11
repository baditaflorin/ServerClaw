# Workstream ADR 0047: Short-Lived Credentials And Internal mTLS

- ADR: [ADR 0047](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0047-short-lived-credentials-and-internal-mtls.md)
- Title: Credential lifetime and mTLS policy
- Status: live_applied
- Branch: `codex/adr-0047-short-lived-creds`
- Worktree: `../proxmox-host_server-short-lived-creds`
- Owner: codex
- Depends On: `adr-0042-step-ca`, `adr-0043-openbao`, `adr-0046-identity-classes`
- Conflicts With: none
- Shared Surfaces: SSH certificates, API tokens, internal HTTPS, service auth

## Scope

- define default credential lifetimes and issuer boundaries
- prefer short-lived machine and human credentials over static secrets
- define when internal mTLS should be required

## Non-Goals

- preserving long-lived static secrets as the default

## Expected Repo Surfaces

- `docs/adr/0047-short-lived-credentials-and-internal-mtls.md`
- `docs/workstreams/adr-0047-short-lived-creds.md`
- `docs/runbooks/configure-step-ca.md`
- `docs/runbooks/configure-openbao.md`
- `inventory/group_vars/all.yml`
- `inventory/host_vars/proxmox-host.yml`
- `playbooks/openbao.yml`
- `roles/openbao_runtime/`
- `workstreams.yaml`

## Expected Live Surfaces

- short-lived human SSH certificates accepted on the Proxmox host and managed guests
- short-lived OpenBao AppRole secret IDs refreshed during converge and post-verification
- mTLS on the OpenBao operator and service API at `https://100.118.189.95:8200`

## Verification

- `make converge-step-ca`
- `make converge-openbao`
- issue an eight-hour `ops` SSH certificate through `step-ca` and verify login to `ops@100.118.189.95` plus `ops@10.10.10.20`
- issue a one-hour X.509 client certificate through `step-ca` and verify `curl --cert ... --key ... --cacert ... https://100.118.189.95:8200/v1/sys/health`
- verify the same OpenBao request fails without a client certificate

## Merge Criteria

- the repo-managed control-plane components stop depending on long-lived default SSH or API credentials for routine verification
- the private OpenBao API requires mTLS for external access and rejects unauthenticated clients

## Live Apply Notes

- Live apply completed on `2026-03-22` from `main`.
- Controller-side verification proved short-lived `ops` SSH certificate login to both the Proxmox host and `docker-runtime`.
- Controller-side verification proved that OpenBao serves a `step-ca`-issued certificate over the Proxmox Tailscale path and rejects TLS requests that do not present a valid client certificate.
