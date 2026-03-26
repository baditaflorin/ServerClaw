# ADR 0167: Agent Handoff and Context Preservation Protocol

- Status: Proposed
- Implementation Status: Proposed
- Date: 2026-03-26

## Context

This repository is designed to be worked on by different LLM agents in sequence. AGENTS.md explicitly states:

> "Work as if another assistant will continue after you. Leave the repo in a state where another assistant can continue without hidden context."

Currently, agents can leave incomplete context when:

- Making changes on a branch without documenting next steps
- Failing to update workstreams.yaml when status changes
- Leaving uncommitted work in a worktree without clear state
- Not documenting blockers or decisions made
- Updating VERSION or configuration without explaining why
- Creating new playbooks without metadata (ADR 0165)
- Making deployment changes without receipts or documentation

This creates friction for the next agent:

- They must reconstruct context from git history
- They don't know what was attempted, blocked, or completed
- They risk duplicating work or undoing intentional changes
- They waste tokens understanding incomplete decisions

A clear **agent handoff protocol** would ensure:

- The next agent can understand what happened and what remains
- Work state is explicit (in progress, blocked, complete)
- Decisions are documented in ADRs, not hidden in chat
- Changes are committed with clear messages
- All configuration changes have explainable rationale

## Decision

All agents working on this repository must follow this **handoff protocol**:

### 1. Work Within a Git Worktree

**Start your session with:**

```bash
git worktree add .claude/worktrees/[agent-name] main
cd .claude/worktrees/[agent-name]
git checkout -b [agent-name]/[task-name]
```

**This ensures:**
- Your work is isolated from other agents
- Your branch is clearly named with your task
- Main branch stays clean for other agents

### 2. Document Work in Workstreams

**Update `workstreams.yaml` immediately when starting:**

```yaml
workstreams:
  - name: "example-feature"
    branch: "my-agent/example-feature"
    assignee: "Claude"
    status: "in-progress"
    adr_reference: "docs/workstreams/adr-0200-example-feature.md"
    started_at: 2026-03-26
    notes: |
      - Implementing feature X
      - Blocked on decision Y (see ADR draft)
      - Next: Complete deployment validation
```

**Update status field:**
- `in-progress`: Work is actively happening
- `blocked`: Work is waiting on something external
- `review-ready`: Code review needed before merge
- `complete`: Ready to merge to main

### 3. Document Decisions in ADRs or Workstream ADRs

**For major decisions, create a workstream ADR:**

```bash
# Create docs/workstreams/adr-0200-example-feature.md
# Use standard ADR format (Context, Decision, Consequences, Boundaries)
# Link back from workstreams.yaml
```

**For smaller decisions, document in commit messages:**

```bash
git commit -m "Implement feature X

- Decision: Use approach A instead of B because C
- Trade-off: Slightly more code, but more maintainable
- Tested: Local validation passes
- Blockers: None"
```

### 4. Leave Clear Status at Session End

**Before committing, update README.md if infrastructure state changed:**

```markdown
## Current Status

[Update this section with what you accomplished]

- Completed: Feature X
- Blockers: Y (waiting for Z)
- Next: Deploy to staging

Last updated: 2026-03-26
Last agent: Claude
```

**Keep README focused on:**
- What's deployed and working
- What's in progress
- What's blocked and why
- What the next agent should do

### 5. Commit Work Frequently

**Commit messages must explain:**

```bash
git commit -m "Add playbook for X

Purpose:
  Automate X task to reduce manual effort

Scope:
  - Created playbooks/x.yml
  - Added roles/x_handler
  - Tested on staging

Status:
  - Ready for merge to main
  - Next: Deploy to production when Y is ready

See also: ADR 0XXX (decision rationale)"
```

**Minimum commit message template:**

```
[area] Short description

Purpose: Why this change matters
Scope: What files changed and why
Status: Current implementation state
Next: What comes after this
See also: Related ADRs or runbooks
```

### 6. Record Deployment Changes

**Every deployment or infrastructure change must create a receipt:**

```yaml
# receipts/2026-03-26-feature-x-deployment.yaml
date: 2026-03-26T14:30:00Z
agent: Claude
change: Deployed feature X
scope:
  - Modified: playbooks/site.yml
  - Created: roles/feature_x
  - Updated: versions/stack.yaml
verification:
  - Validation passed: make validate-data-models
  - Tests passed: pytest tests/integration/
  - Deployed to: staging
  - Verified: Feature works as expected
blockers: null
next_steps:
  - Deploy to production when Y is ready
  - Monitor deployment metrics
  - Notify team of change
```

### 7. Don't Leave Uncommitted Work

**Before ending your session:**

```bash
# Check what's uncommitted
git status

# Commit everything or document why it's not ready
git add -A
git commit -m "WIP: Feature X in progress"

# If not mergeable, clearly document blockers
# Update workstreams.yaml with status: blocked
# Push your branch so the next agent can see it
git push -u origin $(git branch --show-current)
```

### 8. Update Metadata Standards

**When creating new playbooks or roles:**

- Add metadata header per ADR 0165 (Playbook/Role Metadata Standard)
- Include Purpose, Inputs, Outputs, Dependencies
- Document in README.md alongside code
- Link to related ADRs

**Example:**

```yaml
---
# Role: example_role
# Purpose: Do something important
# Inputs: [list variables needed]
# Outputs: [what changes]
# Dependencies: [what must run first]
# See also: ADR 0XYZ
---
```

### 9. Handle Blockers Explicitly

**If you encounter a blocker, document it:**

```yaml
# In workstreams.yaml
status: blocked
blocker:
  description: "Can't proceed because X depends on Y"
  depends_on: "other-agent/other-task branch"
  estimated_unblock: "2026-03-27"
  notes: "Waiting for other workstream to complete"

# Or in the ADR draft
## Blockers

- **Blocked on ADR review**: Decision needed on approach A vs B
- **Blocked on infrastructure**: Waiting for storage provisioning
- **Blocked on dependencies**: Waiting for other-agent/task branch
```

### 10. Merge to Main Only When Complete

**Before merging to main:**

```bash
# Ensure your branch is clean
git status  # Should show nothing to commit

# Update VERSION only when merging (not during branch work)
# ADR 0008 says: bump VERSION when merging to main

# Create a clean commit message for merge
git commit --allow-empty -m "Merge workstream: example-feature

Completed:
  - Feature X implementation
  - Tests passing
  - Documentation updated

Status:
  - Ready for production
  - Deployed to staging, verified working
  - No blockers

See also: docs/workstreams/adr-0200-example-feature.md"

# Merge to main
git checkout main
git pull origin main
git merge --no-ff [your-branch]
```

### 11. Update Shared Files Carefully

**Protected files that should only be changed during integration:**

- `VERSION`: Only bump when merging to main (ADR 0008)
- `changelog.md`: Update with release notes when VERSION changes
- `versions/stack.yaml`: Canonical truth for deployed services
- `README.md` status sections: Only when merged to main
- `workstreams.yaml`: Update your entry before pushing

**Pattern for changes to protected files:**

```bash
# Don't modify on branch
# Instead, create a clean commit when merging:

git checkout main
git pull origin main

# Make the change
echo "0.123.0" > VERSION

# Commit clearly
git commit -m "Bump version for release 0.123.0

Changes included:
  - Feature X from branch-a
  - Feature Y from branch-b
  - Security patch from branch-c

See: changelog.md for detailed notes"
```

### 12. Document Lessons Learned

**If you discover something important, add it to AGENTS.md:**

```markdown
## Lessons Learned

- Lesson: X approach doesn't work because of Y (discovered 2026-03-26)
- Workaround: Do Z instead
- Reference: ADR 0XYZ
```

### Handoff Checklist

When ending your session, verify:

- [ ] Current branch has all work committed
- [ ] `workstreams.yaml` updated with current status
- [ ] README.md updated if infrastructure state changed
- [ ] If merged to main: VERSION bumped, changelog updated
- [ ] New playbooks/roles have metadata headers (ADR 0165)
- [ ] Any blockers documented in workstreams.yaml or ADR draft
- [ ] Next steps documented (in ADR, workstreams.yaml, or README)
- [ ] Branch pushed to origin (git push -u origin branch-name)
- [ ] No uncommitted work left

### Quick Reference for Agents

| Situation | Action |
|---|---|
| Starting new work | Create branch `[agent-name]/[task]`, add to workstreams.yaml |
| Making a change | Commit with purpose/scope/status/next |
| Infrastructure change | Create receipt in receipts/ |
| Major decision | Create ADR in docs/workstreams/ |
| Merging to main | Bump VERSION, update changelog, clear commit message |
| Work incomplete | Mark status: blocked, document blocker, push branch |
| Deploying | Create receipt, verify tests, document next steps |

## Consequences

**Positive**

- Next agent can understand work in 1-2 minutes instead of 30 minutes
- Decisions are recorded, not hidden in chat
- Work state is explicit (in progress, blocked, complete, merged)
- Reduces duplicate work and prevents conflicting changes
- Enables better parallelization of workstreams
- Creates a clear audit trail of changes

**Negative / Trade-offs**

- Requires discipline to document before committing
- Initial sessions may be slower due to documentation overhead
- Some redundancy between commits, ADRs, and workstreams.yaml

## Boundaries

- This protocol applies to all agents working on this repository
- Applies to all branches, not just main
- Does not replace code review - human review should happen before merge
- Documentation overhead is worth the context preservation benefit

## Implementation

This protocol is effective immediately. Agents should:

1. Use git worktrees for all work (already in AGENTS.md)
2. Follow commit message format above
3. Update workstreams.yaml at start and end
4. Create workstream ADRs for major decisions
5. Keep README.md and receipts/ current

## Related ADRs

- ADR 0163: Repository structure index
- ADR 0164: ADR metadata index
- ADR 0165: Playbook/role metadata standard
- ADR 0166: Configuration locations registry
- Original AGENTS.md: Agent working rules

## Agent Instructions

Before starting work:
1. Read AGENTS.md
2. Read ADRs 0163-0167 (this series)
3. Use .repo-structure.yaml to orient yourself
4. Check workstreams.yaml to see what's in progress
5. Use .config-locations.yaml to find specific files
6. Create a workstream entry and branch for your work

When you finish:
1. Commit your work with clear messages
2. Update workstreams.yaml
3. Push your branch
4. Document blockers or next steps
5. If merged to main, bump VERSION and update changelog
