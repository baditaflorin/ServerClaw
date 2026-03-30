# Workstream WS-0262: OpenFGA And Keycloak Delegated Authorization Live Apply

- ADR: [ADR 0262](../adr/0262-openfga-and-keycloak-for-delegated-serverclaw-capability-authorization.md)
- Title: OpenFGA and Keycloak delegated authorization live apply
- Status: live_applied
- Implemented In Repo Version: 0.177.95
- Live Applied In Platform Version: 0.130.61
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0261-main-finish`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0261-main-finish`
- Owner: codex
- Depends On: `adr-0056-keycloak-for-operator-and-agent-sso`, `adr-0043-openbao-for-secrets-transit-and-dynamic-credentials`, `adr-0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3`
- Conflicts With: none
- Canonical Receipt: `receipts/live-applies/2026-03-30-adr-0262-openfga-keycloak-exact-main-live-apply.json`

## Purpose

Implement ADR 0262 by converging the private OpenFGA runtime and PostgreSQL
backend, extending Keycloak with the repo-managed ServerClaw runtime client,
seeding the delegated-authorization bootstrap store and tuples from repo JSON
contracts, and keeping the governed `/v1/openfga` route live behind the shared
API gateway.

## Replay Notes

- the exact-main replay started from `origin/main` commit
  `bbb0f66b8ec995dfa3ecdd7bac9156ed664157cc` with `VERSION` `0.177.92` and
  `platform_version` `0.130.61`
- the OpenFGA runtime remained pinned to internal port `8098` because the
  separate browser-runner runtime occupies `8096` on `docker-runtime-lv3`
- the final release cut and current protected release surfaces are recorded in
  repository version `0.177.95`, while the first platform version where ADR
  0262 became true remains `0.130.61`

## Verification

- `make converge-keycloak env=production` and
  `make converge-openfga env=production` both completed successfully from the
  synchronized replay tree before the shared API gateway follow-up converge
- `curl -fsS -H "Authorization: Bearer $(cat
  /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/openfga/preshared-key.txt)"
  http://100.64.0.1:8014/stores` returned the delegated authorization store
  `serverclaw-authz`
- `python3 scripts/serverclaw_authz.py verify --config
  config/serverclaw-authz/bootstrap.json --openfga-url http://100.64.0.1:8014
  --openfga-preshared-key-file
  /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/openfga/preshared-key.txt
  --keycloak-url http://10.10.10.20:8091` returned
  `verification_passed: true`
- the internal Keycloak client-credentials flow for `serverclaw-runtime`
  returned a bearer token from `http://10.10.10.20:8091`, and
  `https://api.lv3.org/v1/openfga/healthz` returned the expected protected
  `AUTH_INSUFFICIENT_ROLE` envelope for the `lv3-agent-hub` token

## Evidence

- `receipts/live-applies/2026-03-30-adr-0262-openfga-keycloak-exact-main-live-apply.json`
- `receipts/live-applies/evidence/2026-03-30-adr-0261-0262-release-0.177.95-converge-keycloak.txt`
- `receipts/live-applies/evidence/2026-03-30-adr-0261-0262-release-0.177.95-converge-openfga.txt`

## Outcome

- ADR 0262 is implemented in repository version `0.177.95`
- platform version `0.130.61` remains the first platform version where the
  delegated authorization decision became true
- the integrated current platform baseline advances separately during the
  mainline integration closeout tracked in
  [ws-0261-main-integration](./ws-0261-main-integration.md)
