# ADR 0439: Multi-Deployment Repo Architecture — N Independent Servers from One Checkout

- Status: Proposed
- Implementation Status: Not Started
- Date: 2026-04-27
- Concern: forkability, multi-tenancy, agent-isolation, iac-end-to-end
- Tags: multi-deployment, deployments, parallel-converge, agent-coordination, refactor
- Depends on:
  - ADR 0407 (Generic-By-Default — `.local/` Deployment Values)
  - ADR 0409 (Zero-Sanitization Publication)
  - ADR 0422 (Identity Overlay — `PLATFORM_IDENTITY_OVERLAY`)
  - ADR 0424 (Fork-Clone of the Platform onto Hetzner AX41)
  - ADR 0438 (Generic-by-Construction — Generative Cascade IaC)
- Composes with:
  - ADR 0440 (Per-Deployment Identity & Artifact Isolation) — physical layout
  - ADR 0441 (Deployment-Scoped Service Subsetting) — service catalog selection
  - ADR 0442 (Multi-Deployment Make Interface & Agent Worktree Binding) — operator/agent surface

---

## Context

The platform has been progressively generalised so that one operator can fork
the codebase and bring up a clone on a different domain (ADR 0407, 0409, 0422,
0424). The clone story today is **serial**: edit `.local/identity.yml` to
point at the new apex, run `make converge-*`, done. Switching back to prod
means swapping which file is named `identity.yml`.

The operator now wants to manage **N independent deployments concurrently**
from one repo checkout (or one public ServerClaw fork) and have multiple
Claude Code agents work on different deployments in parallel without
stepping on each other. Concrete shape: three servers, one with ten
services, one with fifteen, one with twenty — each on its own apex domain,
each isolated.

The current architecture cannot support this because:

1. **`.local/identity.yml` is a singleton.** It defines exactly one
   `platform_domain`, one operator, one DNS zone. The overlay env var
   from ADR 0422 lets an agent point at a *different* file, but only
   one is "active" per process tree, and many scripts read the default
   path with no override hook.
2. **Generated artifacts are committed and shared.**
   `inventory/group_vars/platform.yml` (192 KB), `inventory/hosts.yml`,
   `build/platform-manifest.json`, and `build/onboarding/*` are
   regenerated from identity+inventory and committed. Two agents
   regenerating against different deployments produce conflicting diffs
   on the same file paths.
3. **Inventory environments are an enum, not a parameter.** The host
   pattern map (`inventory/group_vars/all/main.yml::playbook_execution_host_patterns`)
   hardcodes `production` / `staging` / `clone`. Adding deployments by
   adding new env enum values does not scale and conflates "test
   variant of one deployment" with "entirely separate deployment".
4. **No service-subset mechanism.** Service presence is binary (in
   `platform_service_registry` or not). There is no "deployment X runs
   only these ten services" filter — and adding/removing entries from
   the registry to express that would corrupt the other deployments
   that share the file.
5. **Workstreams and worktrees do not bind to a deployment.** Two
   worktrees on different branches happily regenerate the same
   `platform.yml`, then the second commit conflicts with the first.

This ADR is the umbrella decision. It names the architecture, fixes the
vocabulary, and defines the contract that ADRs 0440–0442 implement.

---

## Decision

Introduce **deployments** as a first-class concept in this repo. A
deployment is the unit of operator identity, infrastructure topology, and
service selection. Everything that today is "the platform" becomes "a
deployment".

### Deployment definition

A deployment is uniquely identified by a short slug (`prod`, `0fork`,
`acme`, `customer-42`) and consists of:

- **Identity** — apex domain, operator name/email, DNS provider zone,
  Tailscale tailnet, mail config (the contents of today's
  `.local/identity.yml`).
- **Topology** — the `proxmox_guests` list, network bridges, host IPs
  (the contents of today's `inventory/host_vars/proxmox-host.yml`,
  per-deployment).
- **Service profile** — an explicit allowlist (or tier label) selecting
  which services from the shared catalog this deployment runs (defined
  in ADR 0441).
- **Generated artifacts** — `platform.yml`, `hosts.yml`,
  `platform-manifest.json`, onboarding scaffolds, all derived from the
  three above. Stored in a per-deployment subdirectory; not committed
  by default.
- **Secret material** — per-service credentials, OpenBao snapshots, SSH
  bootstrap keys (the rest of today's `.local/<service>/`).

### Vocabulary

| Term | Meaning |
|------|---------|
| **Deployment** | A standalone server (or set of servers) under one apex. The unit of operator identity and topology. |
| **Environment** (`env=production`/`env=staging`) | A variant *within* a deployment — same identity, different host group. Survives this refactor unchanged. Most deployments will only ever use `production`. |
| **Service profile** | A named subset of the platform service catalog opted into by a deployment. |
| **Service catalog** | The full set of services this repo knows how to deploy, declared in `inventory/group_vars/all/platform_services.yml`. Shared across deployments. |

`deployment` and `environment` are **orthogonal** axes. A deployment
named `prod` may have `env=production` and `env=staging`. A deployment
named `0fork` may have only `env=production`. Both run from the same
checkout without colliding because every artifact path includes the
deployment slug.

### High-level architecture

```
repo/
├── inventory/
│   ├── group_vars/all/             # generic, shared (no deployment-specific values)
│   ├── group_vars/platform.yml     # REMOVED — moves under .local/deployments/<slug>/generated/
│   ├── host_vars/proxmox-host.yml  # REMOVED — moves under .local/deployments/<slug>/topology/
│   └── hosts.yml                   # REMOVED — moves under .local/deployments/<slug>/generated/
├── roles/                          # generic; reads platform_domain etc. via group_vars
├── playbooks/                      # generic
├── scripts/
│   ├── deployment.py               # NEW — load/list/validate deployments
│   ├── generate_platform_vars.py   # MODIFIED — accepts --deployment <slug>
│   ├── generate_inventory.py       # MODIFIED — accepts --deployment <slug>
│   └── ...
├── docs/
│   ├── adr/                        # generic
│   └── runbooks/multi-deployment.md  # NEW
└── Makefile                        # MODIFIED — every target accepts deployment=<slug>

.local/                              # gitignored
├── deployments/
│   ├── prod/
│   │   ├── identity.yml            # apex, operator, DNS, mail
│   │   ├── topology.yml            # proxmox_guests, bridges, IPs
│   │   ├── profile.yml             # service allowlist (ADR 0441)
│   │   ├── generated/              # platform.yml, hosts.yml, manifest — derived
│   │   └── secrets/                # service credentials, openbao snapshots
│   ├── 0fork/
│   │   ├── identity.yml
│   │   ├── topology.yml
│   │   ├── profile.yml
│   │   ├── generated/
│   │   └── secrets/
│   └── acme/
│       └── ...
└── ssh/
    └── bootstrap.id_ed25519        # shared agent SSH key (no per-deployment fan-out yet)
```

### Operator surface (full detail in ADR 0442)

```bash
# One-time scaffold for a new deployment
make new-deployment slug=acme apex=acme.example operator='ACME Ops <ops@acme.example>'

# Edit .local/deployments/acme/identity.yml + topology.yml + profile.yml as needed.

# All commands from then on take deployment=<slug>:
make generate            deployment=acme
make bootstrap           deployment=acme
make converge-keycloak   deployment=acme env=production
make migrate-service     deployment=acme svc=outline to=docker-runtime
make publish-serverclaw  deployment=acme

# Default deployment when slug is omitted: read from .local/active-deployment
# (a single-line file written by `make use-deployment slug=<slug>`).
```

### Agent worktree binding (full detail in ADR 0442)

A worktree is bound to exactly one deployment for its lifetime. The bind
is recorded in `workstreams/active/<id>.yaml::deployment: <slug>` and
materialised as `.claude/worktrees/<name>/.deployment` (a one-line slug
file). All Make targets default to that slug inside the worktree, so
two agents in two worktrees on different deployments regenerate
**different** generated paths and never produce overlapping diffs.

---

## Consequences

### Positive

- N deployments managed from one checkout / one public ServerClaw fork.
- Two or more agents can converge two or more deployments concurrently
  with no shared mutable state.
- Adding a new deployment is one Make target plus three small YAML
  files — pure IaC, no code edits.
- The public ServerClaw repo gains the same property: a fork operator
  can run three customer deployments from one clone.
- The committed code becomes strictly more generic (no
  deployment-specific generated artifacts in git).

### Negative

- **Breaking change**: today's path expectations
  (`inventory/group_vars/platform.yml`, `inventory/hosts.yml`,
  `inventory/host_vars/proxmox-host.yml`) are abolished. A migration
  script must move the existing files into
  `.local/deployments/prod/...` and the existing operator must run it
  exactly once.
- All scripts that read these paths must be updated (~15 scripts; see
  ADR 0440 for the inventory).
- `workstreams.yaml` gains a `deployment` field; old entries are
  retroactively assigned `deployment: prod`.
- The publish pipeline must learn to publish *one deployment's*
  generic-only view to the public repo (committed code stays generic;
  `.local/deployments/<slug>/` never publishes).

### Neutral

- `env=production`/`env=staging` survive untouched. No converge command
  changes meaning — they just gain a `deployment=` parameter that
  defaults to the active deployment.
- Existing ADRs that name `platform.yml` or `hosts.yml` as paths
  (0359, 0373, 0407, 0409, 0422, 0424, 0430, 0438) remain valid in
  spirit; the path moves but the contract does not.

---

## Migration

A one-time migration of the existing prod deployment:

1. Create `.local/deployments/prod/`.
2. Move `.local/identity.yml` → `.local/deployments/prod/identity.yml`.
3. Move `inventory/host_vars/proxmox-host.yml` →
   `.local/deployments/prod/topology.yml`.
4. Move `inventory/group_vars/platform.yml` →
   `.local/deployments/prod/generated/platform.yml` (no longer
   committed; regenerated on demand).
5. Move `inventory/hosts.yml` → `.local/deployments/prod/generated/hosts.yml`.
6. Generate `.local/deployments/prod/profile.yml` with all currently
   deployed services (computed by reading the live `lv3_service_topology`).
7. Write `.local/active-deployment` with content `prod`.
8. Run `make generate deployment=prod` and confirm the generated
   artifacts match the previously committed ones byte-for-byte modulo
   ordering.
9. Delete the old committed paths from git in one commit titled
   `[refactor] move prod deployment under .local/deployments/`.

This migration is automated by `scripts/migrate_to_multi_deployment.py`
(introduced in ADR 0440 implementation Phase 1).

The 0fork deployment is bootstrapped fresh under
`.local/deployments/0fork/` from `.local/identity.yml.0fork` (which
already exists) plus the existing `.local/0fork/` secrets directory.

---

## Open Questions

1. **Cross-deployment shared state.** Today the build server
   (`10.10.10.30`) runs the pre-push gate for the `lv3` deployment.
   Should the `0fork` deployment have its own gate runner, or share?
   *Tentative*: each deployment owns its own gate; the gate URL is a
   per-deployment identity field.

2. **Public ServerClaw mirror granularity.** Does the public mirror
   stay one repo (showing only generic code, no deployments) or fan out
   to one mirror per deployment? *Tentative*: one mirror, generic only.
   `.local/deployments/<slug>/` is per-fork-operator state and never
   publishes regardless of how many deployments a private operator
   runs.

3. **VERSION / changelog scoping.** Today `VERSION` is one number for
   the whole repo. With N deployments, do we keep one repo-wide
   VERSION (= "version of the IaC code") or per-deployment release
   trains? *Tentative*: one repo-wide VERSION; each deployment's
   `live_apply_evidence` block in its own `topology.yml` records when
   that deployment last consumed a given VERSION.

These are tracked in the implementation ADRs (0440–0442) and resolved
incrementally.
