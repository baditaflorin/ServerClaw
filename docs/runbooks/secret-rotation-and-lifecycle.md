# Secret Rotation And Lifecycle

## Purpose

This runbook describes the repo-managed secret rotation contract introduced by ADR 0065.

The implementation keeps one canonical catalog in `config/secret-catalog.json`, with the general secret inventory in `secrets` and the ADR 0065 automation contract in `rotation_metadata` plus `rotation_contracts`. Live mutations run through `playbooks/secret-rotation.yml`, and OpenBao remains the authoritative KV store for dedicated rotatable secret paths plus their rotation metadata.

## Entry Points

Inspect the catalog:

```bash
python3 scripts/secret_rotation.py --list
```

Validate the catalog and unit tests:

```bash
python3 scripts/secret_rotation.py --validate
python3 -m unittest discover -s tests
```

Syntax-check the rotation playbook:

```bash
make syntax-check-secret-rotation
```

Plan one rotation without changing live state:

```bash
make rotate-secret SECRET_ID=windmill_database_password ROTATION_ARGS="--plan"
```

Apply one low-risk rotation:

```bash
make rotate-secret SECRET_ID=windmill_database_password ROTATION_ARGS="--apply"
```

Apply one high-risk rotation after the `rotate-secret-high-risk` approval path is satisfied:

```bash
make rotate-secret SECRET_ID=windmill_superadmin_secret ROTATION_ARGS="--apply --approve-high-risk"
```

## Catalog Model

Each entry in `config/secret-catalog.json` defines:

1. the owning service and secret type
2. the risk level and command contract to use
3. the rotation and warning windows
4. the controller-local source secret used for initial OpenBao seeding
5. the dedicated OpenBao KV path and metadata keys
6. the Ansible apply target that performs the live mutation without a full service reconverge

The committed `last_rotated` value is a repo contract default. Live executions should treat the OpenBao KV metadata keys as the operational source of truth once the workflow is applied from `main`.

## Live Preflight Checklist

Before any `--apply` run:

1. Run from the integrated checkout that contains the exact code you intend to apply, not from an older or partially merged worktree.
2. Confirm `make validate`, `make syntax-check-secret-rotation`, and `make rotate-secret SECRET_ID=windmill_database_password ROTATION_ARGS="--plan"` all pass from that checkout.
3. Confirm the controller-local prerequisites referenced by `config/controller-local-secrets.json` exist and are readable, especially the SSH key and the OpenBao init payload.
4. Confirm `make converge-openbao` and `make converge-windmill` have been applied successfully on the target platform revision so the dedicated OpenBao paths and the seeded Windmill script exist live.
5. Confirm the target service is healthy before rotation. For the first live apply, start with `windmill_database_password`, which is the lowest-risk candidate in this catalog.
6. Confirm rollback posture exists before touching high-risk credentials. At minimum, know how to re-run the same secret id with an explicit value and verify the owning service health.
7. Confirm whether the secret is low-risk or high-risk. High-risk entries require the `rotate-secret-high-risk` approval path and should not be mixed into exploratory first-live testing.

## Human And Agent Notes

- `playbooks/secret-rotation.yml` is expected to run from a separate worktree. It resolves the secret catalog and controller-local manifest relative to `playbook_dir`, then reads the actual OpenBao init payload path from the manifest.
- The playbook mutates the owning service first and OpenBao second. If a run fails after the service change, treat the platform as partially rotated and reconcile by rerunning the same secret deliberately instead of inventing an ad hoc rollback.
- The committed ADR status means the repo automation exists. It does not mean the live platform metadata is updated. Do not bump `Implemented In Platform Version` until an apply from `main` succeeds and is verified.
- Mail-platform compatibility mirrors still exist for grouped legacy paths. A successful mail secret rotation must leave both the dedicated secret path and the compatibility bundle consistent.
- The first live execution should stay narrow: one secret, one apply, immediate health verification, then receipt/status updates.

## Live Mutation Path

`make rotate-secret` calls `scripts/secret_rotation.py`, which:

1. validates the catalog and selected secret id
2. enforces the correct command contract for low-risk versus high-risk secrets
3. invokes `playbooks/secret-rotation.yml` in plan or apply mode
4. emits a structured `secret.rotation.completed` event payload on success when `SECRET_ROTATION_NATS_EVENT_URL` is configured
5. emits a GlitchTip-compatible error payload when `SECRET_ROTATION_GLITCHTIP_EVENT_URL` is configured and the apply fails

`playbooks/secret-rotation.yml` then:

1. resolves the selected secret contract on the controller
2. generates a fresh value when apply mode does not pass one explicitly
3. applies the live change through `tasks/rotate.yml` in the owning role
4. stores the rotated value in the dedicated OpenBao path
5. updates the OpenBao KV metadata fields for `lv3_last_rotated` and `lv3_last_rotated_by`
6. refreshes the legacy mail runtime compatibility bundle when the rotated secret still belongs to that grouped path

## Current Coverage

The initial catalog covers:

- `windmill_database_password`
- `windmill_superadmin_secret`
- mail platform core runtime credentials
- mail platform notification-profile mailbox passwords and scoped API keys

External third-party secrets that are not repo-generated yet, such as the Brevo API key, remain outside automated rotation until their provider-side rotation path is explicit and safe.

## OpenBao Seeding

`make converge-openbao` now seeds each cataloged secret into a dedicated OpenBao KV path under:

- `services/windmill/*`
- `services/mail-platform/*`

The role also writes path-level metadata for rotation period, warning window, risk level, approval mode, and command contract so future scheduled workflows can evaluate expiry without scraping repo files.

## Windmill Surface

`make converge-windmill` now seeds a repo-managed Windmill script at `f/lv3/rotate_credentials`.

That script summarizes the committed rotation contract and which secrets require an initial rotation. It is the intended seed surface for the later scheduled Windmill execution path once the secret-rotation AppRole is wired into the live runtime.

## Failure Guidance

- Stop immediately if the plan output does not match the intended secret id, risk level, or apply target.
- Stop if a high-risk secret would be applied without the `rotate-secret-high-risk` approval path.
- Stop if the owning service health check fails after the role-local `rotate.yml` task finishes.
- If apply mode fails after mutating a service but before updating OpenBao, treat the service as partially rotated and rerun the same secret id deliberately instead of inventing ad hoc rollback steps.
