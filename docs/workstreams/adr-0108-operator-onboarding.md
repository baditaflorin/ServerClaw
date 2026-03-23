# Workstream ADR 0108: Operator Onboarding and Off-boarding Workflow

- ADR: [ADR 0108](../adr/0108-operator-onboarding-and-offboarding.md)
- Title: Windmill-backed onboarding/offboarding across Keycloak, step-ca, OpenBao, and Tailscale with operators.yaml as the authoritative roster
- Status: merged
- Branch: `codex/adr-0108-operator-onboarding`
- Worktree: `.worktrees/adr-0108`
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

## Delivered

- added the repo-authoritative operator roster at `config/operators.yaml` plus the schema under `config/schemas/operators.schema.json`
- added repo-managed OpenBao policy sources for `platform-admin`, `platform-operator`, and `platform-read`
- added `scripts/operator_manager.py` and `scripts/operator_access_inventory.py` for onboarding, offboarding, sync, inventory, and quarterly access reviews
- added Windmill wrappers plus Make targets for `operator-onboard`, `operator-offboard`, `sync-operators`, and `quarterly-access-review`
- added `lv3 operator add`, `lv3 operator remove`, and `lv3 operator inventory`
- wired the validation gate and repository data-model checks to validate the operator roster
- documented the onboarding and offboarding procedures in dedicated runbooks and updated ADR 0108 implementation metadata for release `0.97.0`

## Notes For The Next Assistant

- The repository-side implementation is complete on `main`, but the live Windmill worker still needs deployment-local environment variables for the Tailscale invite endpoint and optional step-ca registration/revocation hooks.
- `sync-operators` is the mainline reconciliation entrypoint when `config/operators.yaml` changes after merge.
- The current inventory report can query Keycloak, OpenBao, and Tailscale directly; step-ca inventory remains controller-state-driven because the live deployment does not expose a stable certificate-inventory API in repo automation today.
