# Workstream ADR 0108: Operator Onboarding and Off-boarding Workflow

- ADR: [ADR 0108](../adr/0108-operator-onboarding-and-offboarding.md)
- Title: Windmill-backed onboarding/offboarding across Keycloak, step-ca, OpenBao, and Tailscale with operators.yaml as the authoritative roster
- Status: ready
- Branch: `codex/adr-0108-operator-onboarding`
- Worktree: `../proxmox_florin_server-operator-onboarding`
- Owner: codex
- Depends On: `adr-0014-tailscale`, `adr-0042-step-ca`, `adr-0043-openbao`, `adr-0044-windmill`, `adr-0046-identity-classes`, `adr-0056-keycloak`, `adr-0066-audit-log`
- Conflicts With: none
- Shared Surfaces: `config/`, Windmill workflows, Keycloak realm configuration

## Scope

- write `config/operators.yaml` — initial state: one operator (the platform owner) documented with all access details
- write `scripts/operator_manager.py` — implements `create_keycloak_user()`, `register_ssh_principal()`, `create_openbao_entity()`, `create_tailscale_invite()`, and their off-boarding counterparts
- write `scripts/operator_access_inventory.py` — produces per-operator access inventory report
- write Windmill workflow `operator-onboard` — calls `operator_manager.py` functions in sequence; sends Mattermost welcome
- write Windmill workflow `operator-offboard` — calls revocation functions; posts completion to Mattermost
- write Windmill workflow `quarterly-access-review` — scheduled first Monday of each quarter; reports inactive operators
- write `config/schemas/operators.schema.json` — JSON schema for `config/operators.yaml`
- add `lv3 operator add` and `lv3 operator remove` commands to platform CLI
- add `lv3 operator inventory --id <operator-id>` command to platform CLI
- add OpenBao policies `platform-admin`, `platform-operator`, `platform-read` if not already defined (check existing `config/secret-catalog.json`)
- add `config/operators.yaml` to the validation gate schema check

## Non-Goals

- Multi-factor authentication management (MFA is configured by the operator themselves in Keycloak)
- Audit of historical access changes before this ADR (only forward from this ADR)
- Service account management (human operators only; service accounts are managed per-service)

## Expected Repo Surfaces

- `config/operators.yaml`
- `config/schemas/operators.schema.json`
- `scripts/operator_manager.py`
- `scripts/operator_access_inventory.py`
- `config/validation-gate.json` (patched: operators.yaml schema check)
- `docs/runbooks/operator-onboarding.md`
- `docs/runbooks/operator-offboarding.md`
- `docs/adr/0108-operator-onboarding-and-offboarding.md`
- `docs/workstreams/adr-0108-operator-onboarding.md`

## Expected Live Surfaces

- `config/operators.yaml` is committed and valid against the schema
- Windmill `operator-onboard` and `operator-offboard` workflows are visible in Windmill UI
- `quarterly-access-review` is scheduled in Windmill (first Monday of each quarter)
- `lv3 operator inventory` works for the existing platform owner operator

## Verification

- Run `lv3 operator inventory --id <owner-id>` → shows Keycloak status, SSH cert status, OpenBao entity, Tailscale device
- Test onboard: create a test operator with `lv3 operator add --name "Test Operator" --email "test@example.com" --role viewer --ssh-key @/tmp/test_key.pub`
- Verify Keycloak user is created; verify OpenBao entity exists; verify Mattermost welcome message sent
- Test offboard: `lv3 operator remove --id test-operator`; verify Keycloak user is disabled; verify OpenBao entity is revoked
- Verify audit log contains both events

## Merge Criteria

- `config/operators.yaml` committed with the platform owner documented
- Onboard workflow tested end-to-end with a test operator (created and deleted)
- Offboard workflow revokes all access (verified by checking Keycloak, OpenBao)
- `quarterly-access-review` workflow scheduled
- Runbooks for onboarding and offboarding written and deployed to docs site

## Notes For The Next Assistant

- Tailscale operator invitation via API requires the Tailscale API key stored in OpenBao at `platform/tailscale/api-key`; the Tailscale API endpoint for creating device invitations is `POST /api/v2/tailnet/<tailnet>/device-invites`; check the current Tailscale API docs as the endpoint may have changed
- OpenBao policies `platform-admin`, `platform-operator`, and `platform-read` must be created before the onboarding workflow runs; check `config/secret-catalog.json` or `roles/openbao_runtime/` for any existing policy definitions
- SSH certificate principal registration via step-ca: use `step ca ssh certificate <username> /tmp/<username>.pub --sign-only` from the build server; this does not issue a certificate but registers the principal as valid for future `step ssh login` calls
- `config/operators.yaml` should be a YAML file (not JSON) for readability; the schema validation gate must be updated to support YAML schema validation or the file converted to JSON
