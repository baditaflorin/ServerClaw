# ADR 0481: Explicit Deployment Context (no implicit identity.yml swap)

**Status**: ACCEPTED
**Date**: 2026-05-11
**Decision**: Deployment selection is an explicit, agent-checkable parameter. There is no "active deployment" hidden inside an unnamed file at the repo root.

---

## Context

### Problem

The repository runs N parallel Proxmox deployments off a single generic-by-default codebase (ADR 0407). Today: `lv3.org` (Florin's primary) and `0fork.com` (public fork). The pattern is correct; the *selection mechanism* is not.

Until this ADR, the active deployment was identified by **renaming `.local/identity.yml`** (parked copies live next to it as `.local/identity.yml.lv3-backup`, `.local/identity.yml.0fork-backup`, etc.). Whichever happened to be named `identity.yml` at any moment was "the deployment." This produced three concrete failure modes during a 2026-05-11 status-check session:

1. **Agents could not tell which deployment they were on.** Two subagents reading the same repo simultaneously reported different platform domains depending on what the symlink pointed to when each ran.
2. **Truth was split across committed code (lv3-shaped) and `.local/` overlays (0fork-shaped).** The service registry assigned Harbor to `runtime-control` (10.10.10.92) — true on lv3, but that VM does not exist on 0fork. The agent could not reconcile the two without inspecting hidden state.
3. **Stale deployment slots.** `.local/deployments/prod/` contained a duplicate of 0fork data. `.local/deployments/lv3/` did not exist at all. The intended layout (ADR 0440) was scaffolded but never populated for the real lv3 deployment.

The infrastructure for explicit deployment selection already existed:

- `scripts/deployment.py` resolves slugs via precedence: explicit flag → `$DEPLOYMENT` → worktree `.deployment` marker → `.local/active-deployment` → `DeploymentNotResolvedError`
- `.local/deployments/<slug>/` carries `identity.yml`, `topology.yml`, `profile.yml`, `connection.yml`, plus `generated/`, `secrets/`, `receipts/`, `state/`
- ADRs 0437 / 0439 / 0440 / 0480 establish the multi-deployment substrate
- `MULTI_DEPLOYMENT_ENABLED` flag in the Makefile threads `--deployment <slug>` into generator targets

What was missing: **agent-facing surface and mandatory enforcement.** No `make whoami`. No requirement that a converge target name its deployment. CLAUDE.md said nothing about it.

### Why this matters

The platform is designed to be forkable. ServerClaw's public mirror exists so other operators can stand up their own deployment from this code. The number of deployments only goes up. The cost of getting "which deployment am I touching" wrong increases linearly with deployment count and superlinearly with the number of agents/operators acting on the repo at once.

---

## Decision

Deployment selection becomes **mandatory, explicit, and observable in one command.**

### 1. The slug is the unit of identity

Every deployment is a single slug (`lv3`, `0fork`, `mycorp`, …). The slug names a directory under `.local/deployments/<slug>/` that owns everything deployment-specific: identity, topology, secrets, receipts. The slug is the only thing a wrapper command needs.

### 2. Resolution precedence is unchanged but newly enforced

`scripts/deployment.py` already implements the chain:

1. Explicit CLI flag (`--deployment <slug>` / `deployment=<slug>` for make)
2. `$DEPLOYMENT` env var
3. Worktree-local `.deployment` marker file
4. Repo-wide `.local/active-deployment` file
5. Hard error — never silently pick a default

This ADR adds **the final rule**: any safety-critical target (`converge-*`, `probe-*`, `live-apply`, `edge-*`, `bootstrap`, anything that mutates a remote host) MUST list `_require-deployment` as a prereq. That prereq runs `python scripts/deployment.py resolve` and fails the make build if the chain returns `DeploymentNotResolvedError`.

### 3. New Makefile surface

| Target | Purpose |
|---|---|
| `make whoami` | Print active deployment + platform domain + operator + identity file path. The one-line check every agent runs at session start. |
| `make deployments-list` | List every slug present under `.local/deployments/`. |
| `make use-deployment slug=<s>` | Write `<s>` to `.local/active-deployment` (repo-wide default). |
| `make bind-worktree slug=<s>` | Write `<s>` to a `.deployment` marker in the current worktree (overrides repo default). |
| `make new-deployment slug=<s> apex=<domain>` | Scaffold `.local/deployments/<s>/` from the schema templates. |
| `make sync-identity-link` | Refresh `.local/identity.yml` as a symlink to `.local/deployments/<active>/identity.yml` so legacy code paths continue to find the active identity. |
| `make _require-deployment` | Internal prereq. Fails if no slug resolves. Prints the resolution chain in the error. |

### 4. Legacy `.local/identity.yml` is a symlink, not a file

To keep the existing 420+ references working unchanged, `.local/identity.yml` becomes a symlink to `.local/deployments/<active>/identity.yml`. `make use-deployment` and `make sync-identity-link` keep it in sync. Hand-editing the symlink target is forbidden; the symlink IS the active-deployment pointer's view into the data.

### 5. CLAUDE.md gets a Section 0

A new section at the top of `CLAUDE.md` instructs every session to run `make whoami` before doing anything that touches a remote host. If `whoami` errors, the session must resolve the deployment (via one of the four precedence sources) before continuing. This is the agent-confusion fix: a single, deterministic, one-line answer to "where am I."

### 6. Receipts and workstreams gain an explicit `deployment:` field

Rather than restructure existing directories, receipt JSON and workstream YAML add a `deployment: <slug>` field. The pre-push gate validates that the receipt's `deployment` matches the slug present in the workstream that produced it. Old receipts without the field are grandfathered until the next live-apply.

### 7. Out of scope (for this ADR)

- Per-deployment SSH config generation. Today operators maintain `~/.ssh/config` by hand. A future ADR can add `make ssh-config-sync` once we standardize the connection schema.
- Per-deployment publish pipelines. `scripts/publish_to_serverclaw.py` will read the active deployment but does not yet support publishing N deployments to N mirrors.
- Renaming `prod` → `lv3`. The stale `.local/deployments/prod/` slot (a duplicate of 0fork) is removed in this ADR's implementation; the lv3 data is placed under the slug `lv3`. We do not introduce a `prod` slug going forward.

---

## Consequences

### Positive

- **One-line orientation.** `make whoami` is the deterministic answer to "which deployment am I on" — for agents, operators, CI, anyone.
- **No more identity-file shuffling.** Switching deployments is a single command (`make use-deployment slug=<s>`) that writes one marker file. Nothing gets renamed in place.
- **Failure is loud.** `_require-deployment` makes "I forgot to set deployment" a make-time error, not a silent miscategorization at apply-time.
- **Scales to N deployments.** Adding a third or hundredth deployment is `make new-deployment slug=<s> apex=<domain>` — no committed-code change.
- **Worktree-aware.** Two parallel worktrees can bind to different deployments via `.deployment` markers without fighting over a shared symlink.

### Negative

- One more rule for new contributors. Mitigated by `make whoami` being trivial and CLAUDE.md surfacing the rule at the top.
- Targets that pre-date this ADR need `_require-deployment` retrofitted. Done in a follow-up sweep; not all-at-once. New targets added after this ADR MUST include it.

### Migration

1. Backfill `.local/deployments/lv3/` from `.local/identity.yml.lv3-backup`.
2. Remove `.local/deployments/prod/` (stale duplicate of 0fork).
3. Write `.local/active-deployment` → `0fork` (the current active deployment on this host).
4. `make sync-identity-link` refreshes the legacy `.local/identity.yml` symlink.
5. Existing `.local/identity.yml.<name>-backup` files stay where they are as raw archive copies; nothing reads them anymore.

The migration is reversible: deleting `.local/active-deployment` and restoring `.local/identity.yml` from a backup returns to pre-ADR behavior.

---

## References

- ADR 0407 — Generic by default (deployment values live in `.local/`, not committed)
- ADR 0437 — Overlay-aware bootstrap (`PLATFORM_IDENTITY_OVERLAY` env var)
- ADR 0439 — Multi-deployment generators (`--deployment` flag)
- ADR 0440 — Deployment directory layout
- ADR 0448 — Connection registry
- ADR 0480 — Multi-deployment certificate validation
- `scripts/deployment.py` — resolver implementation
