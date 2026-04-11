# Configure Keycloak

## Purpose

This runbook converges the shared Keycloak SSO broker defined by ADR 0056.

It covers:

- PostgreSQL database and role provisioning on `postgres`
- Keycloak runtime deployment on `runtime-control`
- public DNS and edge publication at `https://sso.example.com`
- repo-managed realm, groups, initial named operator account, and confidential clients
- a repo-managed confidential client for delegated ServerClaw runtime verification
- repo-managed post-logout redirect URI contracts for `ops-portal-oauth`, `grafana-oauth`, and `outline`
- repo-managed realm SMTP settings for password resets and required-action mail through `lv3-mail-stalwart:1587` on the shared mail Docker network, with STARTTLS disabled
- Grafana OIDC configuration against the shared Keycloak broker
- controller-local recovery and client-secret artifacts mirrored under `.local/keycloak/`

## Preconditions

Before running the workflow, confirm:

1. the controller has the SSH key at `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519`
2. `postgres`, `runtime-control`, `monitoring`, and `nginx-edge` are reachable through the Proxmox jump path
3. `HETZNER_DNS_API_TOKEN` is available in the shell that runs the converge

## Entrypoints

- syntax check: `make syntax-check-keycloak`
- preflight: `make preflight WORKFLOW=converge-keycloak`
- converge: `HETZNER_DNS_API_TOKEN=... make converge-keycloak`

## Delivered Surfaces

The workflow manages these live surfaces:

- PostgreSQL database `keycloak` on `postgres`
- PostgreSQL login role `keycloak` on `postgres`
- Keycloak runtime under `/opt/keycloak` on `runtime-control`
- shared SSO hostname `https://sso.example.com`
- repo-managed realm `lv3`
- internal Keycloak mail submission endpoint `lv3-mail-stalwart:1587` on the shared mail Docker network
- named operator account `florin.badita`
- confidential OIDC client `grafana-oauth`
- confidential OIDC client `open-webui`
- shared logout authority return paths rooted at `https://ops.example.com/.well-known/lv3/session/`
- confidential agent client `lv3-agent-hub`
- confidential delegated-auth runtime client `serverclaw-runtime`
- Grafana generic OAuth redirect path at `https://grafana.example.com/login/generic_oauth`

## Generated Local Artifacts

After a successful converge, these controller-local files should exist:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/keycloak/database-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/keycloak/bootstrap-admin-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/keycloak/florin.badita-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/keycloak/grafana-client-secret.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/keycloak/open-webui-client-secret.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/keycloak/lv3-agent-hub-client-secret.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/keycloak/serverclaw-runtime-client-secret.txt`

Treat the entire `.local/keycloak/` subtree as recovery material and keep it out of git.

## Verification

Run these checks after converge:

1. `make syntax-check-keycloak`
2. `ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/hosts.yml runtime-control -m shell -a 'docker compose --file /opt/keycloak/docker-compose.yml ps && sudo ls -l /opt/keycloak/openbao /run/lv3-secrets/keycloak && sudo test ! -e /opt/keycloak/keycloak.env' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
3. `curl -s https://sso.example.com/realms/lv3/.well-known/openid-configuration`
4. `curl -I https://grafana.example.com/login/generic_oauth`
5. `curl -s --data "grant_type=client_credentials&client_id=lv3-agent-hub&client_secret=$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/keycloak/lv3-agent-hub-client-secret.txt)" https://sso.example.com/realms/lv3/protocol/openid-connect/token`
6. `ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/hosts.yml runtime-control -m shell -a "docker exec keycloak-keycloak-1 getent ahostsv4 lv3-mail-stalwart && docker exec keycloak-keycloak-1 /bin/bash -lc 'timeout 15 bash -lc \"exec 3<>/dev/tcp/lv3-mail-stalwart/1587\"'" --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
7. `uv run --with playwright python /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/session_logout_verify.py --password-file /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/keycloak/outline.automation-password.txt`
8. `curl -s --data "grant_type=client_credentials&client_id=serverclaw-runtime&client_secret=$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/keycloak/serverclaw-runtime-client-secret.txt)" https://sso.example.com/realms/lv3/protocol/openid-connect/token`

## TOTP Recovery

If an operator can enter the correct password but Keycloak rejects the one-time code with `Invalid authenticator code`, first verify the authenticator device clock is set automatically and synced to network time.

If the failure persists, remove the stored Keycloak OTP credential and require fresh enrollment on next login:

```bash
uvx --from pyyaml python /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/operator_manager.py \
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
uvx --from pyyaml python /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/operator_manager.py \
  reset-password \
  --id florin-badita \
  --password 'REPLACE_WITH_NEW_PASSWORD' \
  --temporary
```

The password recovery action:

- updates the live Keycloak password for that user
- clears the Keycloak brute-force failure counters for that user
- adds `UPDATE_PASSWORD` to the user's required actions when `--temporary` is used

## Bootstrap Admin Recovery

If the master-realm bootstrap admin can no longer obtain a token but the live
Keycloak container is healthy, use the runtime-local Keycloak recovery path on
`runtime-control` before changing any downstream client configuration.

The validated recovery sequence from the 2026-04-03 Open WebUI rollout was:

1. create a temporary emergency admin client with Keycloak's supported `kc.sh bootstrap-admin service` flow inside the live container
2. use that temporary client only long enough to restore or verify the repo-managed `lv3-bootstrap-admin` password held on the runtime at `/etc/lv3/keycloak/bootstrap-admin-password`
3. verify the restored bootstrap admin directly against the runtime-local listener at `http://127.0.0.1:18080/realms/master/protocol/openid-connect/token`
4. delete the temporary emergency client immediately after the bootstrap admin works again
5. resync `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/keycloak/bootstrap-admin-password.txt` from `/etc/lv3/keycloak/bootstrap-admin-password` before replaying workflows that reconcile downstream Keycloak clients, including `make converge-open-webui`

## Notes

- Keycloak is the shared SSO broker. It does not replace OpenBao for secrets or `step-ca` for SSH and internal TLS.
- Grafana is the first repo-managed consumer of the shared OIDC flow in this rollout. Future app integrations should reuse the same realm and identity taxonomy instead of creating app-local password stores.
- The shared browser-session logout contract depends on the edge publication and app-local consumers being current as well as Keycloak. After changing post-logout redirect URIs here, replay `make configure-edge-publication` and any affected service playbooks before relying on end-to-end logout verification.
- The shared edge and Grafana flows now complete Keycloak logout without an interactive confirmation page because the shared proxy logout path can provide `id_token_hint`. Outline is the current declared gap: its app-local logout reaches the Keycloak confirmation page and then returns through `https://ops.example.com/.well-known/lv3/session/proxy-logout`. Treat that confirmation page as expected current behavior until Outline can provide an `id_token_hint`.
- The Keycloak master bootstrap admin remains a break-glass recovery identity and should not become a routine human login.
- After the runtime-control live apply completes, the repo-managed Keycloak runtime and its controller-local mirrors are expected on `runtime-control`. If downstream client reconciliation fails after a Keycloak recovery, check the controller-local bootstrap password mirror first instead of hand-creating replacement client secrets.
- The named operator account is created with a bootstrap password and a required `CONFIGURE_TOTP` action so MFA enrollment happens on first successful interactive login.
- Because the named operator remains MFA-first, the Keycloak converge does not
  verify a repo-managed direct-grant token for that human identity.
- If this workflow is temporarily redirected at a shared runtime host such as
  legacy `docker-runtime` during migration recovery, the Keycloak role now
  fails closed before a host-wide Docker restart. Treat
  `common.docker_daemon_restart` failures as a maintenance-window decision or a
  runtime-pool migration gap, not as a signal to keep retrying the same replay.
- Password resets and required-action mail use `lv3-mail-stalwart:1587` over the shared `mail-platform_default` Docker network. This avoids Docker host-port hairpin failures and avoids STARTTLS certificate mismatch on the internal container DNS name.
- As of the 2026-03-29 ADR 0270 live apply, the repo-managed user reconciliation
  path now force-recreates the Keycloak service and retries once when the local
  admin API fails with transient `500`, JDBC acquisition timeout, or
  connection-style outage signatures. If the replay still fails after that one
  recycle, treat it as a real Keycloak or PostgreSQL incident rather than a
  publication blip.
