# Configure Keycloak

## Purpose

This runbook converges the shared Keycloak SSO broker defined by ADR 0056.

It covers:

- PostgreSQL database and role provisioning on `postgres-lv3`
- Keycloak runtime deployment on `docker-runtime-lv3`
- public DNS and edge publication at `https://sso.lv3.org`
- repo-managed realm, groups, initial named operator account, and confidential clients
- repo-managed realm SMTP settings for password resets and required-action mail through the private mail relay on `10.10.10.20:1587`
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
- private Keycloak mail submission relay at `10.10.10.20:1587`
- named operator account `florin.badita`
- confidential OIDC client `grafana-oauth`
- confidential agent client `lv3-agent-hub`
- Grafana generic OAuth redirect path at `https://grafana.lv3.org/login/generic_oauth`

## Generated Local Artifacts

After a successful converge, these controller-local files should exist:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/keycloak/database-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/keycloak/bootstrap-admin-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/keycloak/florin.badita-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/keycloak/grafana-client-secret.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/keycloak/lv3-agent-hub-client-secret.txt`

Treat the entire `.local/keycloak/` subtree as recovery material and keep it out of git.

## Verification

Run these checks after converge:

1. `make syntax-check-keycloak`
2. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'docker compose --file /opt/keycloak/docker-compose.yml ps && sudo ls -l /opt/keycloak/openbao /run/lv3-secrets/keycloak && sudo test ! -e /opt/keycloak/keycloak.env'`
3. `curl -s https://sso.lv3.org/realms/lv3/.well-known/openid-configuration`
4. `curl -I https://grafana.lv3.org/login/generic_oauth`
5. `curl -s --data "grant_type=client_credentials&client_id=lv3-agent-hub&client_secret=$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/keycloak/lv3-agent-hub-client-secret.txt)" https://sso.lv3.org/realms/lv3/protocol/openid-connect/token`
6. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'python3 - <<'"'"'PY'"'"'\nimport smtplib\nfrom pathlib import Path\npassword = Path(\"/etc/lv3/mail-platform/server-mailbox-password\").read_text().strip()\nclient = smtplib.SMTP(\"10.10.10.20\", 1587, timeout=10)\nclient.ehlo()\nprint(client.login(\"server\", password))\nclient.quit()\nPY'`

## Notes

- Keycloak is the shared SSO broker. It does not replace OpenBao for secrets or `step-ca` for SSH and internal TLS.
- Grafana is the first repo-managed consumer of the shared OIDC flow in this rollout. Future app integrations should reuse the same realm and identity taxonomy instead of creating app-local password stores.
- The Keycloak master bootstrap admin remains a break-glass recovery identity and should not become a routine human login.
- The named operator account is created with a bootstrap password and a required `CONFIGURE_TOTP` action so MFA enrollment happens on first successful interactive login.
- Password resets and required-action mail deliberately use the VM-private Stalwart relay on port `1587` without STARTTLS so Keycloak does not depend on trusting the public submission certificate chain during browser recovery flows.
