# Postmortem: Agent Orientation Overhead — Receipt-to-Outline Investigation (2026-04-15)

**Date:** 2026-04-15
**Duration:** ~12 minutes of exploration before any code was written
**Severity:** Informational — no production impact
**Status:** Resolved; recommendations captured in ADR 0418

---

## Summary

An operator asked a single question: "We have receipt file `20260328T232409Z.json` —
can we auto-upload it to Outline? What scripts do this?"

The answer is: **yes, `subdomain_exposure_audit.py` already does this** via
`_publish_receipt_to_outline()` triggered by `--write-receipt`. The specific
receipt linked in the operator message was already live at
`https://wiki.example.com/doc/20260328t232409z-...`.

However, answering that question required the following exploration steps:
a broad codebase survey, multiple targeted greps, worktree setup to
inspect `origin/main`, and ADR number allocation. This postmortem documents
the overhead and proposes concrete improvements so future agents — or future
sessions of this agent — can answer equivalent questions in a single tool call.

---

## Timeline

| Step | Tool(s) used | Time cost | What was learned |
|------|-------------|-----------|-----------------|
| Initial broad survey | `Agent(Explore)` delegated to subagent | ~3 min (subagent) | Outline scripts exist: `outline_tool.py`, `outline_client.py`, `sync_docs_to_outline.py`. Receipt directories and formats. Existing `_publish_receipt_to_outline` pattern in 9 scripts. ADR index. |
| Check highest ADR on current branch | `adr_query_tool.py allocate` | 10 sec | Next available: 0413/0414 on current branch |
| Confirm subdomain audit already auto-publishes | Grep on `subdomain_exposure_audit.py` | 5 sec | Already calls `_publish_receipt_to_outline` at line 1107 |
| Check other scripts' auto-publish coverage | Grep on `scripts/*.py` | 5 sec | 9 scripts have it, ~30 do not |
| Read existing ADR format for template | `Read` on 0411/0412 | 10 sec | — |
| Read postmortem format | `Read` on 2026-04-13 postmortem | 10 sec | — |
| Create worktree at origin/main | `git worktree add` | 30 sec | origin/main is at v0.178.145, not 0.178.128; ADRs up to 0417 exist |
| Confirm ADR numbers on main | `adr_query_tool.py allocate` in worktree | 5 sec | Next available on main: 0418/0419 |
| **Total** | | **~12 min** | |

The ~3-minute delegated subagent represented ~75% of total exploration time.
Without it, the initial survey would have required 10–15 individual tool calls.

---

## What Worked Well

1. **`adr_query_tool.py allocate`** — fast, authoritative, and collision-safe for
   ADR number allocation. The right tool; no issues.
2. **Existing receipt infrastructure is solid** — `outline_tool.py` has
   `receipt.publish` and `receipt.backfill` commands with `_infer_collection_from_path`
   auto-detection. The pattern is well-built once you find it.
3. **Git worktree** let me inspect `origin/main` state without disturbing the
   current working directory (which had many uncommitted changes that blocked branch checkout).

---

## Root Causes of Orientation Overhead

### R1 — `outline_tool.py` not mentioned in `AGENTS.md`

`AGENTS.md` documents receipts (line 348: "Receipts created in `receipts/live-applies/`")
but never mentions `scripts/outline_tool.py` or `scripts/outline_client.py`.
An agent arriving at a task involving Outline or receipts must discover these
tools through search.

**Cost:** 1 subagent invocation (~3 min).
**Fix:** Add "Programmatic Wiki Tools" section to `AGENTS.md`.

### R2 — `_publish_receipt_to_outline` is copy-pasted, not discoverable as a convention

The auto-publish pattern exists in 9 scripts as a private `_publish_receipt_to_outline`
function. It is not named in any doc, not exported from any module, and not listed
in `.repo-structure.yaml` or the platform manifest. An agent cannot learn
"auto-publish after writing receipts is the convention" without reading multiple
scripts.

**Cost:** 2 grep calls + reading code.
**Fix:** Extract to `outline_client.publish_receipt_to_outline()` (ADR 0418 Step 1).
Once it's a named export, it appears in imports, which makes it discoverable.

### R3 — VERSION on current working branch was 0.178.128, not reflecting origin/main (0.178.145)

The current branch diverged significantly from main. `cat VERSION` returned
`0.178.128`, but `origin/main` was at `0.178.145`. This created confusion
about what ADR numbers were valid: the allocation tool returned 0413/0414
on the branch but 0418/0419 on main.

**Cost:** 15 seconds of confusion + needing a worktree to verify.
**Fix:** At session start, always verify against `origin/main` version, not just
the local HEAD. A one-liner in CLAUDE.md session-start checklist:
```bash
git fetch origin main --quiet && cat <(git show origin/main:VERSION)
```

### R4 — No "script capability index" to answer "does script X auto-publish?"

There is no document or manifest entry listing "which scripts auto-publish
receipts." To answer this, an agent must grep all Python scripts — which works
but burns context.

**Cost:** 1 grep call (cheap but illustrative).
**Fix:** `build/platform-manifest.json` should have a `scripts` section listing
each automation script with its key flags (e.g. `receipt_auto_publish: true`).
Or a lighter option: add a comment header block to each script in the form
`# AUTO-PUBLISH: yes` that can be grepped in one call.

---

## Recommendations

| ID | Recommendation | Owner | ADR |
|----|---------------|-------|-----|
| PM-1 | Add "Programmatic Wiki Tools" section to `AGENTS.md` covering `outline_tool.py`, `outline_client.py`, and the receipt auto-publish convention | Platform | ADR 0418 Step 5 |
| PM-2 | Extract `_publish_receipt_to_outline` to `outline_client.publish_receipt_to_outline()` | Platform | ADR 0418 Step 1 |
| PM-3 | Add `# AUTO-PUBLISH: yes|no` header comment to all receipt-generating scripts | Platform | ADR 0418 Step 3 |
| PM-4 | Add `git show origin/main:VERSION` to the CLAUDE.md session-start check | Platform | — |
| PM-5 | Add a `scripts/` section to `build/platform-manifest.json` with receipt-publish coverage per script | Platform | ADR 0418 follow-up |

---

## Token Efficiency Analysis

This task had an objective answer ("the subdomain audit script already
auto-publishes; ~30 other scripts do not; next ADR is 0418") that required
exploring ~2,000 lines of code across 10+ files to establish.

**Would have been instant if:**
- `AGENTS.md` said: `scripts/outline_tool.py receipt.publish <file>` publishes any receipt to Outline
- `AGENTS.md` said: scripts with auto-publish import `publish_receipt_to_outline` from `outline_client`
- `CLAUDE.md` said: verify `origin/main` VERSION before allocating ADR numbers on diverged branches

**Estimated reduction:** from 12 minutes / ~1 subagent invocation to
~30 seconds / 2 direct grep calls.

---

## Action Items

- [ ] Implement ADR 0418 (shared utility + coverage gap scripts)
- [ ] Add PM-1: `AGENTS.md` "Programmatic Wiki Tools" section
- [ ] Add PM-4: `CLAUDE.md` session-start origin/main VERSION check
- [ ] Run `receipt.backfill` for collections missing historical receipts
