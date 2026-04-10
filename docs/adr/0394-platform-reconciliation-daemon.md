# ADR 0394: Platform Reconciliation Daemon — Continuous Portal and Artifact Regeneration

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet applied
- Implemented In Platform Version: not yet applied
- Implemented On: not yet applied
- Date: 2026-04-10
- Concern: Automation, Platform, Observability
- Depends on: ADR 0044 (Windmill), ADR 0091 (Drift Detection), ADR 0119 (Budgeted Workflow Scheduler), ADR 0226 (Systemd Timers for Control Loops), ADR 0152 (Homepage Dashboard)
- Tags: reconciliation, automation, cron, heartbeat, portals, iac, drift

---

## Context

The LV3 platform maintains four operator-facing portals that are generated from
canonical data sources (service catalogs, ADR corpus, deployment receipts):

| Portal | URL | Generator | Source of Truth |
|--------|-----|-----------|-----------------|
| Homepage | home.lv3.org | `scripts/generate_homepage_config.py` | `service-capability-catalog.json`, `subdomain-catalog.json` |
| Ops Portal | ops.lv3.org | `scripts/generate_ops_portal.py` | Service catalog, inventory, ADRs, runbooks |
| Docs Portal | docs.lv3.org | `scripts/build_docs_portal.py` | `docs/` tree, MkDocs |
| Changelog | changelog.lv3.org | `scripts/generate_changelog_portal.py` | Receipts, promotions, mutation audit |

### The staleness problem

Today, portal regeneration is entirely manual:

1. A developer adds or removes a service (e.g., One-API removed in ADR 0393,
   Open WebUI removed in ADR 0390).
2. The service-capability-catalog and subdomain-catalog are updated.
3. But `generate_homepage_config.py` is not re-run, and `make converge-homepage`
   is not invoked.
4. The live dashboard at home.lv3.org continues showing removed services.

The same pattern applies to all four portals. The ops portal shows stale ADR
counts, the changelog portal misses recent deployments, and the docs portal
lags behind new runbooks.

This creates a class of bugs that is invisible until someone visits the portal
and notices the drift — the exact opposite of infrastructure-as-code.

### Inspiration: OpenClaw's dual-model automation

OpenClaw (an agent automation platform) separates automation into two
complementary execution models:

- **Heartbeat**: A periodic main-session turn (~30 min) that batches multiple
  checks with full session context. Best for work that benefits from
  holistic awareness.
- **Cron**: A precise-timing scheduler for isolated, deterministic tasks.
  Each job runs independently without full session context.

This separation is directly applicable to our portal reconciliation problem:

- **Cron-like**: Regenerate portal artifacts on a fixed schedule (every 15 min
  or on-push). Deterministic, no session context needed.
- **Heartbeat-like**: A periodic health sweep that verifies portal fidelity
  against the catalog, detects drift, and triggers remediation.

### What we already have

- **Windmill** (ADR 0044): Workflow scheduler with API, GUI, and cron support.
  Already runs budgeted workflows (ADR 0119).
- **Systemd timers** (ADR 0226): Policy says host-resident automation uses
  `systemd.timer`, not cron.
- **Drift detection** (ADR 0091): Existing Windmill workflow for configuration
  drift. This ADR extends the pattern to generated artifacts.

---

## Decision

Implement a **Platform Reconciliation Daemon** — a set of scheduled workflows
that continuously regenerate all operator-facing portals and artifacts from
their canonical data sources, detect drift, and optionally auto-deploy.

### Architecture

```
                    +-----------------------+
                    |   Windmill Scheduler  |
                    |  (cron + API trigger) |
                    +-----------+-----------+
                                |
              +-----------------+-----------------+
              |                 |                 |
    +---------v----+  +---------v----+  +---------v----+
    | Portal Regen |  | Artifact     |  | Health       |
    | Workflow     |  | Validation   |  | Sweep        |
    | (cron: */15) |  | (post-push)  |  | (cron: */60) |
    +---------+----+  +---------+----+  +---------+----+
              |                 |                 |
              v                 v                 v
    +-------------------+  +-----------+  +---------------+
    | generate_*_portal |  | --check   |  | Compare live  |
    | scripts           |  | mode      |  | vs generated  |
    +-------------------+  +-----------+  +---------------+
              |                 |                 |
              v                 v                 v
    +-------------------+  +-----------+  +---------------+
    | Ansible converge  |  | Pass/fail |  | Ntfy alert on |
    | (if changed)      |  | + ntfy    |  | drift         |
    +-------------------+  +-----------+  +---------------+
```

### Three workflow tiers

#### Tier 1: Portal Regeneration (cron — every 15 minutes)

A Windmill workflow that runs the generation scripts and compares output to
the currently deployed artifacts:

```bash
# 1. Regenerate all portal artifacts
python scripts/generate_homepage_config.py --output-dir build/homepage-config --write
python scripts/generate_ops_portal.py --write
python scripts/build_docs_portal.py --write
python scripts/generate_changelog_portal.py --write

# 2. Detect changes (git diff on build/ directory)
# 3. If changed: commit, push, trigger Ansible converge via Semaphore/API
# 4. If unchanged: no-op, log "portals in sync"
```

This is the **cron** side of the model — deterministic, isolated, precise timing.

#### Tier 2: Post-Push Validation (event-driven)

Triggered by Gitea/GitHub webhooks on push to main:

1. Run all `--check` modes to verify build artifacts match committed code.
2. If stale: trigger Tier 1 regeneration.
3. Report pass/fail to ntfy and the ops portal.

This catches the case where someone pushes catalog changes but forgets to
regenerate.

#### Tier 3: Health Sweep (heartbeat — every 60 minutes)

A broader reconciliation pass that:

1. Fetches each portal's live HTML and checks for expected service entries.
2. Compares the live homepage service tiles against `service-capability-catalog.json`.
3. Verifies that removed services (lifecycle_status != "active") do not appear.
4. Verifies that active services do appear.
5. Reports drift to ntfy with remediation instructions.

This is the **heartbeat** side — needs awareness of the full platform state
to make judgments.

### API surface

All workflows are exposed through Windmill's API, enabling:

- **Programmatic trigger**: `POST /api/w/lv3/jobs/run/f/reconciliation/portal_regen`
- **Status query**: `GET /api/w/lv3/jobs/completed/f/reconciliation/portal_regen`
- **GUI access**: Windmill's web UI at the existing internal endpoint shows
  run history, logs, and manual trigger buttons.

### Reconciliation service library

Create a shared Python module (`scripts/reconciliation/`) that provides:

```python
# Core reconciliation primitives
def detect_portal_drift(portal: str) -> DriftReport
def regenerate_portal(portal: str) -> RegenerationResult
def converge_portal(portal: str) -> ConvergenceResult
def sweep_portal_health(portal: str, live_url: str) -> HealthReport

# Aggregate operations
def reconcile_all_portals() -> ReconciliationSummary
def validate_all_artifacts() -> ValidationSummary
```

This library is callable from:
1. Windmill workflows (scheduled)
2. CLI (`python -m scripts.reconciliation.cli reconcile-all`)
3. API gateway endpoints (for agent access)
4. Makefile targets (`make reconcile-portals`)

### Scope of managed portals and artifacts

| Artifact | Generator | Reconciliation Tier |
|----------|-----------|-------------------|
| Homepage config | `generate_homepage_config.py` | Tier 1 + Tier 3 |
| Ops portal | `generate_ops_portal.py` | Tier 1 + Tier 3 |
| Docs portal | `build_docs_portal.py` | Tier 1 |
| Changelog portal | `generate_changelog_portal.py` | Tier 1 |
| Platform manifest | `platform_manifest.py` | Tier 2 |
| Discovery artifacts | `generate_discovery_artifacts.py` | Tier 2 |
| ADR index | `generate_adr_index.py` | Tier 2 |

### Integration with existing systems

- **Ntfy** (ADR 0097): Drift alerts go to the `platform-reconciliation` topic.
- **Uptime Kuma**: Existing homepage monitor detects downtime; this ADR adds
  content-level fidelity checks.
- **Grafana**: Dashboard panel showing reconciliation run history, drift
  frequency, and mean-time-to-sync.
- **Ops Portal**: Reconciliation status widget showing last run, next scheduled,
  and any pending drift.

---

## Consequences

### Positive

- **Portals never go stale**: The 15-minute cron ensures that service additions,
  removals, and catalog changes are reflected within one cycle.
- **Drift is detected and alerted**: The health sweep catches cases where the
  generation pipeline itself has bugs or the deployment fails silently.
- **Single reconciliation library**: CLI, API, GUI, and scheduled access all
  use the same code — no fragmentation.
- **Builds on existing infrastructure**: Uses Windmill (already deployed),
  ntfy (already deployed), and the existing generation scripts.
- **Enables future automation**: Once the reconciliation library exists,
  agent workflows can trigger portal updates as part of service lifecycle
  operations (e.g., the decommission procedure in ADR 0389 can call
  `reconcile_all_portals()` as its final step).

### Trade-offs

- **15-minute lag**: Portal updates are not instant. Acceptable for an
  internal operator dashboard. Can be reduced by adding webhook triggers.
- **Windmill dependency**: Reconciliation scheduling depends on Windmill
  availability. Fallback: systemd timers on the control VM (ADR 0226).
- **Build server load**: Frequent regeneration adds minor load. Mitigated
  by the "if changed" guard — no-op runs are cheap.

### Risks

- **Runaway converge loops**: If the health sweep always detects drift
  (e.g., due to a time-dependent field), it could trigger endless
  reconvergence. Mitigation: cooldown period (minimum 30 min between
  converge triggers from the same drift source).
- **Secret exposure in logs**: Generation scripts read catalog files but
  not secrets. Windmill job logs are access-controlled. Low risk.

---

## Implementation Plan

### Phase 1: Reconciliation library (this branch)

1. Create `scripts/reconciliation/` module with core primitives.
2. Add `make reconcile-portals` and `make check-portal-drift` targets.
3. Wire `generate_homepage_config.py --check` into the validation pipeline.

### Phase 2: Windmill workflows

1. Create Windmill flow `reconciliation/portal_regen` with 15-min cron.
2. Create Windmill flow `reconciliation/health_sweep` with 60-min cron.
3. Add API gateway route for manual trigger.

### Phase 3: Post-push webhook

1. Add Gitea webhook for push-to-main events.
2. Webhook handler calls Tier 2 validation.
3. Ntfy notification on validation failure.

### Phase 4: Observability

1. Grafana dashboard for reconciliation metrics.
2. Ops portal widget for reconciliation status.
3. Uptime Kuma content check for portal fidelity.

---

## Related

- ADR 0044: Windmill for Agent and Operator Workflows
- ADR 0091: Continuous Drift Detection and Reconciliation
- ADR 0119: Budgeted Workflow Scheduler
- ADR 0152: Homepage for Unified Service Dashboard
- ADR 0226: Systemd Units, Timers, and Paths for Host-Resident Control Loops
- ADR 0389: Standard Procedure for Decommissioning a Platform Service
- ADR 0395: Homepage Dashboard Fidelity (companion ADR)
