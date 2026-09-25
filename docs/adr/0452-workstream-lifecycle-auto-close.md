# ADR 0452: Workstream Lifecycle Auto-Close

- Status: Proposed
- Implementation Status: Not started
- Date: 2026-04-28
- Concern: workstream-lifecycle, observability, throughput-measurement
- Tags: workstreams, registry, archive, lifecycle, automation
- Extends: [ADR 0326 — Workstream Registry Shards With Active And Archive Assembly](0326-workstream-registry-shards-with-active-and-archive-assembly.md)
- Related:
  - ADR 0019 (Parallel ADR Delivery With Workstreams)
  - ADR 0420 (CI Release-Readiness Checks) — adds the staleness CI hook
  - ADR 0419 (PR-Based Integration Flow) — the PR is the natural close point

---

## Context

ADR 0326 established the active/archive split for workstream shards:

```
workstreams/active/<workstream-id>.yaml
workstreams/archive/<year>/<workstream-id>.yaml
```

The data layout shipped. The **lifecycle transition** did not. As of
2026-04-28 (v0.179.11):

- `workstreams/active/` contains 21 entries
- `workstreams/archive/` is effectively empty
- Multiple workstreams in `active/` already have live-apply receipts in
  `versions/stack.yaml::live_apply_evidence.latest_receipts` (e.g.
  ws-0414, ws-0417, ws-0438, ws-0444) — they are *done in production*
  but still listed as in-flight

### Why this matters

1. **Throughput is unmeasurable.** A 21:0 active:archive ratio means we
   cannot derive workstream completion rate, mean time to close, or
   in-flight aging — three metrics the integration-health work
   (ADR 0453) needs as inputs.
2. **Coordination surface stays bloated.** ADR 0326's stated goal —
   "active coordination becomes much smaller and easier to inspect" —
   never materialized because nothing moves shards out.
3. **Agent context bloat.** Every agent session (Claude, Codex, Aider,
   Cursor, Devin, human reviewer — anything reading the repo) loads
   the active set; stale entries cost tokens, slow review, and create
   false signals about what is actually open.

The root cause is that ADR 0326 specified the *layout* and a manual
lifecycle rule ("once a workstream reaches a terminal state and any
repo-version bookkeeping is complete, its shard moves to
`workstreams/archive/<year>/`") but provided no automated trigger and
no CI enforcement. In a high-velocity multi-agent repo where many
contributors are LLM sessions, manual lifecycle steps are not done.

---

## Decision

Add three mechanical closures around ADR 0326's existing data layout:

### 1. Lifecycle state as a first-class field

Extend the per-workstream shard schema with:

```yaml
lifecycle_state: active | ready_to_archive | archived
acceptance_criteria_met: <bool>
live_apply_receipt: <slug or null>   # references versions/stack.yaml
```

State machine:

- `active` — work in flight. Default.
- `ready_to_archive` — acceptance criteria satisfied AND a matching
  live-apply receipt exists. Set automatically by the auto-close pass.
- `archived` — shard has moved to `workstreams/archive/<year>/`.

### 2. Auto-close pass in `scripts/workstream_registry.py`

Add a `--archive-completed` flag (idempotent). On invocation:

1. Read every shard in `workstreams/active/`.
2. Cross-reference each shard's `id` against the canonical receipt
   stores defined in §3 below. A workstream is considered
   "deployed" if at least one receipt with matching `ref-id`
   exists in `receipts/live-applies/`.
3. If the shard's `acceptance_criteria_met: true` AND a matching
   receipt exists, transition `active → ready_to_archive`.
4. If `lifecycle_state == ready_to_archive` AND the workstream's most
   recent receipt is older than one full release cycle (one
   `[release]` commit on main after the receipt), move the shard to
   `workstreams/archive/<YYYY>/` and set `archived` state.

The two-phase transition gives one release-cycle window for stragglers
(post-deploy fixes, additional receipts) without reopening the shard.

### 3. Receipt slug convention (formalized)

The cross-reference logic above relies on a slug convention that has
been used by drift since ADR 0036 (live-apply receipts) but is not
formally specified anywhere. This ADR formalizes it.

**Canonical receipt store:** `receipts/live-applies/*.json` (one JSON
file per receipt, conforming to `docs/schema/live-apply-receipt.schema.json`).

**Compatibility surface:** `versions/stack.yaml::live_apply_evidence.latest_receipts`
is a generated index pointing at the most recent receipt per service.

**Slug grammar (required for all new receipts):**

```text
slug         := <iso-date> "-" <ref> "-" <description> "-live-apply"
iso-date     := YYYY-MM-DD
ref          := ref-type "-" ref-id
ref-type     := "adr" | "ws"
ref-id       := /[0-9]{4}/
description  := slug-safe text (lowercase, hyphenated, no underscores)
```

Examples (already conforming):

- `2026-04-28-coolify-0fork-runtime-live-apply` — **non-conforming**
  (missing `ref`); under this ADR, future receipts must include either
  `adr-NNNN` or `ws-NNNN` as the second token
- `2026-04-27-ws-0372-0fork-services-all-7-deployed` — conforming
- `2026-04-21-adr-0373-service-registry-and-derived-defaults-mainline-live-apply` — conforming

**Inside the receipt JSON**, the same `ref` MUST appear in either:

- `workflow_id` (e.g. `"workflow_id": "adr-0267-..."`), OR
- An explicit top-level `workstream_ref` field (new, optional)

This dual-anchor (slug + JSON field) makes the cross-reference
robust against rename or accidental slug truncation.

**Migration:** existing non-conforming receipts (e.g. the
`coolify_runtime` entry above) are grandfathered. The convention is
enforced only on new receipts via a release-readiness check in
ADR 0420.

### 4. CI hook (extends ADR 0420)

Add three checks to the release-readiness CI job:

| Check | What it validates | Fix hint |
|-------|-------------------|----------|
| `workstream-staleness` | No active workstream has been silent in git history for >45 days | "Update or close ws-XXXX (see `make workstream-status ws=XXXX`)" |
| `workstream-receipt-orphan` | No live-apply receipt references a workstream that is still in `active/` (after grace cycle) | "Run `python scripts/workstream_registry.py --archive-completed`" |
| `receipt-slug-conformance` | Every new receipt slug under `receipts/live-applies/` matches the §3 grammar | "Add `adr-NNNN` or `ws-NNNN` token to the receipt slug" |

All three are advisory on non-`[release]` PRs and enforced on
`[release]` PRs.

### 5. Make targets

Add to the merge-to-main protocol (`AGENTS.md` — and the
agent-specific mirror files like `CLAUDE.md` §4a, `.codex/AGENTS.md`,
or any other LLM-frontmatter that agents in this repo read):

```bash
python scripts/workstream_registry.py --archive-completed --write
git add workstreams/
```

This becomes part of the standard release commit, alongside the
existing manifest/discovery/release-notes regeneration. The step is
identical regardless of which agent (or human) authors the release —
no agent-specific configuration.

---

## Consequences

**Positive**

- 21:0 ratio self-corrects without manual intervention
- Throughput becomes a first-class derived metric (input for ADR 0453)
- Coordination surface (`workstreams/active/`) stays small and current
- Agent context bloat reduced — fewer stale shards loaded per session
- Receipt → workstream linkage becomes mechanical instead of implicit

**Negative / Trade-offs**

- One more generator step in the release flow (idempotent, fast)
- Schema extension requires backfill of existing 21 active shards
  (one-time migration, scriptable)
- The "is acceptance criteria met" determination still requires a human
  flag flip on the shard — auto-close cannot infer intent from receipts
  alone. Mitigation: the live-apply receipt commit (which a human
  authors) is the natural place to flip the flag

**Neutral**

- The receipt-slug convention (`<date>-<ws-id>-<description>`) becomes
  load-bearing for the cross-reference. Should be documented as
  intentional (it currently is convention by drift).

---

## Boundaries

- This ADR does not change the ADR 0326 data layout — only adds
  mechanical lifecycle automation on top.
- It does not introduce a new tracking system. Plane integration
  (per ADR 0360) remains the secondary mirror; this ADR concerns the
  authoritative git-side state.
- It does not retroactively reconstruct lifecycle history for the 21
  existing active shards — that is a one-time backfill, separate.
- **Agent neutrality.** The auto-close pass, the schema additions,
  the receipt slug grammar, and the CI checks are agent-invariant.
  Any LLM agent (Claude Code, OpenAI Codex, Aider, Cursor, Devin)
  or human can implement, run, and rely on them. Branch naming and
  worktree path inside individual workstream YAMLs are
  per-contributor conventions and do not affect this ADR's
  contracts.

---

## Implementation Notes

1. Backfill the 21 active shards with `lifecycle_state: active` and
   `acceptance_criteria_met: false` as the safe default.
2. For workstreams with live-apply receipts already in
   `versions/stack.yaml`, set `acceptance_criteria_met: true` and let
   the next `--archive-completed` pass handle the transition.
3. Add a `make workstream-status ws=XXXX` helper that prints the shard,
   matching receipts (if any), and the next required action.
4. Wire `--archive-completed --check` into the release-readiness CI
   alongside the staleness check.
