# Operator Onboarding

This runbook documents the repo-managed onboarding path introduced by ADR 0108.

## What This Controls

- `config/operators.yaml` is the authoritative roster for human operators.
- `scripts/operator_manager.py` applies that roster to Keycloak, OpenBao, step-ca, Tailscale, and Mattermost.
- Windmill wrappers live under `config/windmill/scripts/` so the same flow can run from the worker checkout after merge.

## Preconditions

- `config/operators.yaml` validates.
- `.local/keycloak/bootstrap-admin-password.txt` exists on the controller or Windmill worker.
- `.local/openbao/init.json` exists on the controller or Windmill worker.
- Optional but recommended:
  - `TAILSCALE_API_KEY` and `TAILSCALE_TAILNET`
  - `LV3_TAILSCALE_INVITE_ENDPOINT`
  - `LV3_STEP_CA_SSH_REGISTER_COMMAND`
  - `LV3_MATTERMOST_WEBHOOK`
- `viewer` operators do not receive SSH access and therefore do not need an SSH public key; `admin` and `operator` still do.

## Roster-First Flow

Add a new operator interactively through the governed CLI:

```bash
lv3 operator add \
  --name "Alice Example" \
  --email "alice@example.com" \
  --role operator \
  --ssh-key @/tmp/alice.pub
```

The workflow:

1. normalizes the operator record into `config/operators.yaml`
2. ensures the Keycloak realm roles and groups exist
3. upserts the Keycloak user and assigns the ADR 0108 realm role
4. upserts the OpenBao entity and the repo-managed operator policies
5. optionally calls the configured step-ca and Tailscale automation hooks
6. posts a welcome summary to Mattermost when a webhook is configured
7. emits a mutation-audit event and writes controller-local state under `.local/state/operator-access/`

## Direct Script Usage

Use the controller-side script when you need to run the logic without the CLI wrapper:

```bash
python3 scripts/operator_manager.py onboard \
  --name "Alice Example" \
  --email "alice@example.com" \
  --role operator \
  --ssh-key @/tmp/alice.pub \
  --emit-json
```

Dry-run support:

```bash
python3 scripts/operator_manager.py onboard \
  --name "Alice Example" \
  --email "alice@example.com" \
  --role operator \
  --ssh-key @/tmp/alice.pub \
  --dry-run \
  --emit-json
```

## Post-Merge Sync

When `config/operators.yaml` changes on `main`, the Windmill sync wrapper can reconcile the live systems from the merged roster:

```bash
python3 config/windmill/scripts/sync-operators.py
```

Or locally:

```bash
make sync-operators
```

## Verification

- `python3 scripts/operator_manager.py validate`
- `python3 scripts/operator_access_inventory.py --id <operator-id>`
- `make workflow-info WORKFLOW=operator-onboard`
- `make workflow-info WORKFLOW=sync-operators`

## Notes

- The current implementation keeps bootstrap passwords out of git and returns them only in the command result.
- Tailscale invite creation is intentionally endpoint-configurable because the invite endpoint has shifted across API revisions.
- step-ca registration and revocation use explicit command templates so the repo can stay authoritative without hard-coding one deployment-specific wrapper.
