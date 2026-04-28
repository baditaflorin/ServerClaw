# ADR 0453: Integration-Health Telemetry

- Status: Proposed
- Implementation Status: Not started
- Date: 2026-04-28
- Concern: release-stability, observability, gate-discipline
- Tags: telemetry, metrics, ci, release-health
- Builds on:
  - ADR 0267 (Expiring Gate Bypass Waivers With Structured Reason Codes) — bypass *governance* already exists; this ADR adds *rate metrics* on top
- Related:
  - ADR 0419 (PR-Based Integration Flow)
  - ADR 0420 (CI Release-Readiness Checks)
  - ADR 0087 (Repository Validation Gate)
  - ADR 0452 (Workstream Lifecycle Auto-Close) — provides workstream-aging input
  - ADR 0454 (Incident & Postmortem Registry) — surfaces aged-out waiver follow-ups

---

## Context

A metrics review of the 30-day window ending 2026-04-28 surfaced four
integration-health signals that no current ADR governs:

1. **~8 reverts/rollbacks** clustered around large refactors
   (ADR 0373, 0407, 0438). The pre-push gate caught most before
   live-apply, but the fix-revert-rerefactor loop is expensive and
   invisible until someone runs `git log --grep="Revert"` by hand.
2. **Bypass *rate* is invisible.** ADR 0267 already governs each
   bypass individually (structured reason codes, expiry, substitute
   evidence; 19 bypass receipts in `receipts/gate-bypasses/` as of
   2026-04-28). What is missing is a rolling-window *rate* metric
   that flags when the same reason class is firing repeatedly enough
   to indicate systemic gate erosion rather than isolated incidents.
3. **No live-apply lag tracking.** Time between `[release]` and the
   matching `[live-apply]` receipt is invisible. Some receipts close
   the loop same-day; others take >7d, and the platform does not
   distinguish.
4. **No periodic surfacing.** The metrics review that found these is
   a one-shot human exercise. Without automation, the next regression
   gets caught only when someone manually re-runs the analysis.

ADR 0420 covers *correctness* gates (manifest fresh, version bumped).
ADR 0267 covers *individual* bypass governance. Neither covers
*health trends* that only show up over rolling windows.

### Scope clarification

This ADR does **not** redefine bypass reason codes — those live in
`config/gate-bypass-waiver-catalog.json` per ADR 0267 and already
include the closed taxonomy (`emergency_hotfix`,
`build_server_unreachable`, `pre_existing_gate_failures`, etc.). The
9-code catalog is sufficient; this ADR only adds aggregate
observability over it.

---

## Decision

### 1. Derived integration-health artifact

Add `scripts/generate_integration_health.py --write`, producing
`build/integration-health.json` on every `[release]` and `[live-apply]`
commit landing on main:

```json
{
  "generated_at": "2026-04-28T12:00:00Z",
  "windows": {
    "release_stability_14d": 0.92,
    "gate_bypass_rate_30d": 19,
    "gate_bypass_top_reason_30d": "pre_existing_gate_failures",
    "gate_bypass_repeat_reasons_30d": ["pre_existing_gate_failures"],
    "live_apply_lag_p95_days": 5.2,
    "workstream_aging_max_days": 38
  },
  "thresholds": {
    "release_stability_14d_min": 0.90,
    "gate_bypass_rate_30d_max": 8,
    "gate_bypass_repeat_threshold": 3,
    "live_apply_lag_p95_days_max": 7,
    "workstream_aging_max_days_max": 45
  },
  "breaches": ["gate_bypass_rate_30d"]
}
```

Definitions:

- **release_stability** = `(release_commits − revert_commits) / release_commits`
  over rolling 14d. Computed by parsing commit messages on `main`.
- **gate_bypass_rate_30d** = count of files in
  `receipts/gate-bypasses/` with `created_at` inside the trailing 30d
  window. Source of truth is the receipt store, not git-grep.
- **gate_bypass_repeat_reasons_30d** = reason codes that appear
  ≥`gate_bypass_repeat_threshold` times in the 30d window. Repeated
  same-reason bypasses indicate systemic gate erosion that ADR 0267's
  per-waiver expiry does not catch on its own.
- **live_apply_lag** = days between a `[release] X.Y.Z` commit and the
  earliest receipt under `receipts/live-applies/` referencing that
  version. p95 across the trailing 30d.
- **workstream_aging** = max days a workstream has been in
  `workstreams/active/` without a metadata change, sourced from
  ADR 0452 lifecycle data.

### 2. Threshold-driven CI block

Extend the ADR 0420 release-readiness CI job with an `integration-health`
check. Behaviour:

- **Advisory** on non-`[release]` PRs (warn, do not block).
- **Enforced** on `[release]` PRs: any breached threshold blocks merge
  until either (a) the breach clears or (b) the PR description includes
  an `INTEGRATION_HEALTH_ACK: <reason>` line owned by an admin.

The ack escape hatch exists because some breaches are knowingly
acceptable (e.g. a deliberate revert of a bad refactor *increases*
revert count; that is the system working).

### 3. Bypass governance — explicit non-goal

Per the scope clarification above, this ADR does **not** redefine
reason codes. ADR 0267 already specifies:

- A closed taxonomy of 9 reason codes in
  `config/gate-bypass-waiver-catalog.json`
- Per-waiver expiry (`max_expiry_days` per code)
- Repeated-waiver escalation
  (`warning_after_occurrences=1`, `blocker_after_occurrences=2`)
- Required substitute evidence and remediation refs
- Schema validation in `docs/schema/gate-bypass-waiver-receipt.schema.json`

What ADR 0453 adds is the *aggregate rate metric* over the existing
receipt store, plus the integration-health surface that feeds the
monthly review (§4). Where ADR 0267's per-waiver enforcement and
ADR 0453's rate threshold both fire, the more restrictive applies.

If, in operation, the 9-code catalog proves insufficient (e.g. a new
class of legitimate bypass emerges), the catalog is extended via PR
under ADR 0267 — not under this ADR.

### 4. Monthly review automation

The monthly review runs from a scheduled job. The implementation
must be agent-neutral — any of the following triggers is acceptable:

- A GitHub Actions cron job (preferred — runs in repo, no
  agent-runtime dependency)
- A Gitea Actions cron mirror
- An ad-hoc scheduled task in any agent runtime that supports it
  (Claude Code `/schedule`, OpenAI Codex scheduled tasks, a plain
  cron entry on a control host calling
  `make integration-health-review`)

On the 1st of each month the trigger:

1. Regenerates `build/integration-health.json`.
2. Diffs against the prior month's snapshot
   (`build/integration-health.prev.json`).
3. Opens a PR titled `[ops] Integration health — <month>` with the
   diff, breached thresholds, top 3 reverts, and recommended
   actions.

The mechanism (cron, agent runtime, manual) is an operator choice;
the artifacts (`integration-health.json`, the PR) are identical
regardless. The PR is the metrics review. No human-driven
regeneration step.

---

## Consequences

**Positive**

- Release stability becomes a tracked, visible metric instead of a
  retrospective discovery
- Gate bypasses become enumerable, auditable, and rate-limited
  structurally — not by social convention
- Live-apply lag surfaces deploys that "merged but never shipped",
  closing a loop that today goes silent
- The metrics review becomes self-running; no agent has to remember to
  do it monthly

**Negative / Trade-offs**

- One more generator in the release flow (idempotent, fast)
- Pre-push hook gains another validation; rejecting a bypass costs
  ~30s of operator time when it triggers
- Threshold tuning will require a few cycles — initial values may be
  too tight or too loose. Mitigation: ack escape hatch + monthly review
  iterates the thresholds in the same diff PR.

**Neutral**

- The closed-enum reason codes will reject some currently-valid
  bypasses retroactively. Existing bypass commits stay; only new
  bypasses must conform.

---

## Boundaries

- This ADR does **not** define a runtime alerting system. ADR 0114
  (rule-based incident triage engine) handles runtime alerts; this is
  a CI/release-side health surface.
- It does **not** replace per-service health probes (uptime-kuma,
  Prometheus). Those are workload health; this is repository
  integration health.
- It does **not** govern hotfix mechanics — when an `emergency_hotfix`
  bypass is genuine, the bypass succeeds. The governance is on
  *follow-up*, not on the emergency itself.
- **Agent neutrality.** The generator script, the JSON artifact
  schema, the threshold values, the `INTEGRATION_HEALTH_ACK` escape
  hatch, and the monthly review trigger are agent-invariant. Any
  LLM agent or cron implementation can produce identical outputs;
  the ADR does not pin the trigger to any one agent runtime.

---

## Implementation Notes

1. Bootstrap thresholds from the 30-day baseline (recorded as
   `receipts/audits/2026-04-28-gate-bypass-baseline.json` per ws-0453):
   - `release_stability_14d_min`: 0.90 (current ~0.92)
   - `gate_bypass_rate_30d_max`: 8 (current 19 — already breached;
     accept the breach for one cycle then enforce, since most are
     `pre_existing_gate_failures` clusters around the ws-0346/ws-0374
     remediation push)
   - `gate_bypass_repeat_threshold`: 3 (any reason code firing 3+
     times in the window flags repeat-class erosion)
   - `live_apply_lag_p95_days_max`: 7 (baseline first)
   - `workstream_aging_max_days_max`: 45 (requires ADR 0452)
2. Run `generate_integration_health.py` in advisory-only mode for two
   release cycles before flipping enforcement on.
3. The monthly `/schedule` agent uses the same generator; its only
   added work is the diff-and-PR step.
4. Reason-code taxonomy questions are out of scope here. If a `ws-####`
   shorthand was used in a legacy bypass receipt that does not match
   the ADR 0267 catalog, the fix is a one-line patch to the receipt's
   `reason_code` field, governed by ADR 0267 — not by this ADR.
