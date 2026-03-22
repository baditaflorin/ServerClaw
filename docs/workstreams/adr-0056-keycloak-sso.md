# Workstream ADR 0056: Keycloak For Operator And Agent SSO

- ADR: [ADR 0056](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0056-keycloak-for-operator-and-agent-sso.md)
- Title: Shared SSO and identity broker for internal control-plane apps
- Status: ready
- Branch: `codex/adr-0056-keycloak-sso`
- Worktree: `../proxmox_florin_server-keycloak-sso`
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
- `docs/runbooks/plan-visual-agent-operations.md`
- `workstreams.yaml`

## Expected Live Surfaces

- private SSO for internal operator surfaces
- brokered identities for approved agent and service integrations

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0056-keycloak-for-operator-and-agent-sso.md`

## Merge Criteria

- the ADR clearly separates SSO from secret issuance and SSH trust
- app-integration targets and recovery boundaries are explicit

## Notes For The Next Assistant

- plan local recovery paths before routing every operator login through the IdP
