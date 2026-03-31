# Configure Atlas

## Purpose

This runbook covers the ADR 0304 Atlas schema-management surfaces used for:

- repository-side catalog validation
- pre-migration linting against ephemeral PostgreSQL
- live schema snapshot refresh for committed `config/atlas/*.hcl` baselines
- scheduled and on-demand drift detection against the production PostgreSQL databases

Atlas does not execute service migrations. It validates repo contracts and
observes the live PostgreSQL schemas that service-native migration runners have
already applied.

## Entrypoints

- validate: `make atlas-validate`
- lint: `make atlas-lint`
- refresh snapshots: `make atlas-refresh-snapshots`
- drift check: `make atlas-drift-check`

Representative Windmill path after `make converge-windmill`:

```bash
python3 scripts/windmill_run_wait_result.py \
  --base-url http://100.64.0.1:8005 \
  --workspace lv3 \
  --path f/lv3/atlas_drift_check \
  --payload-json '{}'
```

## Preconditions

1. Docker is available on the controller so Atlas lint and schema-inspect runs
   can execute in the pinned Atlas container.
2. The controller-local OpenBao Atlas AppRole artifact exists at
   `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/openbao/atlas-approle.json`.
3. The controller-local NATS and ntfy secrets exist at:
   - `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/nats/jetstream-admin-password.txt`
   - `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ntfy/alertmanager-password.txt`
4. `docker-runtime-lv3`, `postgres-lv3`, and OpenBao are reachable through the
   Proxmox jump path used by the controller automation.
5. `make converge-openbao` has already seeded the Atlas AppRole and
   `make converge-windmill` has already seeded the `f/lv3/atlas_drift_check`
   script when the Windmill path is part of the verification.

## Managed Inputs And Outputs

Inputs:

- `config/atlas/catalog.json`
- repo migration directories listed in `config/atlas/catalog.json.lint_targets`
- controller-local OpenBao, NATS, and ntfy artifacts under `.local/`
- live PostgreSQL schemas reached through the declared guest topology

Outputs:

- committed schema snapshots under `config/atlas/*.hcl`
- drift receipts under `receipts/atlas-drift/`
- optional NATS notifications on `platform.db.schema_drift`
- optional ntfy alerts for drift findings

The seeded Windmill checkout also consumes repo-local runtime artifacts under
`.local/` when the job subprocess environment omits the equivalent secret
variables. That fallback keeps the governed `f/lv3/atlas_drift_check` path
usable from the isolated checkout without storing secrets in the repository.

## Verification

Run the repo-side path in this order:

1. `make atlas-validate`
2. `make atlas-lint`
3. `make atlas-refresh-snapshots`
4. `make atlas-validate`
5. `make atlas-drift-check`

Confirm drift receipts were written:

```bash
find receipts/atlas-drift -type f -name '*.json' | sort
```

Confirm the Atlas AppRole can mint the read-only schema-inspection credential:

```bash
role_id="$(jq -r '.role_id' /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/openbao/atlas-approle.json)"
secret_id="$(jq -r '.secret_id' /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/openbao/atlas-approle.json)"
token="$(curl -fsS --request POST --data "{\"role_id\":\"$role_id\",\"secret_id\":\"$secret_id\"}" http://127.0.0.1:8201/v1/auth/approle/login | jq -r '.auth.client_token')"
curl -fsS --header "X-Vault-Token: $token" http://127.0.0.1:8201/v1/database/creds/postgres-atlas-readonly
```

If Windmill owns the production verification, run the seeded script and confirm
the result references the same drift summary contract:

```bash
python3 scripts/windmill_run_wait_result.py \
  --base-url http://100.64.0.1:8005 \
  --workspace lv3 \
  --path f/lv3/atlas_drift_check \
  --payload-json '{}'
```

If `make converge-windmill` fails while syncing repo-managed raw apps with a
Windmill API connection error, check whether another concurrent playbook
cleanly stopped the Windmill stack between the earlier health check and the
`wmill sync push` helper. The managed role now restarts the minimal compose
subset (`openbao-agent`, `windmill_server`, `windmill_worker`,
`windmill_worker_native`) before retrying that sync step, so a rerun from the
same tree should recover once the shared hosts are quiet enough.

## Notes

- `make atlas-refresh-snapshots` is the only supported path for refreshing the
  committed `config/atlas/*.hcl` files. Do not hand-edit those HCL snapshots.
- If `make atlas-refresh-snapshots` or `make atlas-drift-check` fails with
  `HTTP Error 500` and the OpenBao response reports
  `"postgres-atlas-readonly" is not an allowed role`, rerun
  `make converge-openbao` from a tree that includes the ADR 0304 OpenBao
  backend allowed-role reconciliation task. The AppRole and policy can be
  present while the database backend config still lags the expected
  `allowed_roles` list.
- The current implementation pins the Atlas image by digest in
  `config/atlas/catalog.json`. If Harbor is not serving the mirror yet, record
  that temporary exception in the live-apply receipt instead of silently
  repointing the image.
- `make atlas-drift-check` is read-only against PostgreSQL. It should produce
  receipts and notifications, but it must not mutate database schema state.
- The seeded Windmill wrapper prefers the runtime environment when
  `LV3_ATLAS_OPENBAO_APPROLE_JSON` and
  `LV3_NTFY_ALERTMANAGER_PASSWORD` are present, but it will fall back to
  `.local/openbao/atlas-approle.json` and
  `.local/ntfy/alertmanager-password.txt` inside the isolated checkout when the
  worker subprocess drops those values.
