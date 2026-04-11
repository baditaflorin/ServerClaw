# Workstream ADR 0056: Keycloak For Operator And Agent SSO

- ADR: [ADR 0056](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0056-keycloak-for-operator-and-agent-sso.md)
- Title: Shared SSO and identity broker for internal control-plane apps
- Status: live_applied
- Branch: `codex/adr-0056-keycloak-sso`
- Worktree: `../proxmox-host_server-keycloak-sso`
- Owner: codex
- Depends On: `adr-0046-identity-classes`, `adr-0047-short-lived-creds`, `adr-0049-private-api-publication`
- Conflicts With: none
- Shared Surfaces: internal app auth, operator sessions, agent clients, MFA policies

## Scope

- choose Keycloak as the shared SSO layer
- define initial app integrations and role boundaries
- align SSO policy with the platform identity taxonomy

## Non-Goals

- replacing OpenBao or `step-ca`
- removing local break-glass accounts from critical systems

## Expected Repo Surfaces

- `docs/adr/0056-keycloak-for-operator-and-agent-sso.md`
- `docs/workstreams/adr-0056-keycloak-sso.md`
- `docs/runbooks/configure-keycloak.md`
- `docs/runbooks/plan-visual-agent-operations.md`
- `docs/runbooks/identity-taxonomy-and-managed-principals.md`
- `playbooks/keycloak.yml`
- `roles/keycloak_postgres/`
- `roles/keycloak_runtime/`
- `roles/grafana_sso/`
- `config/controller-local-secrets.json`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `config/uptime-kuma/monitors.json`
- `workstreams.yaml`

## Expected Live Surfaces

- public Keycloak issuer at `https://sso.example.com`
- Keycloak realm `lv3` on `docker-runtime` with a PostgreSQL backend on `postgres`
- named operator `florin.badita` with required TOTP enrollment
- confidential clients `grafana-oauth` and `lv3-agent-hub`
- Grafana public login redirected through the shared Keycloak OIDC flow

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `make syntax-check-keycloak`
- `HETZNER_DNS_API_TOKEN=... make converge-keycloak`
- `dig +short @1.1.1.1 sso.example.com A`
- `curl -s https://sso.example.com/realms/lv3/.well-known/openid-configuration`
- `curl -I https://grafana.example.com/login/generic_oauth`
- `curl -s -X POST 'https://sso.example.com/realms/lv3/protocol/openid-connect/token' -H 'Content-Type: application/x-www-form-urlencoded' --data "grant_type=client_credentials&client_id=lv3-agent-hub&client_secret=$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/keycloak/lv3-agent-hub-client-secret.txt)"`

## Merge Criteria

- the ADR clearly separates SSO from secret issuance and SSH trust
- the repo-managed Keycloak converge path applies cleanly from `main`
- public issuer discovery, agent client credentials, and Grafana redirect behavior are verified live

## Notes For The Next Assistant

- keep local break-glass paths for Grafana and Keycloak recovery even as more apps move behind the shared broker
- treat Windmill, NetBox, Portainer, and Mattermost SSO as follow-on integrations instead of hand-edited Keycloak drift
