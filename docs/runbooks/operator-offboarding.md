# Operator Offboarding

This runbook documents the repo-managed offboarding path introduced by ADR 0108.

## Offboard One Operator

```bash
lv3 operator remove --id alice-example
```

Direct script path:

```bash
python3 scripts/operator_manager.py offboard --id alice-example --emit-json
```

The offboarding flow:

1. marks the operator inactive in `config/operators.yaml`
2. disables the Keycloak user instead of deleting it
3. upserts the OpenBao entity in a disabled state
4. optionally invokes the configured step-ca revocation hook
5. removes matching Tailscale devices when API credentials are configured
6. posts a completion message to Mattermost when a webhook is configured
7. emits a mutation-audit event and updates `.local/state/operator-access/<id>.json`

## Quarterly Review

Build the quarterly review report:

```bash
python3 scripts/operator_manager.py quarterly-review --emit-json
```

Windmill wrapper:

```bash
python3 config/windmill/scripts/quarterly-access-review.py
```

The report flags operators with no recorded activity for 45 days and marks operators stale at 60 days.

## Verification

- `python3 scripts/operator_access_inventory.py --id <operator-id> --offline`
- `make workflow-info WORKFLOW=operator-offboard`
- `make workflow-info WORKFLOW=quarterly-access-review`

## Failure Handling

- If Keycloak disable succeeds but OpenBao or Tailscale fails, rerun the same offboard command. The flow is idempotent.
- If Tailscale credentials are unavailable, remove the device manually in the admin console and record the action in the same incident thread or receipt.
- If emergency SSH revocation is required, configure `LV3_STEP_CA_SSH_REVOKE_COMMAND` to point at the approved revocation wrapper and rerun the offboard command.
