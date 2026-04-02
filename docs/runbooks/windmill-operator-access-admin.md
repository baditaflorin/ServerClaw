# Windmill Operator Access Admin

## Purpose

This runbook documents the browser-first operator administration surface introduced by ADR 0122, the data-dense AG Grid roster from ADR 0238, the bounded rich-notes editing from ADR 0241, the guided in-app onboarding added for ADR 0242, the ADR 0311 global command palette now powered by `cmdk`, and the privacy-preserving journey analytics and onboarding scorecards added for ADR 0316.

It wraps the existing ADR 0108 backend so operators can:

- list current operators
- onboard a new operator through a schema-first form
- off-board an existing operator through a schema-first form
- reconcile the live identity systems with `config/operators.yaml` through a schema-first form
- inspect one operator's access inventory
- edit bounded rich operator notes through the ADR 0241 Tiptap surface while still storing markdown in `config/operators.yaml`
- launch or resume task-specific guided tours for those workflows
- surface live onboarding success scorecards, alert handoff feedback, and contextual help recovery affordances without creating a second mutation path

The roster uses **AG Grid Community** for the data-dense operator view, so operators can sort, filter, page, pin or resize columns, and move through the selection with the keyboard instead of relying on a hand-built HTML table.

The forms use `react-hook-form` plus `zod`, so one authoritative schema now controls defaults, local validation, touched-state feedback, and submit behavior for onboarding, off-boarding, and reconciliation.

## Location

- Windmill workspace: `lv3`
- Raw app path: `f/lv3/operator_access_admin`
- Windmill base URL: `http://100.64.0.1:8005`
- Direct app route: `http://100.64.0.1:8005/apps/get/p/f/lv3/operator_access_admin`

The app is private to the Windmill workspace. It is not published anonymously.

## Access

- login page: `http://100.64.0.1:8005/user/login`
- bootstrap email: `superadmin_secret@windmill.dev`
- bootstrap password source: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt`

The current platform path uses the managed Windmill bootstrap admin for browser access. That keeps the app reachable from a fresh machine without requiring a terminal-local cookie jar or manual API token injection.

## What The App Uses

The UI does not provision access directly. It calls repo-managed Windmill scripts that delegate to:

- `scripts/operator_manager.py`
- `scripts/operator_access_inventory.py`
- `config/operators.yaml`

That keeps the UI, CLI, and Make targets on the same governed backend path.

The shared frontend form contracts live in:

- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/schemas.ts`

## Rich Notes Workflow

The `Rich Notes` panel is the first bounded ADR 0241 editing surface.

- the left pane is a Tiptap editor with headings, lists, task items, code blocks, links, tables, and person mentions inserted as `@operator-id`
- the right pane is the canonical markdown source so operators can paste markdown in, inspect what will be stored, or copy it back out
- the `Save Notes` action calls `f/lv3/operator_update_notes`, which delegates to `scripts/operator_manager.py update-notes`
- the worker persists the resulting markdown back into `config/operators.yaml` and records `audit.last_reviewed_at` plus `audit.last_reviewed_by`

This is intentionally bounded knowledge editing, not a replacement for the larger Outline knowledge system at `wiki.lv3.org`.

## Runtime Feedback Model

The browser app now uses TanStack Query for server-state and mutation feedback:

- roster query key: `["operator-roster"]`
- inventory query key: `["operator-inventory", "<operator_id>"]`
- roster background refresh cadence: every `60` seconds
- inventory background refresh cadence: every `45` seconds while an operator is selected
- onboarding, off-boarding, roster reconciliation, and rich-notes persistence invalidate the affected query keys instead of forcing a full-page reload

Operators should expect explicit `Loading`, `Refreshing`, `Stale`, `Fresh`, and `Error` state pills in both the roster and inventory panels, plus a structured mutation result panel that records the last action outcome.

## Canonical Page-State Guidance

ADR 0315 now standardizes this page on one explicit state inventory with
next-best-action guidance.

Across the page and its major panels, operators can now encounter:

- `Loading`
- `Background Refresh`
- `Empty`
- `Partial / Degraded`
- `Success`
- `Validation Error`
- `System Error`
- `Unauthorized`
- `Not Found`

Every non-happy-path state now answers three questions inline:

- what happened in plain language
- what to do next without losing context
- where to recover safely through the owning runbook or validation guidance

The shared recovery links on this surface are:

- `windmill-operator-access-admin`
- `operator-onboarding`
- `operator-offboarding`
- `validate-repository-automation`

The `Latest Result` panel is now part of the recovery model, not just a log
dump. Treat its structured JSON payload as the canonical handoff artifact when
you need another operator to continue the task.

## Journey Analytics And Scorecards

ADR 0316 adds three operator-visible helpers to the same private raw app:

- an `Onboarding Success Scorecard` panel that summarizes checklist completion, first safe-action speed, search success, alert resolution speed, help recovery, and resumable-tour completion
- a `Contextual Help Drawer` that records privacy-preserving help opens and successful recovery completions without storing free-form operator content
- a transient alert banner that offers acknowledgement, drawer handoff, and retry affordances when the roster, inventory, or a governed mutation returns an error

The durable scorecard path stays repo-managed:

- browser milestones emit only bounded categorical events
- `f/lv3/operator_journey_event` records those milestones into `.local/state/journey-analytics/`
- `f/lv3/operator_journey_scorecards` renders the current report and writes the latest JSON snapshot for scheduled review
- Plausible receives canonical route milestones for `ops.lv3.org`
- Glitchtip receives bounded failure signals only when a journey event explicitly requests it

Privacy constraints:

- raw operator notes, query text, secrets, markdown, and stack traces are not allowed in recorded journey-event properties
- quick-filter analytics use length buckets instead of raw search terms
- the repo-local ledger under `.local/state/journey-analytics/` is the authoritative source for the scorecard report

## Operator Workflows Backed By The App

- onboarding: `f/lv3/operator_onboard`
- off-boarding: `f/lv3/operator_offboard`
- roster sync: `f/lv3/sync_operators`
- inventory lookup: `f/lv3/operator_inventory`
- roster listing: `f/lv3/operator_roster`
- rich note persistence: `f/lv3/operator_update_notes`
- journey event recording: `f/lv3/operator_journey_event`
- journey scorecard report rendering: `f/lv3/operator_journey_scorecards`

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

## Command Palette

ADR 0311 adds a global `Ctrl/Cmd+K` command palette to the app.

The live palette is intentionally a fast-open surface, not a mutation bypass:

- applications and pages can open directly
- operators can be selected directly into the roster and inventory workflow
- safe quick actions such as refresh and guided-tour launch run immediately
- ADR and runbook search results come from the repo-managed `f/lv3/command_palette_search` helper
- governed mutations still route into the full onboarding, off-boarding, reconciliation, or notes-save flows

Palette behavior:

- `Ctrl/Cmd+K` toggles the palette from anywhere in the app
- `/` opens it when focus is not already inside a text field
- favorites and recents are browser-local and stay scoped to this app surface
- glossary entries deep-link to the canonical docs pages rather than storing a second policy source in the browser bundle

## New Operator Flow

1. Open Windmill and launch `f/lv3/operator_access_admin`.
2. Let the first-run tour start automatically, or choose `Onboard Admin Or Operator` or `Onboard Viewer` from `Guided Onboarding`.
3. Use the roster `Quick Filter` when you need to narrow by operator name, role, status, group, or notes before creating or reviewing access.
4. Use the AG Grid column controls to pin or resize columns when you need hidden metadata such as groups, Tailscale login, or notes.
5. Confirm the target role and complete the required form fields.
6. Resolve any inline schema validation feedback before submitting.
7. Submit the create action.
8. Record the returned bootstrap password securely.
9. Direct the new operator to sign in through Keycloak, rotate the bootstrap password, and complete TOTP enrollment.

## Off-boarding Flow

1. Open the same app.
2. Start `Off-board Operator` from `Guided Onboarding` if you want the step-by-step walkthrough.
3. Use the AG Grid roster to select the target operator or narrow the view with `Quick Filter`.
4. Optionally record a reason.
5. Resolve any inline schema validation feedback before submitting.
6. Submit the off-board action.
7. Refresh the roster and, when needed, inspect the per-operator inventory result.

## Inventory Review

Use `Review Inventory` from `Guided Onboarding` when you want a focused verification pass after onboarding, reconciliation, or off-boarding.

The panel reads the current live state for the selected operator and is the fastest post-mutation confidence check in the app. The AG Grid row selection drives both this panel and the off-boarding form, so keep the selected row aligned with the operator you intend to verify.

## Repo Validation

Run:

```bash
docker run --rm \
  -e WM_TOKEN="$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" \
  -v "$PWD/config/windmill/apps:/workspace" \
  ghcr.io/windmill-labs/windmill:1.662.0@sha256:13d5456a80500822446ce0154f68d5fd5089628df82e77e2bd9cb24ff898d58d \
  sh -lc 'cd /workspace && wmill generate-metadata f/lv3/operator_access_admin.raw_app --base-url http://100.64.0.1:8005 --workspace lv3 --token "$WM_TOKEN" --lock-only --skip-scripts --skip-flows --yes'
uv run --with pytest --with pyyaml python -m pytest tests/test_windmill_operator_admin_app.py -q
uv run --with pytest python -m pytest tests/test_journey_scorecards.py tests/test_windmill_operator_admin_app.py -q
uv run --with pytest --with pyyaml python -m pytest tests/test_command_palette_search.py tests/test_windmill_operator_admin_app.py -q
uv run --with pytest --with pyyaml python -m pytest tests/test_operator_manager.py tests/test_windmill_operator_admin_app.py -q
python3 -m py_compile scripts/operator_manager.py scripts/journey_scorecards.py config/windmill/scripts/operator-roster.py config/windmill/scripts/operator-inventory.py config/windmill/scripts/operator-update-notes.py config/windmill/scripts/operator-journey-event.py config/windmill/scripts/operator-journey-scorecards.py
ANSIBLE_CONFIG=ansible.cfg ANSIBLE_COLLECTIONS_PATH=collections uvx --from ansible-core ansible-playbook -i inventory/hosts.yml playbooks/windmill.yml --syntax-check
tmpdir="$(mktemp -d)" && mkdir -p "$tmpdir/f/lv3" && rsync -a config/windmill/apps/f/lv3/operator_access_admin.raw_app/ "$tmpdir/f/lv3/operator_access_admin.raw_app/" && cd "$tmpdir/f/lv3/operator_access_admin.raw_app" && npm ci --no-audit --no-fund && npx tsc --noEmit
```

## Notes

- The bootstrap password is intentionally shown once in the onboarding result and is not written to git.
- The app depends on the worker checkout being mounted at `/srv/proxmox_florin_server`; the Windmill runtime now bind-mounts that host checkout into both worker pools.
- The AG Grid roster keeps the browser experience dense, but the actual access mutations still flow only through the repo-governed ADR 0108 scripts.
- The app now relies on repo-managed frontend dependencies staged during raw-app sync, so new browser libraries must be added to the raw app `package.json` and verified through `make converge-windmill`.
- ADR 0311 now relies on the repo-managed `f/lv3/command_palette_search` helper for ADR and runbook matches. If the palette starts returning stale or empty docs results, re-run `f/lv3/command_palette_search` directly before assuming the browser bundle is at fault.
- The app is a Windmill-private admin surface; `ops.lv3.org` remains a separate portal.
- ADR 0241 keeps the stored source format as markdown even though the editor is rich text, so repo diffs, sync workflows, and later migrations stay inspectable.
- Inline validation mirrors the frontend schema only; the governed backend scripts remain the authoritative enforcement path for live identity mutations.
- Guided tours are browser-local helpers only; they do not change the governed backend path or replace the runbooks.
- Repo-managed Windmill raw apps with frontend dependencies should commit `package-lock.json`; the runtime now prefers `npm ci` before raw-app sync and only falls back to `npm install --no-package-lock` when no lockfile exists.
- Raw-app dependency changes must refresh `config/windmill/apps/wmill-lock.yaml` with `wmill generate-metadata` before the next live Windmill sync, or the remote bundle step can fail with unresolved package imports.
- The ADR 0316 scorecards intentionally combine browser milestones, worker-side ledger events, Plausible route aggregates, and Glitchtip failure counts. If the panel looks stale, re-run `f/lv3/operator_journey_scorecards` and inspect `.local/state/journey-analytics/operator-access-admin-latest.json` in the worker checkout before assuming the browser bundle is wrong. The mirrored Glitchtip secret can now be a DSN or a direct store URL, but `glitchtip_events` will stay at `0` until `errors.lv3.org` serves a valid TLS endpoint backed by a live Glitchtip runtime.
