# Windmill Operator Access Admin

## Purpose

This runbook documents the browser-first operator administration surface introduced by ADR 0122.

It wraps the existing ADR 0108 backend so operators can:

- list current operators
- onboard a new operator
- off-board an existing operator
- reconcile the live identity systems with `config/operators.yaml`
- inspect one operator's access inventory

## Location

- Windmill workspace: `lv3`
- Raw app path: `f/lv3/operator_access_admin`

The app is private to the Windmill workspace. It is not published anonymously.

## What The App Uses

The UI does not provision access directly. It calls repo-managed Windmill scripts that delegate to:

- `scripts/operator_manager.py`
- `scripts/operator_access_inventory.py`
- `config/operators.yaml`

That keeps the UI, CLI, and Make targets on the same governed backend path.

## Operator Workflows Backed By The App

- onboarding: `f/lv3/operator_onboard`
- off-boarding: `f/lv3/operator_offboard`
- roster sync: `f/lv3/sync_operators`
- inventory lookup: `f/lv3/operator_inventory`
- roster listing: `f/lv3/operator_roster`

## New Operator Flow

1. Open Windmill and launch `f/lv3/operator_access_admin`.
2. Fill in `name`, `email`, `role`, and `ssh key` when the role is `admin` or `operator`.
3. Submit the create action.
4. Record the returned bootstrap password securely.
5. Direct the new operator to sign in through Keycloak, rotate the bootstrap password, and complete TOTP enrollment.

## Off-boarding Flow

1. Open the same app.
2. Select the target operator from the roster.
3. Optionally record a reason.
4. Submit the off-board action.
5. Refresh the roster and, when needed, inspect the per-operator inventory result.

## Repo Validation

Run:

```bash
uv run --with pytest --with pyyaml python -m pytest tests/test_windmill_operator_admin_app.py -q
python3 -m py_compile config/windmill/scripts/operator-roster.py config/windmill/scripts/operator-inventory.py
ANSIBLE_CONFIG=ansible.cfg ANSIBLE_COLLECTIONS_PATH=collections uvx --from ansible-core ansible-playbook -i inventory/hosts.yml playbooks/windmill.yml --syntax-check
```

## Notes

- The bootstrap password is intentionally shown once in the onboarding result and is not written to git.
- The app depends on the worker checkout being mounted at `/srv/proxmox_florin_server`, the same assumption used by the existing ADR 0108 Windmill wrappers.
- The app is a Windmill-private admin surface; `ops.lv3.org` remains a separate portal.
