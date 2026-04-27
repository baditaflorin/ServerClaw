# ADR 0442: Multi-Deployment Make Interface & Agent Worktree Binding

- Status: Proposed
- Implementation Status: Not Started
- Date: 2026-04-27
- Concern: forkability, multi-tenancy, agent-isolation, operator-ergonomics
- Tags: multi-deployment, makefile, worktrees, workstreams, agents
- Implements: ADR 0439 (Multi-Deployment Repo Architecture)
- Depends on:
  - ADR 0440 (Per-Deployment Identity & Artifact Isolation)
  - ADR 0441 (Deployment-Scoped Service Subsetting)
  - ADR 0419 (PR-Based Integration Flow)

---

## Context

ADRs 0440 and 0441 give us the data layout. This ADR defines the
**operator surface** (Make targets) and the **agent isolation contract**
(worktree ↔ deployment binding) that make N concurrent deployments
practical.

Today's reality:

- The Makefile threads `env=production` through to Ansible. There is no
  `deployment=` parameter.
- Workstreams (`workstreams/active/*.yaml`, generated index
  `workstreams.yaml`) describe what's in flight per worktree, but have
  no notion of which deployment a workstream is editing.
- Two agents in `.claude/worktrees/foo` and `.claude/worktrees/bar` can
  both run `make generate-platform-vars` and produce conflicting
  uncommitted edits in `inventory/group_vars/platform.yml`.
- Operators have no way to ask "which deployment is this worktree for?"
  except by reading shell history.

We need:

1. A simple, uniform `deployment=<slug>` parameter on every Make target.
2. A way to bind a worktree to a deployment so that target defaults are
   correct and confusing cross-deployment runs are blocked.
3. Workstream metadata that records which deployment each in-flight
   workstream is operating on.
4. Concurrency safety: when two agents *do* converge two deployments at
   once, no shared filesystem mutation can corrupt either run.

---

## Decision

### `deployment=<slug>` is universal

Every Make target that today accepts `env=` accepts `deployment=`.
Resolution precedence (matches ADR 0440):

1. Explicit `deployment=<slug>` on the command line.
2. `$DEPLOYMENT` env var.
3. Worktree marker `.claude/worktrees/<name>/.deployment` (if invoked
   inside a worktree).
4. `.local/active-deployment` (single-line file at repo root).
5. Hard error with actionable message.

The Makefile reads precedence via a one-liner shim early in the file:

```make
DEPLOYMENT := $(shell python3 scripts/deployment.py resolve --quiet 2>/dev/null)
ifndef DEPLOYMENT
    $(error No deployment resolved. Run 'make use-deployment slug=<slug>' or pass deployment=<slug>)
endif
```

`make` users who pass `deployment=foo` override the resolved value
because Make's command-line variable assignment beats the `:=`. (We
add a guard so a known-bad slug fails fast: `make ... deployment=typoed`
errors with a list of known deployments.)

### New top-level Make targets

```
# Lifecycle
make new-deployment slug=<slug> apex=<domain> operator='Name <email>'
                            # scaffolds .local/deployments/<slug>/{identity,topology,profile}.yml
                            # with sensible defaults; never overwrites
make use-deployment slug=<slug>
                            # writes .local/active-deployment
make list-deployments       # lists .local/deployments/* with current versions
make whoami                 # prints active deployment + worktree binding (if any)

# Per-deployment artifact regeneration (replaces today's generate-* targets)
make generate deployment=<slug>
                            # runs all generators: platform-vars, inventory,
                            # manifest, discovery, adr-index — into
                            # .local/deployments/<slug>/generated/
make generate-all           # iterates every deployment under .local/deployments/

# Worktree binding
make bind-worktree slug=<slug>
                            # writes .deployment in the current worktree
make worktree-status        # reads .deployment + workstream entry, prints summary
```

### Existing targets gain `deployment=`

| Target | Today | Tomorrow |
|--------|-------|----------|
| `make converge-<svc>` | `env=production` | `deployment=<slug> env=production` |
| `make migrate-service` | `svc= to= env=production` | `deployment=<slug> svc= to= env=production` |
| `make detect-orphans` | scans current inventory | scans `<slug>/generated/hosts.yml` |
| `make purge-orphans` | acts on current inventory | scoped to deployment |
| `make publish-serverclaw` | runs against `.local/identity.yml` | `deployment=<slug>` selects which identity to sanitize against; default: every deployment, sequentially |
| `make audit-sanitization` | scans `.local/identity.yml` | scans every `.local/deployments/*/identity.yml` |
| `make parallel-converge` | parallel across services | parallel across services *within one deployment* — never cross-deployment |
| `make time-converge` | service-scoped | + deployment-scoped |
| `make bootstrap` | uses `PLATFORM_IDENTITY_OVERLAY` | accepts `deployment=`; sets the overlay automatically |

### Concurrency safety

A new module `scripts/deployment_lock.py` exposes:

```python
@contextmanager
def deployment_lock(slug: str, kind: str = "converge"):
    """
    Advisory file lock at .local/deployments/<slug>/state/<kind>.lock.
    Raises DeploymentLocked if held; prints PID and timestamp of holder.
    """
```

The Makefile wraps every mutating target (`converge-*`, `generate`,
`migrate-service`, `live-apply`) in this lock. Two agents converging
the same deployment at the same time get a clean error, not interleaved
SSH sessions to the same host. Two agents converging *different*
deployments take *different* locks and proceed in parallel.

The lock files live under `.local/deployments/<slug>/state/` (gitignored,
ephemeral). They're advisory — the kernel doesn't enforce them; the
Make wrapper does. That's good enough for the "agents who cooperate via
this repo" threat model. (If an operator runs `ansible-playbook`
directly, they bypass the lock — at their own risk.)

### Workstream binding

`workstreams/active/<id>.yaml` schema gains a required field:

```yaml
# workstreams/active/multi-deployment-rollout-2026-04.yaml
id: multi-deployment-rollout-2026-04
deployment: prod                           # NEW — required
worktree: .claude/worktrees/loving-agnesi-b8dab1
branch: claude/loving-agnesi-b8dab1
status: active
owns_surfaces:
  - docs/adr/0439-*.md
  - scripts/deployment.py
# ...
```

`scripts/workstream_registry.py` validates that `deployment` is set and
that the slug exists. `workstreams.yaml` (the generated index) gets a
new top-level grouping by deployment, so the operator can see at a
glance "what's in flight on `prod` vs `0fork`".

The cross-workstream surface ownership check
(`config/contracts/workstream-registry-v1.yaml`) becomes
deployment-aware: two workstreams may own the same surface if and only
if they're on different deployments. (E.g. both can edit
`profile.yml` — but they each edit their own deployment's copy.)

### Worktree marker file

When an agent runs `make bind-worktree slug=<slug>` inside its
worktree, we write:

```
.claude/worktrees/<name>/.deployment   # one line: <slug>
```

This file is **not** committed (added to `.gitignore`). Its presence
makes every Make invocation inside that worktree default to that
deployment. An agent that tries to converge a different deployment
from the same worktree gets:

> Worktree is bound to deployment `prod`. To act on `0fork`, either
> rebind (`make bind-worktree slug=0fork`) or use a separate worktree.

The bind is intentionally one-deployment-at-a-time per worktree —
agents who need to act on multiple deployments use multiple worktrees,
which is already how this team works.

### Public ServerClaw surface

The published repo gets the same Make interface but with no deployments
under `.local/`. A fresh fork operator runs:

```
git clone https://github.com/baditaflorin/ServerClaw.git
cd ServerClaw
make new-deployment slug=mysite apex=mysite.example operator='Me <me@mysite.example>'
# ... edit the three generated YAML files ...
make bootstrap
```

…and gets a one-deployment platform. To add a second:

```
make new-deployment slug=client42 apex=client42.example operator='...'
make bootstrap deployment=client42
```

No code differences between the private and public interface — the
Makefile, scripts, and ADRs all publish unchanged. Only the contents
of `.local/deployments/` differ.

---

## Consequences

### Positive

- One uniform parameter (`deployment=`) replaces ad-hoc env-var
  juggling (`PLATFORM_IDENTITY_OVERLAY`).
- Agents in different worktrees can converge different deployments
  concurrently with explicit lock-based isolation.
- The public ServerClaw fork story stops being "one-fork-per-clone" and
  starts being "N-deployments-per-clone" with no extra
  per-fork-operator effort.
- `make whoami` and `make worktree-status` make it impossible for an
  agent (or a tired operator) to mistake which deployment they're
  acting on.
- Workstream registry tells the operator at a glance which deployments
  have active agent work.

### Negative

- Every operator-facing Make invocation grows a `deployment=` parameter.
  Mitigated by the active-deployment file and worktree binding —
  invocations inside a bound worktree look identical to today.
- One-time migration of `workstreams/active/*.yaml` to add the
  `deployment` field to every existing entry.
- The Makefile gains ~80 lines of plumbing. Acceptable.

### Neutral

- `env=production`/`env=staging` survive untouched.
- The pre-push gate (build server `10.10.10.30`) is currently a `prod`
  resource. For now, only `prod` exercises remote validation; other
  deployments use `SKIP_REMOTE_GATE=1`. ADR 0439 open question 1
  tracks the per-deployment gate runner.

---

## Migration plan

Phase 1 (lands behind `MULTI_DEPLOYMENT_ENABLED=1` from ADR 0440):

1. Implement `scripts/deployment.py resolve` and the resolution
   precedence chain.
2. Add the Makefile shim and the new lifecycle targets (`new-deployment`,
   `use-deployment`, `list-deployments`, `whoami`, `bind-worktree`,
   `worktree-status`).
3. Add `scripts/deployment_lock.py` and wrap mutating targets.
4. Backfill `deployment: prod` into every existing
   `workstreams/active/*.yaml` (one mechanical PR).
5. Update `scripts/workstream_registry.py` schema validator to require
   `deployment`.

Phase 2 (flag flip):

6. Every `converge-*` and ops target gains `deployment=` threading.
7. `bootstrap` learns to derive `PLATFORM_IDENTITY_OVERLAY` from the
   resolved deployment (overlay env var becomes a Makefile-internal
   detail, no longer operator-facing).
8. `make whoami` becomes the recommended pre-flight check in agent
   prompts and CLAUDE.md.

Phase 3:

9. Author the multi-deployment runbook
   (`docs/runbooks/multi-deployment.md`) with the three example flows:
   "stand up a new deployment", "two agents on two deployments", "live
   apply with deployment scoping".
10. CI: pre-push gate runs `make audit-sanitization` (now scans every
    deployment) and `scripts/deployment.py validate-all` (schema-checks
    every deployment's identity/topology/profile).

### Rollback

Phase 1 is additive — revert the PR. Phase 2 changes are wrapped in
`MULTI_DEPLOYMENT_ENABLED`; flip to `0` to get today's single-deployment
behaviour. Phase 3 adds a runbook and a CI step; both removable.

---

## Open Questions

1. **Cron'd / scheduled converges.** If an automation job runs
   `make converge-* deployment=prod` on a cadence, how does it
   coordinate with an agent who happens to hold the converge lock?
   *Tentative*: cron loses; lock-holder logs a "I'm here, will release
   shortly" notice. Cron retries on next tick. (Already how
   `make parallel-converge` handles per-service contention.)

2. **`make publish-serverclaw` with N deployments.** Today it
   sanitizes once. Tomorrow: does it iterate every deployment and
   produce one publish, or does the operator pick one? *Tentative*:
   single publish — the public mirror is generic-only by ADR 0409, so
   the leak-marker scan must succeed against the union of all
   deployments' identities. Use `--deployment all` (default).

3. **Cross-deployment migrations.** "Move outline from deployment A
   to deployment B" is a category we haven't designed for. Out of
   scope for this ADR; flagged as future work. Most likely shape:
   `make export-service-state svc= deployment=A` → operator-mediated
   import on B.

4. **Tailscale tailnet boundary.** Each deployment has its own
   tailnet (per ADR 0424). If two deployments need to talk
   (e.g. shared OpenBao), how is that wired? *Tentative*: out of
   scope — start with strict isolation; add cross-tailnet ACLs later
   if a real use case appears.
