# Platform Operations Portal

## Purpose

The operations portal is a repo-managed interactive runtime served at
`https://ops.example.com` from `docker-runtime`.

It gives operators one place to answer:

- where does a service live
- which VM owns it
- what subdomain points at it
- which runbook documents it
- which ADR introduced it
- which agent tools already exist
- which first-party surface should I jump to next

The current portal combines:

- a FastAPI-based operator shell under `scripts/ops_portal/`
- repo-synced catalogs and receipts mirrored into `/opt/ops-portal/data`
- dashboard actions such as the runbook launcher
- a shared masthead application launcher with task-lane grouping, persona filters,
- a return-to-task surface for resumable runbook flows, including a task
  notification lane and activity timeline
- a shared masthead application launcher with task-lane grouping, persona filters,
  favorites, and recent destinations

## Task-Lane Information Architecture

ADR 0309 adds a task-oriented information architecture layer above the existing
service, workflow, and runbook catalogs.

The live interactive shell now uses five canonical lanes:

- `Start`
- `Observe`
- `Change`
- `Learn`
- `Recover`

The lane overlay is declared in:

- `config/workbench-information-architecture.json`
- `docs/schema/workbench-information-architecture.schema.json`
- `scripts/workbench_information_architecture.py`

The interactive portal uses that overlay to:

- group sidebar navigation by operator intent instead of only by product name
- assign one primary lane plus optional secondary lanes to each first-party page
- map launcher services, workflows, and runbooks onto the same lane model
- show the next likely lane after success and after failure through the visible
  lane banner on page sections and launcher cards

## Contextual Help Drawer

ADR 0313 adds a shared **Contextual Help** drawer to both the interactive ops
portal runtime and the generated static snapshot.

The drawer is meant to answer the page-local questions operators hit most often
without forcing them to leave the flow of work:

- what this page is for and who it is aimed at
- which platform terms on the page have special meaning
- which ADRs, runbooks, or docs pages are the canonical next read
- how to back out safely or hand the task off when the action is risky

Expected root-page content now includes:

- a **Contextual Help** toggle in the masthead
- glossary entries such as `Live apply`, `Recovery tier`, and `Handoff`
- a visible **Escalation Path** block with the owning runbook and handoff route

Page-specific help content is assembled in
`scripts/ops_portal/contextual_help.py` so the generated snapshot and the live
runtime stay on the same glossary and escalation model.

## Local Generation

Generate the static snapshot locally when you need a read-only render for checks,
design review, or fallback artifacts:

```bash
make generate-ops-portal
```

This renders:

- `build/ops-portal/index.html`
- `build/ops-portal/environments/index.html`
- `build/ops-portal/vms/index.html`
- `build/ops-portal/subdomains/index.html`
- `build/ops-portal/runbooks/index.html`
- `build/ops-portal/adrs/index.html`
- `build/ops-portal/agents/index.html`

The generator reads:

- `config/environment-topology.json`
- `config/service-capability-catalog.json`
- `config/subdomain-catalog.json`
- `config/agent-tool-registry.json`
- `versions/stack.yaml`
- `docs/adr/*.md`
- `docs/runbooks/*.md`

The generated snapshot is not the production runtime. Production serves the
interactive app from `scripts/ops_portal/` and syncs the same catalogs into the
container data directory during converge.

## Health Data

The portal can embed a generation-time health snapshot:

```bash
uv run --with pyyaml --with jsonschema python3 scripts/generate_ops_portal.py \
  --health-snapshot path/to/snapshot.json \
  --write
```

When no snapshot is provided, the portal still renders and marks service health as `unknown`.

## Validation

Run:

```bash
uv run --with pyyaml --with jsonschema python3 scripts/generate_ops_portal.py --check
make syntax-check-ops-portal
```

That covers both sides of the portal contract:

- `generate_ops_portal.py --check` verifies the static snapshot still renders
- `make syntax-check-ops-portal` verifies the interactive runtime playbook and
  role wiring
- the runtime verification role also asserts that the live root page includes
  `Contextual Help`, `Live apply`, and `Escalation Path`

For the launcher-specific runtime behavior, also run the focused tests:

```bash
uv run --with pytest --with pyyaml --with jsonschema --with fastapi==0.116.1 --with httpx==0.28.1 --with cryptography==45.0.6 --with PyJWT==2.10.1 --with jinja2==3.1.5 --with itsdangerous==2.2.0 --with python-multipart==0.0.20 pytest tests/test_interactive_ops_portal.py tests/test_ops_portal_runtime_role.py tests/test_ops_portal_playbook.py tests/test_ops_portal.py -q
```

For a direct local HTML assertion on the built snapshot:

```bash
python3 - <<'PY'
from pathlib import Path
html = Path("build/ops-portal/index.html").read_text(encoding="utf-8")
for marker in ("Contextual Help", "Live apply", "Escalation Path"):
    assert marker in html, marker
print("ops-portal-help-ok")
PY
```

## Deployment

For a repo-managed converge without the production live-apply guard:

```bash
make converge-ops-portal env=production
```

For the governed production replay used during live applies:

```bash
make ensure-resource-lock-registry
make resource-lock-acquire \
  RESOURCE='vm:120/service:ops_portal' \
  HOLDER='agent:<workstream-or-operator>' \
  LOCK_TYPE=exclusive \
  TTL_SECONDS=3600 \
  CONTEXT_ID='<workstream-or-ticket>'

ALLOW_IN_PLACE_MUTATION=true \
make live-apply-service service=ops_portal env=production \
  EXTRA_ARGS='-e bypass_promotion=true'
```

`bypass_promotion=true` is the documented break-glass path for direct production
replays from a workstream branch. The Make target still enforces canonical truth,
interface contracts, redundancy checks, immutable-guest checks, and emits the
promotion-bypass audit event before running the service playbook.

`ALLOW_IN_PLACE_MUTATION=true` is the documented ADR 0191 narrow exception for
`ops_portal` because the live service still runs on immutable-replacement-governed
`docker-runtime`. The `live-apply-service` target now injects
`ops_portal_repo_root=$(REPO_ROOT)` automatically for `ops_portal`, so the
active worktree is the exact checkout mirrored into `/opt/ops-portal/service`
without needing a second manual override.

The runtime mirror only pulls structured production/staging `*.json` receipt
documents from `receipts/live-applies/` and `receipts/drift-reports/`.
`receipts/live-applies/evidence/` transcripts and `preview/` validation
payloads stay in the repo as authoritative branch history, but they are not
copied into `/opt/ops-portal/data/` because the interactive runtime reads
deployment receipt JSON documents rather than raw transcript blobs.

Before starting the replay, confirm no competing branch-local `ops_portal`
production apply is still active:

```bash
ps -axo pid=,etime=,command= | rg 'ws-.*ops_portal.*playbooks/services/ops_portal.yml'
```

Do not run two branch-local `ops_portal` production replays at the same time.
Concurrent applies share `/opt/ops-portal/service` on `docker-runtime` and
can clobber each other's uploaded tree, which leaves partial routes such as
`/partials/launcher` or `/partials/tasks` missing even when the playbook itself
reached the verify phase. The runtime role now refreshes
`/opt/ops-portal/service` again immediately before syncing the Docker build
context, and it checks these live partials locally during replay so drift fails
closed instead of silently publishing an incomplete shell. That extra refresh
narrows the overlap window, but it does not make concurrent production replays
safe.

After the replay completes or fails, release the shared lock:

```bash
make resource-lock-release \
  RESOURCE='vm:120/service:ops_portal' \
  HOLDER='agent:<workstream-or-operator>'
```

After a live ADR 0313 replay, also confirm the root page contains the help
drawer strings and the task-lane shell cues from the guest-local runtime:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 \
  'curl -fsS http://127.0.0.1:8092/ | grep -E "Contextual Help|Live apply|Escalation Path|Journey-Aware Home|Attention Center|Platform Overview|Start|Observe|Change|Learn|Recover"'
```

## Publication Boundary

The portal publication path has three repo-managed components:

- `ops_portal_runtime` serves the interactive FastAPI shell on
  `docker-runtime`
- `public_edge_oidc_auth` runs `oauth2-proxy` on `nginx-edge` and uses the Keycloak client secret mirrored at `.local/keycloak/ops-portal-client-secret.txt`
- `nginx_edge_publication` forwards authenticated traffic for `ops.example.com` to
  the interactive runtime instead of serving the old static snapshot directly

Internal verification should show an unauthenticated request redirecting to the sign-in flow:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes ops@100.118.189.95 \
  'curl -k -I -H "Host: ops.example.com" https://10.10.10.10'
```

Expected result: `HTTP/2 302` with `Location: https://ops.example.com/oauth2/sign_in?...`

External publication is now verified end to end:

- `https://ops.example.com` returns `302` to `/oauth2/sign_in` for unauthenticated requests
- `https://sso.example.com/realms/lv3/.well-known/openid-configuration` returns `200`

Two network details are now part of the live publication contract:

- `nginx-edge` sets `proxmox_firewall_enabled: false`, which leaves `net0` at `firewall=0` and avoids the Proxmox `fwbr*` bridge path that was dropping public `80/443` SYNs before the guest kernel saw them
- `docker-runtime` must allow TCP `8091` from `nginx-edge` in both the Proxmox VM firewall and the in-guest nftables policy so `sso.example.com` and `oauth2-proxy` can reach Keycloak

If cloud access to `https://ops.example.com` regresses, verify those two conditions before changing the portal or Keycloak configuration again.

## Application Launcher

ADR 0235 adds a shared masthead application launcher as the default
cross-application switcher inside the interactive portal.

Launcher inputs come from repo-managed data:

- `config/service-capability-catalog.json`
- `config/subdomain-exposure-registry.json`
- `config/workflow-catalog.json`
- `config/persona-catalog.json`
- `config/workbench-information-architecture.json`

Workflow entries only appear when the workflow declares
`human_navigation.launcher` metadata in the workflow catalog.

Operator flow:

1. Open `https://ops.example.com` and complete the normal sign-in flow.
2. Select **Application Launcher** in the masthead.
3. Search for a destination, switch persona if needed, and use the task-lane
   groups to narrow the list.
4. Toggle the star button on any destination to add or remove it from
   favorites.
5. Open a destination through the launcher to record it in recent destinations.

Expected behavior:

- the launcher groups entries into `Start`, `Observe`, `Change`, `Learn`, and
  `Recover`
- switching persona changes which destinations stay visible without mutating the
  underlying catalogs
- favorites and recent destinations persist for the current browser session
- each launcher card shows the primary lane together with the next likely lane
  after success and after failure
- launcher redirects preserve the destination URL while recording the recent
  visit server-side through the portal session

The safest live verification path is:

1. favorite `Keycloak` or another common admin surface
2. open `Validation Gate Status` or `Drift Status` from the launcher
3. reopen the launcher and confirm the destination now appears under
   **Recent destinations**

A failed live replay that serves `/health` but returns `404` for
`/partials/launcher` indicates sync drift or a clobbered guest-side portal tree,
not a healthy launcher rollout.

## Journey-Aware Entry Routing

ADR 0308 adds a dedicated entry route at `https://ops.example.com/entry` and the
local neutral view `http://127.0.0.1:8092/entry?neutral=1`.

The entry router now applies this order after sign-in:

1. a permitted deep link from `next=` or a curated `item_id=`
2. unfinished activation work
3. a saved home pinned by the operator
4. a role-derived default home
5. the neutral start surface

Current role defaults are:

- `viewer` -> Homepage (`observe-first`)
- `operator` -> Ops Portal (`operate-first`)
- `admin` -> Ops Portal (`govern-and-change`)

The start surface keeps activation state and saved-home preference in
browser cookies:

- `lv3_workbench_activation_steps`
- `lv3_workbench_activation_skip`
- `lv3_workbench_home`

Pinning a preferred home stays blocked until the activation checklist is
completed or explicitly skipped. Invalid `next=` URLs fail closed back to the
neutral start surface; only local paths and `https://*.example.com` URLs are
accepted.

The safest live verification path is:

1. open `https://ops.example.com/entry` and confirm the unauthenticated edge still
   redirects through `oauth2-proxy`
2. authenticate and open `/entry?neutral=1`
3. confirm **Journey-Aware Start Surface** renders with the activation
   checklist and the four curated home destinations
4. mark the activation steps complete or use **Skip for now**
5. pin `Docs Portal` or another curated home, revisit `/entry`, and confirm the
   router now sends the session to the saved home instead of the role default
6. clear the saved home and confirm the next `/entry` visit falls back to the
   role default again

Guest-local verification should include:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 \
  'curl -fsS http://127.0.0.1:8092/entry?neutral=1 | grep -E "Journey-Aware Start Surface|Pin as home|Skip for now"'
```

## First-Run Activation Checklist

ADR 0310 adds the first-run activation panel directly to the interactive ops
portal instead of creating a separate onboarding shell.

Checklist inputs come from repo-managed data:

- `config/activation-checklist.json`
- `docs/schema/activation-checklist.schema.json`

Portal behavior:

- the checklist renders at `https://ops.example.com#activation`
- item progress is persisted in the signed browser session so normal refreshes
  and redirects keep the current first-run state
- launcher entries with purpose `administer` stay out of the active destination
  set until the required checklist stages are complete or advanced tools are
  explicitly revealed for the session
- mutating service actions (`deploy`, `restart`, `rotate-secret`) and mutating
  runbooks fail closed server-side under the same activation state

Operator flow:

1. Open `https://ops.example.com` and start at the **First-Run Activation** panel.
2. Mark the required items complete as you review the linked runbooks and portal
   panels.
3. Use `Validation Gate Status` as the safe first task inside the runbook
   launcher.
4. Only use **Reveal advanced tools for this session** when you need a
   supervised bypass before the required stages are complete.

Expected verification path:

1. `GET /partials/activation` returns `200` and renders `First-Run Activation`
2. before activation completes, `/partials/launcher` shows the locked-state copy
   and `GET /launcher/go/service:keycloak` redirects to `/#activation`
3. before activation completes, `/partials/overview` renders disabled deploy,
   restart, and rotate-secret controls
4. after the required items are completed or the supervised reveal path is
   triggered, `/partials/launcher` exposes admin destinations and mutating
   actions no longer render as locked

## Shared Attention Center

ADR 0312 adds a shared notification center plus a browser-visible activity
timeline to the interactive portal.

Operator flow:

1. Open `https://ops.example.com`.
2. Scroll to **Attention Center**.
3. Review the active queue for drift, runtime assurance, blocked coordination,
   maintenance, or live-apply follow-up items.
4. Use **Acknowledge** when a human has taken ownership, or **Dismiss** when the
   item is no longer useful in the active queue.
5. Reopen an acknowledged or dismissed item if it still needs human attention.
6. Confirm the action also appears in **Activity Timeline** so the change is
   auditable without deleting the underlying source signal.

The current implementation persists attention state under the managed runtime
path `/opt/ops-portal/state/attention-state.json` on `docker-runtime`
instead of keeping it only in browser session data.

The safest live verification path is:

1. open **Attention Center**
2. acknowledge one runtime assurance or drift item
3. refresh the page and confirm the item remains under the acknowledged section
4. open **Activity Timeline** and confirm the acknowledgement event is present

## Structured Runbook Launcher

The interactive portal runbook panel now loads its entries from the platform API gateway instead of maintaining a separate local workflow-only list.

Operator flow:

1. Open `https://ops.example.com`.
2. Use the **Runbook Launcher** panel.
3. Pick one runbook that explicitly opts into the `ops_portal` delivery surface.
4. Submit JSON parameters if the runbook requires them.

The safest verification path is the repo-managed `docs/runbooks/validation-gate-status.yaml` runbook, which is read-only and returns the current validation-gate summary through the shared runbook service.

Portal operators do not need to know how the workflow is wired underneath:

- the portal parses JSON parameters and forwards them as a thin adapter
- the API gateway enforces auth and resolves the shared runbook contract
- the shared use-case service owns runbook lookup, surface allowlists, templating, workflow sequencing, and persisted run records
- browser-local drafts stay separate from committed task state so an unfinished
  form does not pollute the audit trail or the persisted resume summary

## Return To Task

Portal-launched resumable flows now reopen through the shared task route
`/tasks/runbooks/<run_id>`.

Operator flow:

1. Launch a portal-exposed runbook that intentionally pauses or escalates.
2. Reopen the task from the **Return To Task** section on the home surface.
3. Use the saved resume summary to inspect what already happened and which step
   comes next.
4. Resume only after reviewing the stored evidence and the next human action.

The dashboard keeps two reentry lanes visible:

- **Notification Center** cards for tasks that currently need review
- **Activity Timeline** entries that deep-link back to the same task detail page

The safest resumable verification path is the repo-managed
`docs/runbooks/validation-gate-task-review.yaml` flow:

1. launch it from the portal
2. confirm the task pauses after the first validation-gate summary
3. reopen `/tasks/runbooks/<run_id>` and confirm the resume summary shows the
   last safe resume point and the next action
4. resume the task and confirm the final diagnostic snapshot completes

## Declared-To-Live Attestation

The interactive portal overview now includes the declared-to-live attestation rollup from the platform API gateway.

Operator flow:

1. Open `https://ops.example.com`.
2. Check the **Attested** summary tile in the overview strip.
3. Open a service card and read the `Declared-live ...` hint strip for endpoint, route, and receipt witness state.
4. If the overview banner says declared-to-live data is degraded, verify the upstream gateway payload before changing portal code.

Internal verification from a trusted network path:

```bash
curl -sf http://10.10.10.20:8092/partials/overview | grep -E 'Attested|Declared-live'
curl -H "Authorization: Bearer $LV3_TOKEN" https://api.example.com/v1/platform/attestation
```

Expected result:

- the portal overview shows the attestation summary tile
- affected service cards render `Declared-live <status> · endpoint <status> / route <status> / receipt <status>`
- the gateway route returns the same witness record shape the portal is rendering
