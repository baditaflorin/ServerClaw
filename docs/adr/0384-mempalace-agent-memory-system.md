# ADR 0384: MemPalace Agent Memory System Integration

- **Status:** Proposed
- **Implementation Status:** Scoping
- **Date:** 2026-04-08
- **Author:** Claude Agent

## Context

The proxmox_florin_server platform is a complex infrastructure-as-code system with:

- **73 Ansible roles** managing 50+ services across multiple VMs
- **383 ADRs** documenting decisions, tradeoffs, and implementation details
- **Multiple agents** (architecture, operations, testing) working across sessions
- **Session-scoped memory loss** — each Claude Code session starts fresh, losing context about:
  - Why certain architectural decisions were made (beyond what's written in ADRs)
  - Failed deployment attempts and the root causes discovered
  - Ongoing investigations and debugging sessions
  - Technical details learned during convergence runs
  - Cross-session progress on multi-phase migrations (e.g., ADR 0373 role registry)

### Current Problem

When an agent completes a session of work:

1. **Technical context evaporates** — Why did we skip this validation check? What did we try that failed?
2. **Decision rationale is incomplete** — ADRs capture decisions but not the reasoning process or rejected alternatives
3. **Debugging knowledge is lost** — Hours spent understanding a timeout or bootstrap failure aren't available to the next agent
4. **Cross-service insights disappear** — Patterns noticed in one service (e.g., OpenBao agent config, Jinja2 template issues) aren't readily accessible across the codebase
5. **Workstream continuity is fragile** — Multi-phase projects (ADR 0373: 5 of 73 roles migrated) must be re-contextualized from git history alone

Example: Session 12 discovered that `derive_service_defaults` works for Docker app services but not system packages (9 Group B roles out-of-scope). This insight should be immediately available to the next agent, not buried in git commit messages.

### Why MemPalace

MemPalace is a local, open-source memory system designed for exactly this problem:

- **96.6% LongMemEval recall** — highest published benchmark for session-to-session memory
- **Zero API calls** — runs entirely locally on the machine, no cloud dependency
- **Structural memory** (wings, rooms, halls) — organizes memories by person, project, and decision type
- **Raw verbatim storage** — every decision, debugging note, and architectural debate is preserved without summarization loss
- **19 MCP tools** — integrates with Claude Code via plugin or MCP server
- **Auto-save hooks** — can capture memories automatically during work
- **Specialist agents** — different agents (reviewer, architect, ops) maintain focused memories

This is particularly valuable for a codebase with:
- Complex architectural decisions requiring narrative context
- Long-running convergence sessions with technical insights
- Cross-session migrations and refactors
- Multiple specialized roles (infrastructure, deployment, security)

## Decision

Integrate MemPalace as the primary **agent cross-session memory system** for the proxmox_florin_server platform.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Session N (Claude Agent)                                  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ Work: Implement ADR 0373 Phase 4                     │ │
│  │                                                      │ │
│  │  1. Read MEMORY.md (loads 170 tokens of context)   │ │
│  │  2. Work on roles/dify_runtime, roles/directus...  │ │
│  │  3. Discover pattern: all PostgreSQL roles need X  │ │
│  │  4. Tests pass, merge to main                      │ │
│  │  5. Auto-save hook captures:                       │ │
│  │     - Decision: skip roles marked Group B          │ │
│  │     - Pattern: postgres role standardization       │ │
│  │     - Technical: CTmpl macro parameters work X way │ │
│  │     - Milestone: Phase 4 complete, 45/73 done     │ │
│  └──────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
           │
           ▼
    MemPalace Palace
    (~/.mempalace/)
           │
           ├─ wing_proxmox_florin/
           │  ├─ hall_facts/
           │  │  └─ adr_0373_role_registry (temporal KG facts)
           │  ├─ hall_events/
           │  │  └─ session_12_completion
           │  ├─ hall_discoveries/
           │  │  └─ postgres_role_pattern
           │  └─ hall_decisions/
           │     └─ group_b_skip_rationale
           │
           ├─ wing_claude_ops/
           │  ├─ hall_facts/
           │  │  └─ team_preferences
           │  └─ hall_advice/
           │     └─ debugging_patterns
           │
           └─ knowledge_graph/ (SQLite)
              └─ temporal entity facts
                 (who did what, when, status)

┌─────────────────────────────────────────────────────────────┐
│  Session N+1 (Claude Agent) — One week later               │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ Work: Continue ADR 0373 Phase 5                      │ │
│  │                                                      │ │
│  │  1. Claude loads MEMORY.md at session start          │ │
│  │     → "Phase 4 complete, 45/73 done"               │ │
│  │     → "Group B roles (9) out-of-scope, why: ..."   │ │
│  │     → "Postgres pattern: [details]"                │ │
│  │                                                      │ │
│  │  2. Search MemPalace: "postgres role pattern"       │ │
│  │     → Found discovery from Session 12              │ │
│  │     → Technical details and code examples available │ │
│  │                                                      │ │
│  │  3. Continue Phase 5 with full context              │ │
│  │     (no re-learning, no false starts)              │ │
│  └──────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Integration Points

#### 1. Claude Code Plugin (Recommended)

Install MemPalace as a Claude Code plugin:

```bash
claude plugin install mempalace --scope user
```

This gives Claude Code access to:
- `mempalace_search` — find previous decisions and debugging notes
- `mempalace_add_drawer` — save technical discoveries and patterns
- `mempalace_kg_query` — check what was decided and by whom
- `mempalace_wake_up` — load critical facts at session start

**Usage in this codebase:**

```
Session start:
  1. Read CLAUDE.md (project rules)
  2. Load memory: mempalace wake_up --wing proxmox_florin
  3. Establish context: last session completed Phase X, here's what was learned

During work:
  - Hit an issue? Search for similar debugging:
    mempalace_search "convergence timeout keycloak"
  - Discover a pattern?
    mempalace_add_drawer "postgres role standardization pattern"

Session end:
  - Auto-save hook captures session discoveries (15-message interval)
```

#### 2. Specialist Agent Memories

Create focused memories for each agent archetype in `~/.mempalace/agents/`:

**reviewer.json** — Code quality and pattern detection
- Stores recurring bug patterns (e.g., "3rd time this quarter: middleware validation skipped")
- Tracks refactoring candidates and technical debt
- Records which patterns are context-specific vs. platform-wide

**architect.json** — Design decisions and tradeoffs
- Each ADR is filed with its decision narrative, not just the final choice
- Rejected alternatives and why they failed
- Cross-service architectural patterns (e.g., OpenBao agent config idioms)

**ops.json** — Deployment incidents and debugging
- Every failed convergence and its root cause
- Timeout thresholds discovered empirically
- Service-specific quirks (e.g., Keycloak reconciliation timeout needs investigation)
- Which VMs are unreachable and when (e.g., 10.10.10.92 unreachable during Session 7)

**Example ops diary:**

```yaml
Session 7:
  - host_10_10_10_92_unreachable: "Blocks direct debugging; root cause undetermined"
  - keycloak_timeout_issue: "Outline reconciliation → admin token refresh fails after 24 retries"
  - root_cause: "Keycloak API overload during token refresh window"

Session 8:
  - keycloak_fix_applied: "Made reconciliation optional via keycloak_reconcile_outline_users flag"
  - validation: "Convergence proceeded past timeout; 346 tasks succeeded"
```

#### 3. ADR Corpus Integration

Link MemPalace with existing ADRs:

- **ADR discovery room** (`wing_proxmox_florin / hall_decisions / adr_NNNN_slug`)
- When an ADR is implemented, capture:
  - Rejected alternatives and why (not always in the written ADR)
  - Debugging sessions that led to the decision
  - Cross-ADR dependencies discovered during implementation
  - Temporal facts (when decision was made, when implemented, by whom)

Example:

```
Fact: ADR 0373 (role registry) Phase 1
  - Author: Claude agent (Session 12)
  - Status: 5 of 73 roles migrated (Gitea, Keycloak, Woodpecker, Coolify, Flagsmith)
  - Discovery: derive_service_defaults pattern works for Docker services only
  - Out-of-scope: 9 Group B roles (system packages, special infra)
  - Next phase: Phase 4 continues with remaining Docker roles
```

#### 4. Workstream Memory

Integrate with existing `workstreams.yaml` tracking:

- Each active workstream entry in `workstreams/active/` is also a MemPalace room
- Technical decisions made in a workstream session are automatically filed
- Multi-phase projects maintain continuous context across sessions

Example workstream room structure:

```
wing_proxmox_florin
  / hall_events
    / workstream_adr_0373_phase_1_2_3  (sessions 10-12)
    / workstream_adr_0373_phase_4_5    (sessions 13+)

wing_proxmox_florin
  / hall_discoveries
    / derive_service_defaults_scope_limit (contributed by workstream_adr_0373)
```

#### 5. Runbook and Procedure Discovery

Index operational procedures in MemPalace:

- `wing_proxmox_florin / hall_advice / runbook_NNNN_slug`
- When an operator follows a runbook and encounters issues, capture the divergence
- Example: "Runbook says wait 30s for service startup, but Keycloak needs 90s in this config"

This builds a learned set of corrections and workarounds:

```
mempalace_search "keycloak startup timeout"
→ Found in hall_advice/runbook_keycloak_deployment:
  "Standard wait is 30s, but with reconciliation enabled needs 90s.
   See ADR 0377 for investigation."
```

#### 6. Cross-Service Pattern Library

Collect and index technical patterns discovered across the codebase:

- `wing_proxmox_florin / hall_discoveries / pattern_*`

Examples:
- `pattern_openbao_agent_config` — how to wire the agent into systemd/docker
- `pattern_postgres_client_role` — shared role + registry approach (ADR 0359)
- `pattern_jinja2_filter_limitations` — `ljust` is not available, use Ansible filters instead
- `pattern_hairpin_nat_extra_hosts` — fix for service discovery in guest network
- `pattern_ctmpl_macro_parameter_syntax` — correct OpenBao template parameter passing

#### 7. Session Checkpoints and Handoffs

Capture session boundaries and continuity:

- At session end, auto-save hook files a structured handoff:
  ```yaml
  - session_N_completed:
      - phase: "ADR 0373 Phase 4"
      - outcome: "5 more roles migrated, 45/73 total"
      - blockers: "Group B roles out-of-scope"
      - next_steps: "Phase 5: continue with roles/dify, roles/directus"
  ```

- Next agent reads this and immediately knows where to pick up

#### 8. Incident Postmortems

File incident investigations in MemPalace:

- `wing_proxmox_florin / hall_events / incident_NNNN_slug`
- Example: "Keycloak Timeout Incident (2026-04-07)"
  - Root cause: Admin token refresh fails during outline reconciliation
  - Fix applied: `keycloak_reconcile_outline_users: false`
  - Impact: Convergence now proceeds to completion
  - Residual: Separate Gitea bootstrap issue identified (Session 7 finding)

### Implementation Phases

#### Phase 1: Setup and Initial Mining (Week 1)

1. Install MemPalace locally: `pip install mempalace`
2. Initialize the palace: `mempalace init ~/.mempalace`
3. Mine existing repositories:
   ```bash
   mempalace mine /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/ \
     --mode projects --wing proxmox_florin
   mempalace mine ~/.claude/projects/.../memory/ \
     --mode convos --wing proxmox_florin
   ```
4. Create specialist agents:
   ```bash
   mempalace init-agent reviewer "Code quality and patterns"
   mempalace init-agent architect "Design decisions and tradeoffs"
   mempalace init-agent ops "Deployment and incidents"
   ```
5. Verify: `mempalace status` shows palace with ~50-100 initial memories

**Deliverables:**
- `~/.mempalace/palace/` initialized with seed memories
- `~/.mempalace/agents/reviewer.json`, `architect.json`, `ops.json` created
- Verification that `mempalace_search` can find ADR 0373 implementation details

#### Phase 2: Claude Code Integration (Week 2)

1. Install Claude Code plugin:
   ```bash
   claude plugin install mempalace --scope user
   ```
2. Create CLAUDE.md memory instructions:
   ```markdown
   You have access to MemPalace agent memory. Use it to:
   - Load critical facts at session start: mempalace wake_up --wing proxmox_florin
   - Search for past decisions: mempalace_search "topic"
   - Record discoveries: mempalace_add_drawer "pattern: ..."

   See ~/.mempalace/status for the memory structure.
   ```
3. Configure auto-save hooks in `.claude/settings.json`:
   ```json
   {
     "hooks": {
       "Stop": [{
         "matcher": "proxmox_florin",
         "hooks": [{
           "type": "command",
           "command": "~/.mempalace/hooks/mempal_save_hook.sh"
         }]
       }]
     }
   }
   ```
4. Test: Start a session, do 15 messages of work, verify memory capture

**Deliverables:**
- Claude Code plugin installed and verified
- Auto-save hooks configured
- First session memories captured

#### Phase 3: Historical Context Population (Week 3)

1. Manually capture key decision contexts from memory files:
   - Sessions 1-12 discovery items → file into `hall_discoveries`
   - Known workarounds and quirks → file into `hall_advice`
   - Timeline of ADR implementations → file as temporal facts

2. Cross-link ADRs with implementation memories:
   - Example: ADR 0373 → link to `workstream_adr_0373_phase_*` sessions
   - Example: ADR 0359 (Postgres registry) → link to discovery pattern

3. Create initial knowledge graph facts:
   ```bash
   mempalace_kg_add "proxmox_florin" "implements" "docker_compose_runtime" \
     valid_from="2026-01-01"
   mempalace_kg_add "ADR_0373" "status" "phase_4_in_progress" \
     valid_from="2026-04-08"
   ```

**Deliverables:**
- 50-100 historical memories migrated from session notes
- ADR corpus linked to implementation contexts
- Knowledge graph populated with ~30 key facts

#### Phase 4: Feedback and Refinement (Week 4+)

1. Gather feedback from first 5 agent sessions using MemPalace
2. Refine wing/room structure based on actual usage patterns
3. Add domain-specific rooms discovered during real work (e.g., "convergence_timeouts")
4. Document patterns and best practices for memory filing

**Deliverables:**
- Usage feedback captured and incorporated
- Palace structure stabilized
- Internal documentation for agents on how to use MemPalace

### Integration with Existing Tools

#### With workstreams.yaml

Workstream entries now have associated MemPalace rooms:

```yaml
# workstreams/active/adr-0373-phase-4.yaml
id: adr-0373-phase-4
title: ADR 0373 Phase 4 — Migrate Group A Roles
owner: Claude Agent
status: in_progress
mempalace_room: wing_proxmox_florin/hall_events/workstream_adr_0373_phase_4

features:
  - roles/dify_runtime, roles/directus_runtime, ...

blockers:
  - Group B roles (9) out-of-scope due to non-Docker architecture
```

#### With Plane Issue Board (ADR 0360)

Each Plane issue can reference a MemPalace room:

```
Issue: "ADR 0373 Phase 4 implementation"
Description:
  - Checklist: migrate 8 remaining Docker app roles
  - Memory room: mempalace_room/wing_proxmox_florin/hall_events/workstream_adr_0373_phase_4
  - Search pattern: "roles/dify roles/directus"
```

#### With git Commit Messages

Commit messages can reference MemPalace discoveries:

```
commit abc123def
Author: Claude <claude@anthropic.com>

[adr-0373-phase-4] Migrate dify_runtime and directus_runtime

- Applied derive_service_defaults pattern (works for Docker services)
- Discovered: ljust is not a Jinja2 filter; use Ansible ljust instead
- See MemPalace wing_proxmox_florin/hall_discoveries/ljust_filter_limitation

Closes Plane issue PROXMOX-1234
```

#### With CLAUDE.md

Update the project CLAUDE.md to include memory access:

```markdown
## Memory System

This codebase uses MemPalace for cross-session agent memory.

Before starting work:
1. `mempalace wake_up --wing proxmox_florin` — load critical facts
2. Search for similar work: `mempalace_search "what I'm about to do"`

During work:
- Discover a pattern? Save it: `mempalace_add_drawer "pattern: ..."`
- Hit a timeout? Search for it: `mempalace_search "timeout keycloak"`

At session end:
- Auto-save hook captures discoveries (every 15 messages)
- Manual save: `mempalace_save wing_proxmox_florin`

See ~/.mempalace/status for the current palace structure.
```

## Consequences

### Positive

- **Session continuity** — Next agent picks up exactly where the last one left off, with full context
- **Knowledge preservation** — Debugging insights, patterns, and workarounds aren't lost to time
- **Faster onboarding** — New agents can search MemPalace instead of re-reading git history
- **Cross-service discovery** — Pattern found in Keycloak is immediately available to Gitea work
- **Incident learning** — Debugging sessions (e.g., Session 7 timeout investigation) become searchable resources
- **Reduced false starts** — "We tried X and it failed because Y" is remembered, not re-discovered
- **Specialist focus** — Each agent type (reviewer, architect, ops) maintains focused expertise
- **Zero cloud dependency** — Everything local, no API keys, fully private

### Negative

- **Setup burden** — Initial mining and configuration required (~1 hour one-time)
- **Memory discipline** — Agents must remember to save discoveries; auto-save helps but isn't perfect
- **Eventual staleness** — Memories are only as current as the last session; old decisions may become irrelevant
- **Storage growth** — Every conversation stored verbatim; long-running projects accumulate data (~100MB for 6 months of conversation)
- **Search query skill** — Finding the right memory requires good search terms; unrelated topics may pollute results

### Mitigation

- Auto-save hooks eliminate manual save discipline
- Temporal validity windows in knowledge graph (facts have `valid_from` and `ended` dates)
- Regular cleanup of irrelevant memories (can prune rooms, invalidate stale facts)
- AAAK compression layer (experimental) for token-efficient long-term storage
- Clear room naming and wing structure to improve search accuracy

## Evolution Path

| Phase | Timeline | Mechanism | Goal |
|-------|----------|-----------|------|
| **Phase 1-4** | Now | Claude Code plugin + auto-save hooks | Establish memory habit and demonstrate value |
| **Phase 5** | Q2 2026 | NATS event integration | Auto-capture convergence events (failures, timeouts, anomalies) |
| **Phase 6** | Q3 2026 | Knowledge graph fact queries | Architect agent queries "when was Group B scope decided?" and gets temporal answer |
| **Phase 7** | Q4 2026 | Specialized agent diaries | Reviewer, ops, architect agents maintain independent focus diaries in AAAK compression |

## Links

- MemPalace Repository: https://github.com/milla-jovovich/mempalace
- MemPalace LongMemEval Benchmark: 96.6% recall, zero API calls
- Related: ADR 0360 (Plane as Agent Task HQ), ADR 0373 (Role Registry Migration)
- Related: AGENTS.md (handoff protocol), CLAUDE.md (session protocol)

## Questions for Review

1. Should MemPalace storage live in `.local/` (per worktree) or `~/.mempalace/` (shared across worktrees)?
   - **Recommendation:** `~/.mempalace/` (shared) so all proxmox_florin work across all worktrees feeds the same palace

2. Should specialist agents (reviewer, architect, ops) have their own diaries or share one hall_advice room?
   - **Recommendation:** Separate diaries per agent (more focus, less noise)

3. How do we handle MemPalace storage across multiple machines (e.g., if the repo is cloned on a different laptop)?
   - **Recommendation:** `~/.mempalace/` is machine-local (no git sync); critical facts are also in MEMORY.md for portability

4. Should we auto-mine new conversation exports from `.claude/projects/...` each session?
   - **Recommendation:** Yes, via the `MEMPAL_DIR` environment variable in auto-save hooks

## Acknowledgments

MemPalace is an open-source project by Milla Jovovich and Ben Sigman. This ADR documents our integration approach and is not endorsed by the MemPalace team but follows their documented patterns for specialized agent use.
