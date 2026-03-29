# Configure Keycloak

## Purpose

This runbook converges the shared Keycloak SSO broker defined by ADR 0056.

It covers:

- PostgreSQL database and role provisioning on `postgres-lv3`
- Keycloak runtime deployment on `docker-runtime-lv3`
- public DNS and edge publication at `https://sso.lv3.org`
- repo-managed realm, groups, initial named operator account, and confidential clients
- a repo-managed confidential client for delegated ServerClaw runtime verification
- repo-managed post-logout redirect URI contracts for `ops-portal-oauth`, `grafana-oauth`, and `outline`
- repo-managed realm SMTP settings for password resets and required-action mail through `lv3-mail-stalwart:1587` on the shared mail Docker network, with STARTTLS disabled
- Grafana OIDC configuration against the shared Keycloak broker
- controller-local recovery and client-secret artifacts mirrored under `.local/keycloak/`

## Preconditions

Before running the workflow, confirm:

1. the controller has the SSH key at `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519`
2. `postgres-lv3`, `docker-runtime-lv3`, `monitoring-lv3`, and `nginx-lv3` are reachable through the Proxmox jump path
3. `HETZNER_DNS_API_TOKEN` is available in the shell that runs the converge

## Entrypoints

- syntax check: `make syntax-check-keycloak`
- preflight: `make preflight WORKFLOW=converge-keycloak`
- converge: `HETZNER_DNS_API_TOKEN=... make converge-keycloak`

## Delivered Surfaces

The workflow manages these live surfaces:

- PostgreSQL database `keycloak` on `postgres-lv3`
- PostgreSQL login role `keycloak` on `postgres-lv3`
- Keycloak runtime under `/opt/keycloak` on `docker-runtime-lv3`
- shared SSO hostname `https://sso.lv3.org`
- repo-managed realm `lv3`
- internal Keycloak mail submission endpoint `lv3-mail-stalwart:1587` on the shared mail Docker network
- named operator account `florin.badita`
- confidential OIDC client `grafana-oauth`
- shared logout authority return paths rooted at `https://ops.lv3.org/.well-known/lv3/session/`
- confidential agent client `lv3-agent-hub`
- confidential delegated-auth runtime client `serverclaw-runtime`
- Grafana generic OAuth redirect path at `https://grafana.lv3.org/login/generic_oauth`

## Generated Local Artifacts

After a successful converge, these controller-local files should exist:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/keycloak/database-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/keycloak/bootstrap-admin-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/keycloak/florin.badita-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/keycloak/grafana-client-secret.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/keycloak/lv3-agent-hub-client-secret.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/keycloak/serverclaw-runtime-client-secret.txt`

Treat the entire `.local/keycloak/` subtree as recovery material and keep it out of git.

## Verification

Run these checks after converge:

1. `make syntax-check-keycloak`
2. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'docker compose --file /opt/keycloak/docker-compose.yml ps && sudo ls -l /opt/keycloak/openbao /run/lv3-secrets/keycloak && sudo test ! -e /opt/keycloak/keycloak.env'`
3. `curl -s https://sso.lv3.org/realms/lv3/.well-known/openid-configuration`
4. `curl -I https://grafana.lv3.org/login/generic_oauth`
5. `curl -s --data "grant_type=client_credentials&client_id=lv3-agent-hub&client_secret=$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/keycloak/lv3-agent-hub-client-secret.txt)" https://sso.lv3.org/realms/lv3/protocol/openid-connect/token`
6. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'docker exec keycloak-keycloak-1 getent ahostsv4 lv3-mail-stalwart && docker exec keycloak-keycloak-1 /bin/bash -lc '"'"'"'"'"'"'"'"'timeout 15 bash -lc "exec 3<>/dev/tcp/lv3-mail-stalwart/1587"'"'"'"'"'"'"'"'"''`
7. `uv run --with playwright python /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/session_logout_verify.py --password-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/keycloak/outline.automation-password.txt`
8. `curl -s --data "grant_type=client_credentials&client_id=serverclaw-runtime&client_secret=$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/keycloak/serverclaw-runtime-client-secret.txt)" https://sso.lv3.org/realms/lv3/protocol/openid-connect/token`

## TOTP Recovery

If an operator can enter the correct password but Keycloak rejects the one-time code with `Invalid authenticator code`, first verify the authenticator device clock is set automatically and synced to network time.

If the failure persists, remove the stored Keycloak OTP credential and require fresh enrollment on next login:

```bash
uvx --from pyyaml python /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/operator_manager.py \
  recover-totp \
  --id florin-badita
```

The recovery action:

- deletes the user's current Keycloak OTP credential(s)
- clears the Keycloak brute-force failure counters for that user
- adds `CONFIGURE_TOTP` back to the user's required actions

After the command succeeds, sign in again with the existing password and complete TOTP enrollment with a newly scanned QR code.

## Password Recovery

If the locally mirrored bootstrap password no longer matches the live account, set a new known password and optionally force rotation at next login:

```bash
uvx --from pyyaml python /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/operator_manager.py \
  reset-password \
  --id florin-badita \
  --password 'REPLACE_WITH_NEW_PASSWORD' \
  --temporary
```

The password recovery action:

- updates the live Keycloak password for that user
- clears the Keycloak brute-force failure counters for that user
- adds `UPDATE_PASSWORD` to the user's required actions when `--temporary` is used

## Notes

- Keycloak is the shared SSO broker. It does not replace OpenBao for secrets or `step-ca` for SSH and internal TLS.
- Grafana is the first repo-managed consumer of the shared OIDC flow in this rollout. Future app integrations should reuse the same realm and identity taxonomy instead of creating app-local password stores.
- The shared browser-session logout contract depends on the edge publication and app-local consumers being current as well as Keycloak. After changing post-logout redirect URIs here, replay `make configure-edge-publication` and any affected service playbooks before relying on end-to-end logout verification.
- The shared edge and Grafana flows now complete Keycloak logout without an interactive confirmation page because the shared proxy logout path can provide `id_token_hint`. Outline is the current declared gap: its app-local logout reaches the Keycloak confirmation page and then returns through `https://ops.lv3.org/.well-known/lv3/session/proxy-logout`. Treat that confirmation page as expected current behavior until Outline can provide an `id_token_hint`.
- The Keycloak master bootstrap admin remains a break-glass recovery identity and should not become a routine human login.
- The named operator account is created with a bootstrap password and a required `CONFIGURE_TOTP` action so MFA enrollment happens on first successful interactive login.
- Because the named operator remains MFA-first, the Keycloak converge does not
  verify a repo-managed direct-grant token for that human identity.
- Password resets and required-action mail use `lv3-mail-stalwart:1587` over the shared `mail-platform_default` Docker network. This avoids Docker host-port hairpin failures and avoids STARTTLS certificate mismatch on the internal container DNS name.
