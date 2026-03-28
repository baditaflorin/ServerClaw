# Windmill Operator Access Admin

## Purpose

This runbook documents the browser-first operator administration surface introduced by ADR 0122 and the guided in-app onboarding added for ADR 0242.

It wraps the existing ADR 0108 backend so operators can:

- list current operators
- onboard a new operator
- off-board an existing operator
- reconcile the live identity systems with `config/operators.yaml`
- inspect one operator's access inventory
- launch or resume task-specific guided tours for those workflows

## Location

- Windmill workspace: `lv3`
- Raw app path: `f/lv3/operator_access_admin`
- Windmill base URL: `http://100.118.189.95:8005`
- Direct app route: `http://100.118.189.95:8005/apps/get/p/f/lv3/operator_access_admin`

The app is private to the Windmill workspace. It is not published anonymously.

## Access

- login page: `http://100.118.189.95:8005/user/login`
- bootstrap email: `superadmin_secret@windmill.dev`
- bootstrap password source: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt`

The current platform path uses the managed Windmill bootstrap admin for browser access. That keeps the app reachable from a fresh machine without requiring a terminal-local cookie jar or manual API token injection.

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

## Guided Tours

The app now ships a Shepherd-powered `Guided Onboarding` launcher for:

- first-run orientation
- admin or operator onboarding
- viewer onboarding
- off-boarding
- inventory review

Tour behavior:

- the first-run walkthrough auto-starts on a fresh browser session
- every tour is safe to skip and can be resumed from the launcher after dismissal
- each step links back to the authoritative ADR 0108 runbooks instead of embedding an alternate policy source in the UI
- keyboard navigation, focus trapping, and `Esc` exit are handled by Shepherd

## New Operator Flow

1. Open Windmill and launch `f/lv3/operator_access_admin`.
2. Let the first-run tour start automatically, or choose `Onboard Admin Or Operator` or `Onboard Viewer` from `Guided Onboarding`.
3. Confirm the target role and complete the required form fields.
4. Submit the create action.
5. Record the returned bootstrap password securely.
6. Direct the new operator to sign in through Keycloak, rotate the bootstrap password, and complete TOTP enrollment.

## Off-boarding Flow

1. Open the same app.
2. Start `Off-board Operator` from `Guided Onboarding` if you want the step-by-step walkthrough.
3. Select the target operator from the roster.
4. Optionally record a reason.
5. Submit the off-board action.
6. Refresh the roster and, when needed, inspect the per-operator inventory result.

## Inventory Review

Use `Review Inventory` from `Guided Onboarding` when you want a focused verification pass after onboarding, reconciliation, or off-boarding.

The panel reads the current live state for the selected operator and is the fastest post-mutation confidence check in the app.

## Repo Validation

Run:

```bash
uv run --with pytest --with pyyaml python -m pytest tests/test_windmill_operator_admin_app.py -q
python3 -m py_compile config/windmill/scripts/operator-roster.py config/windmill/scripts/operator-inventory.py
npx --prefix config/windmill/apps/f/lv3/operator_access_admin.raw_app tsc --noEmit -p config/windmill/apps/f/lv3/operator_access_admin.raw_app/tsconfig.json
ANSIBLE_CONFIG=ansible.cfg ANSIBLE_COLLECTIONS_PATH=collections uvx --from ansible-core ansible-playbook -i inventory/hosts.yml playbooks/windmill.yml --syntax-check
```

## Notes

- The bootstrap password is intentionally shown once in the onboarding result and is not written to git.
- The app depends on the worker checkout being mounted at `/srv/proxmox_florin_server`; the Windmill runtime now bind-mounts that host checkout into both worker pools.
- The app is a Windmill-private admin surface; `ops.lv3.org` remains a separate portal.
