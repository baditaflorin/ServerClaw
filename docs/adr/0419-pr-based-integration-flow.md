# ADR 0419: Pull Request-Based Integration Flow

**Date:** 2026-04-16
**Status:** Implemented
**Related:** ADR 0418 (Receipt-to-Outline Auto-Publish), ADR 0420 (CI Release-Readiness Checks)

---

## Context

All changes to `main` currently flow through direct push:

```
worktree → commit → git push origin branch:main
```

This workflow developed organically as agent-driven development scaled. It
relies entirely on the pre-push hook (`validate_nats_topics.py`, topology
consistency, SSL certs, ADR status transitions) and the remote gate on the
build server (`scripts/remote_exec.sh pre-push-gate`) to catch problems
before they land on main.

### Problems with direct-push-to-main

1. **No review opportunity.** Changes land on main the instant they pass
   the gate (or bypass it). There is no window to inspect the diff, discuss
   trade-offs, or catch conceptual issues the gate cannot detect.

2. **Gate bypasses are invisible.** When the remote gate fails for
   pre-existing reasons (ansible-lint warnings, stale generated docs),
   the operator sets `SKIP_REMOTE_GATE=1` and the push proceeds. The
   bypass receipt is committed, but nobody reviews the diff before merge.

3. **No diff preview in a web UI.** The full changeset is only visible
   via `git log` after it lands on main. GitHub's PR diff view, file-by-file
   navigation, and inline comments are never used.

4. **No discussion trail.** Architectural decisions embedded in code have
   no natural place for asynchronous review comments. ADRs capture the
   "what" and "why," but there is no lightweight mechanism for "I'd change
   this approach" feedback before code lands.

5. **CI runs after the fact.** The existing GitHub Actions workflow
   (`.github/workflows/validate.yml`) runs on pushes to main, but by then
   the code is already merged. Failures are retroactive, not preventive.

### What already exists

- **GitHub Actions CI** (`.github/workflows/validate.yml`): runs
  `make validate` on PRs and pushes to main. Already functional.
- **PR template** (`.github/pull_request_template.md`): basic checklist
  for type of change and contributor hygiene.
- **Pre-push hook**: 4 local checks + remote gate with local fallback.
- **Gate bypass system**: `log_gate_bypass.py` with waiver receipts,
  formal verification (`verify_waiver_escalation.py`), and Z3 proofs.

The infrastructure for a PR-based flow exists. The missing piece is the
**convention** telling agents and operators to use it, **branch protection**
enforcing it, and an **enhanced PR template** that embeds the release
checklist.

---

## Decision

### 1. All non-emergency changes to main go through pull requests

The default integration path becomes:

```
branch → push branch → create PR → CI passes → merge
```

Agents (Claude Code, Codex, etc.) create a PR via `gh pr create` instead
of pushing directly to `main`. The PR provides:
- A diff preview in the GitHub web UI
- A place for review comments
- CI status checks visible before merge
- A permanent audit trail of what was reviewed and when

### 2. Emergency escape hatch: admin direct push

For genuine emergencies (production outage, security patch), admins can
still push directly to main. Branch protection is configured to allow
admin bypass. The pre-push hook and gate bypass system remain in place
for this path.

This is NOT the normal flow. Any direct push should be followed by a
retroactive PR or incident note explaining why the normal flow was skipped.

### 3. Branch protection rules (when available)

GitHub branch protection requires GitHub Pro for private repos. While
the repo remains private on GitHub Free, the PR convention is enforced
by agent instructions (CLAUDE.md, AGENTS.md) and social contract only.

When GitHub Pro is available (or the repo goes public via ServerClaw),
configure branch protection:

| Setting | Value | Rationale |
|---------|-------|-----------|
| Require pull request before merging | Yes | Enforce PR flow |
| Required approvals | 0 (initially) | Solo operator; increase when team grows |
| Require status checks to pass | Yes | CI must pass before merge |
| Required status check: `validate` | Yes | The existing CI job name |
| Require branches to be up to date | No | Avoids rebase churn on fast-moving main |
| Allow force pushes | No | Protect history |
| Allow deletions | No | Protect main |
| Allow admin bypass | Yes | Emergency escape hatch |

Until then, the pre-push hook continues to enforce local validation on
any direct pushes, and the PR workflow is the documented convention.

### 4. Enhanced PR template

Replace the current basic template with a comprehensive one that embeds
the merge-to-main release checklist. This eliminates the need to remember
the checklist from `CLAUDE.md` — it's right there in the PR body.

### 5. Update agent instructions

Update `CLAUDE.md` section 4 ("Merge-to-Main Checklist") to use the PR
flow. Update `AGENTS.md` to document the convention.

### 6. Agent workflow: PR creation

Claude Code and other agents follow this sequence:

```bash
# 1. Push the working branch
git push origin claude/my-branch -u

# 2. Create PR
gh pr create --base main \
  --title "[release] Bump to X.Y.Z — summary" \
  --body "$(cat <<'EOF'
## Summary
- bullet points

## Release checklist
- [x] VERSION bumped
- [x] changelog.md updated
- [x] Release notes generated
- [x] Platform manifest regenerated
- [x] Discovery artifacts regenerated
EOF
)"

# 3. Wait for CI (optional — can check with gh pr checks)
gh pr checks <number> --watch

# 4. Merge (squash for clean history)
gh pr merge <number> --squash --delete-branch

# 5. Or merge with full commit history
gh pr merge <number> --merge --delete-branch
```

---

## Consequences

### Positive

- Every change to main has a reviewable diff in GitHub's web UI
- CI runs before merge, not after — failures are preventive
- Gate bypasses are visible in the PR conversation, not just in receipt files
- Permanent audit trail: who merged what, when, with what CI status
- PR comments provide a lightweight review mechanism
- The release checklist is embedded in the PR template — harder to forget

### Negative / Trade-offs

- Slightly more steps for agents (push branch + create PR + merge vs. push to main)
- Solo operator sees no benefit from "required approvals" — set to 0 initially
- Emergency direct pushes are still possible but require admin bypass

### Not in scope

- Multi-reviewer approval workflow (not needed for solo operator)
- Auto-merge on CI pass (can be added later via GitHub settings)
- PR-based release automation (covered in ADR 0420)

---

## Implementation Checklist

- [x] Write this ADR
- [ ] Configure branch protection rules via `gh` CLI (requires GitHub Pro for private repos)
- [x] Enhance `.github/pull_request_template.md` with release checklist
- [x] Update `CLAUDE.md` section 4 to use PR-based flow
- [x] Update `AGENTS.md` with PR workflow convention
- [x] Document emergency direct-push procedure

---

## Artifacts

| Artifact | Path |
|----------|------|
| This ADR | `docs/adr/0419-pr-based-integration-flow.md` |
| PR template | `.github/pull_request_template.md` |
| CI workflow | `.github/workflows/validate.yml` |
| Agent instructions | `CLAUDE.md` section 4 |
