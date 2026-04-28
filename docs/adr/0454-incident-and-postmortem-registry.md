# ADR 0454: Incident & Postmortem Registry

- Status: Proposed
- Implementation Status: Not started
- Date: 2026-04-28
- Concern: documentation, audit-trail, postmortem-discipline, agent-memory-bridge
- Tags: incidents, postmortems, registry, index, governance
- Related:
  - ADR 0114 (Rule-Based Incident Triage Engine) — runtime alerting; complementary
  - ADR 0382 (Keycloak Sign-In Button Stuck — Postmortem)
  - ADR 0415 (Postmortem: Cert Mismatch Gate Forced No-Verify)
  - ADR 0420 (CI Release-Readiness Checks) — adds the index-staleness check
  - ADR 0453 (Integration-Health Telemetry) — auto-populates `bypasses/`

---

## Context

The repo currently handles postmortems in three inconsistent places:

1. **As ADRs** — `0382-keycloak-sign-in-button-stuck-postmortem.md`,
   `0415-postmortem-cert-mismatch-gate-forced-no-verify.md`. Two in
   the last 90 days. Discoverable via the ADR index.
2. **As agent-side ephemeral notes** — placeholder-IP lockout
   (2026-04-12), OpenBao credential drift (2026-04-12), Grist OIDC
   restart (2026-04-05), and others live as agent-private files
   (Claude memory under `~/.claude/.../memory/`, Codex session notes,
   Aider chat history, operator scratchpads). They exist but the
   repo has no record.
3. **Implicitly, in commit messages and release notes** — "fix" and
   "revert" commits often describe incidents in the body, with no
   structured pointer.

ADR 0114 covers *runtime triage* (alerts → response). It does not
cover *documentation* — the audit trail of what broke, what we did,
and what we changed.

### Why this matters

1. **Audit trail gaps.** When an incident recurs, we cannot answer
   "did this happen before?" without searching every agent's private
   notes and the git history simultaneously. The placeholder-IP
   lockout is a known incident (one agent has a note about it) but
   is invisible to every other agent and to anyone working only
   from the repo.
2. **Postmortem discipline is uneven.** Big incidents get ADRs.
   Smaller incidents (Grist OIDC, OpenBao drift) get agent-side
   notes only. The threshold for "ADR-worthy" is undefined, so
   smaller incidents go undocumented in the repo.
3. **ADR 0453's bypass governance** auto-creates stubs at
   `docs/incidents/bypasses/`. That directory needs a parent
   structure and an index for those stubs to integrate with.
4. **Cross-agent context bridge.** Agent-private notes persist for
   one agent and one session-history; they do not transfer to other
   agents (Claude → Codex → Aider → human reviewer) or to future
   operators. The repo is the only durable, agent-neutral record.

---

## Decision

### 1. Directory layout (mirrors `docs/adr/` pattern)

```
docs/incidents/
  .index.yaml                # generated
  schema.json                # frontmatter schema
  postmortems/
    YYYY-MM-DD-<short-slug>.md
  bypasses/                  # auto-populated by ADR 0453
    YYYY-MM-DD-<reason>-<sha>.md
  references/
    <pointer>.yaml           # cross-references to postmortem ADRs
```

### 2. Required frontmatter

```yaml
---
id: incident-2026-04-12-placeholder-ip-lockout
date: 2026-04-12
severity: high            # low | medium | high | critical
status: resolved          # open | mitigated | resolved
services:                 # affected services or surfaces
  - networking
  - tailscale
related_adrs:
  - 0438                  # generic-by-construction
related_workstreams: []
duration_minutes: 360
detection: alert          # alert | user-report | self
---
```

### 3. Cross-reference, do not duplicate

Postmortem ADRs (0382, 0415, future) **stay in `docs/adr/`**. The
incident index references them via a `references/` pointer YAML:

```yaml
# docs/incidents/references/adr-0415.yaml
type: postmortem-adr
adr: 0415
incident_id: incident-2026-03-29-cert-mismatch-gate-no-verify
```

This keeps the ADR index authoritative for ADRs and the incident
index authoritative for "everything we learned the hard way",
without duplicating content.

### 4. Generator and CI hook

`scripts/generate_incident_index.py --write` produces
`docs/incidents/.index.yaml`, mirroring the structure of
`docs/adr/.index.yaml`. Runs in:

- The merge-to-main checklist (CLAUDE.md §4a)
- The release-readiness CI job (ADR 0420), with a fix hint
  pointing back to this ADR

A `--check` mode fails CI when the index is stale.

### 5. Bootstrap from agent-private notes

A one-time, agent-agnostic migration helper reads from any of the
following sources (whichever the operator/agent points it at) and
creates initial postmortem files in `docs/incidents/postmortems/`
with a `migrated_from: <source-tag>` flag:

| Source | Path pattern | Example tag |
|--------|--------------|-------------|
| Claude Code memory | `~/.claude/projects/.../memory/postmortem_*.md` | `claude-memory` |
| Codex session notes | `.codex/notes/*.md` or wherever the running Codex agent stages notes | `codex-notes` |
| Aider chat history | `.aider.chat.history.md` excerpts | `aider-history` |
| Operator scratchpads | Any local notes file the operator points at | `operator-notes` |
| Generic markdown | Any file the migration helper is told to ingest | `manual` |

The helper itself is agent-neutral: it accepts paths via CLI flags
(`--from <path>`) and an optional `--source-tag <label>`. Different
agents can run it pointing at their own private stores; the output
is the same canonical `docs/incidents/postmortems/<slug>.md` file
plus a `migrated_from: <tag>` provenance field.

Three known candidates as of 2026-04-28 (all currently in
Claude-side memory, but the migration mechanism does not assume any
agent):

- 2026-04-12 placeholder-IP lockout (RFC 5737 incident)
- 2026-04-12 OpenBao credential drift (Gitea start failure)
- 2026-04-05 Grist OIDC stale container restart

After migration, these become durable repo records readable by every
agent and human; the original agent-private notes can be retired or
kept as session-local working notes.

### 6. Pre-push hook integration

Any commit message containing `incident:` or `postmortem:` (case
insensitive) requires the same commit to add or update an incident
file. Mirrors the existing convention that ADR-changing commits must
include the ADR file. Implemented as a pre-push validation.

### 7. Severity gate (light-touch)

Severity `high` or `critical` incidents must produce a postmortem
ADR within 14 days of the incident date. The release-readiness CI
job warns when this is overdue. Severity `low` and `medium`
incidents only need the postmortem markdown — no ADR escalation
required. This codifies the threshold for "ADR-worthy" that today
is implicit.

---

## Consequences

**Positive**

- Single queryable surface for the incident history of the platform
- Bypass governance from ADR 0453 has a structured home
- The ADR threshold for postmortems becomes explicit
  (severity-driven), not vibes-driven
- Incidents captured by any contributor (Claude, Codex, Aider,
  Cursor, Devin, human operator) become repo-durable and reviewable
  by all the others
- Future agents and reviewers can answer "has this happened before?"
  with a grep over `docs/incidents/`, no agent-private store needed

**Negative / Trade-offs**

- New directory structure to maintain — though it mirrors a pattern
  the repo already has (ADR index)
- One more generator in the release flow
- Pre-push hook validation could fire on false positives
  (commit message mentions "incident" in a non-incident sense).
  Mitigation: scope the trigger to specific prefixes
  (`incident:`, `postmortem:`) rather than substring match.

**Neutral**

- Migration of 3 memory files is a one-time cost. Future memory
  files for incidents flow naturally to the repo via the pre-push
  hook.

---

## Boundaries

- This ADR is **not** a runtime alerting system. ADR 0114 owns that.
- It is **not** a replacement for the ADR system. ADRs remain the
  durable record for *decisions*; this is the durable record for
  *incidents*. Postmortem ADRs remain in `docs/adr/` and are
  referenced from here.
- It is **not** a ticket tracker. Plane (per ADR 0360) handles
  in-flight incident response coordination; this is the post-hoc
  audit trail.
- **Agent neutrality.** The directory layout, schema, generator,
  bootstrap migration helper (`--from <path> --source-tag <label>`),
  and pre-push hook are agent-invariant. Incidents captured by any
  contributor — Claude Code, OpenAI Codex, Aider, Cursor, Devin,
  human operator — flow into the same canonical artifacts. No agent
  has privileged write access; no agent's notes are second-class.

---

## Implementation Notes

1. Schema for `docs/incidents/schema.json` modeled directly on
   `docs/adr/schema.json` to reuse generator scaffolding.
2. The bootstrap migration script ships behind a one-time
   `--migrate-from-memory` flag, runs once, then is deleted.
3. Severity assignment is the operator's call at incident creation
   time; the 14-day ADR-escalation deadline is computed from the
   incident date, not the file creation date.
4. The bypass stubs created by ADR 0453 use severity `low` by
   default. Operator can upgrade severity if the bypass turned out
   to mask a real incident.
5. CI integration is identical to the existing ADR-index check,
   sharing infrastructure where possible.
