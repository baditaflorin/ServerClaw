# Workstream ADR 0141: API Token Lifecycle and Exposure Response

- ADR: [ADR 0141](../adr/0141-api-token-lifecycle-and-exposure-response.md)
- Title: governed token TTL policy, weekly inventory audit, revocation hooks, and exposure-response receipts
- Status: merged
- Branch: `codex/adr-0141-token-lifecycle`
- Worktree: `.worktrees/adr-0141`
- Owner: codex
- Depends On: `adr-0043-openbao`, `adr-0044-windmill`, `adr-0056-keycloak`, `adr-0065-secret-rotation`, `adr-0090-platform-cli`, `adr-0115-mutation-ledger`
- Conflicts With: none
- Shared Surfaces: `config/token-policy.yaml`, `config/token-inventory.yaml`, `scripts/token_lifecycle.py`, `config/windmill/scripts/`, `scripts/lv3_cli.py`, `docs/runbooks/`

## Scope

- add `config/token-policy.yaml` as the canonical lifecycle contract for governed token classes
- add `config/token-inventory.yaml` as the repo-managed inventory of token instances that must be audited
- write `scripts/token_lifecycle.py` with validation, audit, rotation, and exposure-response subcommands
- add Windmill wrappers for `audit-token-inventory` and `token-exposure-response`
- add runbooks for routine audit and incident response
- extend `lv3` so locally stored platform tokens warn when expiry is near and support explicit token-file lifecycle commands
- add focused regression coverage for audit findings, hook-backed revocation or rotation, and CLI expiry warnings

## Non-Goals

- implementing direct provider-native API adapters for every token system in the first iteration
- claiming that every live token on the platform is already hooked to an executable revocation command
- replacing ADR 0065 secret rotation for non-token secrets

## Expected Repo Surfaces

- `config/token-policy.yaml`
- `config/token-inventory.yaml`
- `scripts/token_lifecycle.py`
- `config/windmill/scripts/audit-token-inventory.py`
- `config/windmill/scripts/token-exposure-response.py`
- `docs/runbooks/token-lifecycle-management.md`
- `docs/runbooks/token-exposure-response.md`
- `scripts/lv3_cli.py`
- `tests/test_token_lifecycle.py`
- `tests/test_lv3_cli.py`

## Expected Live Surfaces

- the weekly `audit-token-inventory` workflow can run from the Windmill worker checkout and write receipts
- tokens that define executable hooks can be rotated or revoked without ad hoc shell work
- `lv3` warns when the locally stored platform token is expired or within its 24-hour renewal window

## Verification

- `uv run --with pyyaml python scripts/token_lifecycle.py validate`
- `uv run --with pyyaml python scripts/token_lifecycle.py audit --dry-run --print-report-json`
- `uv run --with pytest --with pyyaml pytest -q tests/test_token_lifecycle.py tests/test_lv3_cli.py`
- `uv run --with pyyaml python scripts/validate_repository_data_models.py --validate`

## Merge Criteria

- token policy and inventory validate through the shared repository data-model gate
- the audit path produces a receipt and correctly classifies healthy, warning, and expired tokens
- exposure response writes an incident receipt and blocks when required revocation hooks are missing
- the CLI token lifecycle commands can store, report, and warn on local token expiry metadata

## Outcome

- repository implementation is complete on `main` in repo release `0.122.0`
- the repo now ships the canonical token policy and inventory, the audit and exposure-response engine, Windmill wrappers, and CLI token-expiry enforcement
- platform version remains unchanged until executable provider hooks are applied from `main` and validated live
