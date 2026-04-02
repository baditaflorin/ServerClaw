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
- `make preflight WORKFLOW=operator-onboard` passes.
- Optional but recommended:
  - `TAILSCALE_API_KEY` and `TAILSCALE_TAILNET`
  - `LV3_TAILSCALE_INVITE_ENDPOINT`
  - `LV3_STEP_CA_SSH_REGISTER_COMMAND`
  - `LV3_MATTERMOST_WEBHOOK`
- `viewer` operators do not receive SSH access and therefore do not need an SSH public key; `admin` and `operator` still do.
- `make converge-windmill` now mirrors the ADR 0108 operator-manager bootstrap secrets and optional environment values into the Windmill worker runtime so the browser-first path can use the same live credentials and optional hooks as the controller path without a worker-local `.local/` checkout.
- Controller-local live runs should override `LV3_OPENBAO_URL` to a forwarded loopback automation endpoint such as `http://127.0.0.1:18201`; the shared service catalog still points OpenBao at the private mTLS listener on `https://100.64.0.1:8200`, while `operator_manager.py` uses the non-mTLS automation listener on `127.0.0.1:8201`.

## Canonical Live Surface

Prefer the Windmill worker path for real onboarding:

```bash
WINDMILL_TOKEN="$(tr -d '\n' < /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" \
python3 scripts/windmill_run_wait_result.py \
  --base-url http://100.64.0.1:8005 \
  --workspace lv3 \
  --path f/lv3/operator_onboard \
  --payload-json '{
    "name": "Alice Example",
    "email": "alice@example.com",
    "role": "operator",
    "ssh_key": "'"$(cat /tmp/alice.pub)"'",
    "operator_id": "alice-example",
    "keycloak_username": "alice.example"
  }'
```

That route runs on `docker-runtime-lv3` and already exposes `LV3_OPENBAO_URL=http://lv3-openbao:8201`
inside the worker runtime, so it avoids the controller-side mTLS trap automatically.

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

## Browser-First Path

The same governed backend is also available through the Windmill admin app documented in [windmill-operator-access-admin.md](windmill-operator-access-admin.md).

Use that app when you need a non-terminal path from a new workstation. It calls the same ADR 0108 wrappers and does not create a second provisioning path.

The app now includes a `Guided Onboarding` launcher:

- the first-run Shepherd tour starts automatically on a fresh browser session
- `Onboard Admin Or Operator` and `Onboard Viewer` give role-specific walkthroughs
- dismissed tours can be resumed from the same launcher without restarting the page

Provisioning access is no longer the end of the browser-first onboarding path.
After the Windmill-backed identity step succeeds, direct the operator to
`https://ops.lv3.org#activation` so they complete the ADR 0310 first-run
activation checklist before they use advanced launcher destinations or live
mutating controls.

## Post-Provisioning Activation

Once the operator exists in Keycloak and the governed backend has returned the
bootstrap credentials:

1. have the operator sign in through the protected portal path at `ops.lv3.org`
2. review the **First-Run Activation** panel at `#activation`
3. complete the linked onboarding and portal-orientation checklist items
4. use the runbook launcher's validation-gate status path as the safe first task
5. only reveal advanced tools for the session when a supervised early bypass is
   actually required

## Controller-Local Fallback

If you need the controller-side script path, forward the guest-host OpenBao automation listener first:

```bash
ssh -f -N \
  -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ExitOnForwardFailure=yes \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p' \
  -L 18201:127.0.0.1:8201 \
  ops@10.10.10.20
```

Then run the controller script against that loopback URL:

```bash
LV3_OPENBAO_URL=http://127.0.0.1:18201 \
python3 scripts/operator_manager.py onboard \
  --name "Alice Example" \
  --email "alice@example.com" \
  --role operator \
  --ssh-key @/tmp/alice.pub \
  --emit-json
```

For direct guest-host fallback without Windmill, use the same explicit `ProxyCommand` form and run
the script on `ops@10.10.10.20` with `LV3_OPENBAO_URL=http://127.0.0.1:8201`.

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

When the controller-side OpenBao or Windmill path is unavailable and you only need the
Keycloak direct-API fallback from ADR 0317, use:

```bash
python3 scripts/provision_operator.py \
  --id matei-busui-tmp-001 \
  --name "Matei Busui" \
  --email busui.matei1994@gmail.com \
  --username matei.busui-tmp \
  --role admin \
  --expires 2026-04-08T00:00:00Z \
  --requester florin@badita.org
```

Notes:

- `scripts/provision_operator.py` now resolves `.local/` from the shared repo root, so it is safe
  to run from a dedicated git worktree under `.worktrees/`.
- Use `--skip-email` when re-verifying an existing account from exact `main`; this preserves the
  direct-API provisioning and assignment checks without sending duplicate onboarding mail.

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

- `make preflight WORKFLOW=operator-onboard`
- `python3 scripts/operator_manager.py validate`
- `python3 scripts/operator_access_inventory.py --id <operator-id>`
- `make workflow-info WORKFLOW=operator-onboard`
- `make workflow-info WORKFLOW=sync-operators`
- `curl -fsS https://sso.lv3.org/realms/lv3/.well-known/openid-configuration >/dev/null`
- `curl -fsS http://100.64.0.1:8005/api/version`
- `curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" http://100.64.0.1:8005/api/w/lv3/schedules/list | jq '.[] | select(.path=="f/lv3/quarterly_access_review_every_monday_0900")'`

## Notes

- The current implementation keeps bootstrap passwords out of git and returns them only in the command result.
- Tailscale invite creation is intentionally endpoint-configurable because the invite endpoint has shifted across API revisions.
- step-ca registration and revocation use explicit command templates so the repo can stay authoritative without hard-coding one deployment-specific wrapper.
- As of ADR 0206, product-specific integration code for the controller and Windmill operator-access path lives under `platform/operator_access/`, while `scripts/operator_manager.py` remains the composition root and orchestration layer.
