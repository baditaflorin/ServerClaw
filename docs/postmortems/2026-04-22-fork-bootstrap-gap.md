# Postmortem: `make bootstrap` Broken for Forks — 2026-04-22

**Status:** Root cause fixed in ADR 0437. End-to-end fork validation pending.
**Severity:** Low (blocked self-replication promise; no production outage).
**Author:** claude
**Related:** ADR 0424, ADR 0425, ADR 0430, ADR 0431, ADR 0437.

## Summary

The documented one-command install path from `CLAUDE.md` and `README.md` —
`git clone ServerClaw && cd ServerClaw && make init-local && make bootstrap`
— did not actually work against any machine other than the original author's
Proxmox host. Four independent gaps had to be fixed before a plain `make
bootstrap` could stand up an identical deployment on the 0fork.com clone.

This undermined the ADR 0407 "generic by default" claim. From the outside,
the private and public ServerClaw repos looked forkable; in practice the
only path to a working fork was a hand-crafted wrapper
(`make deploy-0fork`), because each gap failed silently rather than loudly.

## Timeline

- **2026-04-21** — ADR 0424 fork attempt begins on Hetzner AX41-NVMe.
  Operator discovers Proxmox install works but service convergence
  requires a separate `deploy-0fork` entry point. Wrapper added in ADR
  0431 as a stopgap.
- **2026-04-22 14:00 UTC** — Hetzner host reinstalled from scratch to
  reset PVE state. Operator asks to validate that the documented
  `make bootstrap` path works end-to-end for the fork, with timing
  instrumentation baked in.
- **2026-04-22 14:45 UTC** — While preparing to run `make bootstrap`,
  agent discovers `scripts/generate_inventory.py` does not honour
  `PLATFORM_IDENTITY_OVERLAY`. Committed `inventory/hosts.yml` contains
  10.10.10.X production IPs; running bootstrap would target the wrong
  network. Operator confirms intent: fix the root cause, not work
  around it. "Aim is to reduce manual changes and have a resilient
  installation that will work."
- **2026-04-22 15:30 UTC** — Four gaps mapped (inventory generation,
  BOOTSTRAP_KEY override, env=clone threading, proxmox_host_jump flag).
- **2026-04-22 16:00 UTC** — ADR 0437 written. Fix implemented in
  `scripts/generate_inventory.py` + `Makefile` top-of-file conditional.
  `scripts/timed.sh` promoted from `.local/0fork-timings/timed-ssh.sh`
  into the committed tree as a generic command-wrapper.

## What happened

Four gaps, each individually small, compounded to make the "single command"
path unreachable:

### Gap 1 — `scripts/generate_inventory.py` ignored the overlay

The generator read only `inventory/host_vars/proxmox-host.yml` (the
committed production host_vars). Even when the operator set
`PLATFORM_IDENTITY_OVERLAY=.local/identity.yml.0fork` and wrote a matching
`.local/host_vars/proxmox-host.yml` per ADR 0430, running `make
generate-inventory` said "inventory/hosts.yml is up to date" because the
generator wasn't looking at the overlay at all.

Result: `inventory/hosts.yml` stayed pinned to the author's production
CIDR. `ansible_host: 10.10.10.50` for every guest.

### Gap 2 — `BOOTSTRAP_KEY` was hardcoded

`BOOTSTRAP_KEY ?= $(LOCAL_OVERLAY_ROOT)/ssh/bootstrap.id_ed25519`. The
0fork clone's SSH key is `hetzner_llm_agents_ed25519` (provisioned via
Hetzner Robot). There was no path for a fork operator to swap keys
without editing the Makefile, which the ADR 0407 "generic by default"
rule forbids.

### Gap 3 — `env=clone` not threaded through bootstrap stages

Only `converge-site` (Stage 5 of `make bootstrap`) honours `$(env)` via
`$(ANSIBLE_SCOPED_RUN) --env $(env)`. The earlier stages
(`install-proxmox`, `configure-network`, `harden-access`,
`provision-guests`) call `ansible-playbook` directly with no `-e env=...`
override. Consequence: `playbook_execution_host_patterns` resolves to
production for the first four stages of bootstrap on a fork, breaking
immediately on host selection.

### Gap 4 — `proxmox_guest_ssh_connection_mode=proxmox_host_jump` missing

On a fresh fork with no mesh VPN, guests are only reachable via the
proxmox host (ProxyJump). The ADR 0430 runtime machinery handles this
but only when the `proxmox_guest_ssh_connection_mode=proxmox_host_jump`
extra-var is passed. `deploy-0fork` passed it; `make bootstrap` did not.

## Root cause

Each gap was a consequence of the same architectural miss: `make bootstrap`
was written assuming the author's own deployment, and the overlay
machinery was layered on later without retrofitting the bootstrap target.

When ADR 0430 established `.local/host_vars/proxmox-host.yml` as a valid
fork overlay, the runtime consumers (roles, tasks, inventory filters) were
all made overlay-aware — but **`scripts/generate_inventory.py` was not
updated**. It is build-time tooling, not runtime, so it was easy to miss
when ADR 0430 audited runtime consumers only.

Similarly, `make bootstrap` staging was designed before ADR 0407 / ADR
0430. Each subsequent overlay ADR added runtime knobs (identity overlay,
host_vars overlay, `env=clone` lanes) but no one tied them back to the
top-level operator command. The result: a working deployment required
either the author's environment or a bespoke wrapper.

Why the gap went undetected until now: the only fork attempt before this
(ADR 0424) used `deploy-0fork` from the start, so the bootstrap path was
never exercised against non-author hardware.

## Fix

ADR 0437 implements overlay-aware `make bootstrap`. A single environment
variable (`PLATFORM_IDENTITY_OVERLAY`) switches Makefile defaults so that
all four gaps collapse to one conditional block at the top of the
Makefile. Production behaviour is byte-identical; fork behaviour now
works off the same command.

Concrete changes:

- `scripts/generate_inventory.py` gained `--host-vars-overlay` and
  `--out` flags. The generator remains deterministic and purely
  functional.
- `Makefile` gained a top-of-file conditional that, when
  `PLATFORM_IDENTITY_OVERLAY` is set, rewires `ANSIBLE_INVENTORY`,
  `BOOTSTRAP_KEY`, `env`, `ANSIBLE_OVERLAY_EXTRA`, and
  `LV3_PROXMOX_HOST_ADDR`.
- The four bootstrap stage targets + three verify targets append
  `$(ANSIBLE_OVERLAY_EXTRA)` (empty in production).
- Stage 1 of `make bootstrap` now regenerates the overlay inventory
  into `.local/inventory/hosts.yml` before Stages 2–5 run.
- `scripts/timed.sh` promoted from `.local/` so every fork operator
  inherits the timing journal baseline by default.

## Lessons

1. **When adding an overlay machinery, audit build-time tooling too, not
   just runtime.** ADR 0430 correctly audited every runtime consumer but
   missed `scripts/generate_inventory.py`. Add a checklist item to the
   "new overlay" ADR template: "did you update every generator under
   `scripts/` that reads the overlaid path?".
2. **Documented install paths should be tested against a non-author
   environment before being published.** `README.md` and `CLAUDE.md`
   told operators to run `make bootstrap`. No CI or fork-acceptance
   test exercised that promise. Adding a `make bootstrap --check` (or a
   Docker-dev-equivalent end-to-end test for fork mode) would have
   caught this earlier.
3. **Bespoke wrappers like `deploy-0fork` are a smell.** If the fork
   operator has to use a different Make target than the documented
   one, the core contract is broken. Every fork-specific wrapper is an
   open issue against ADR 0407 "generic by default".
4. **Keep one command in the docs.** `CLAUDE.md` and `README.md` must
   never list `deploy-0fork` alongside `make bootstrap`. The fork path
   is the `PLATFORM_IDENTITY_OVERLAY=…` environment variable, not a
   different command.

## Follow-ups

- [ ] Run `PLATFORM_IDENTITY_OVERLAY=.local/identity.yml.0fork make
  bootstrap` against fork-pve-01 end-to-end; record wall-clock and rc per
  stage via `scripts/timed.sh`. Update this postmortem with the timings.
- [ ] Add a CI check that exercises `make generate-inventory --check`
  under both production and an ephemeral overlay fixture.
- [ ] Deprecate `deploy-0fork` / `converge-0fork-chain` /
  `smoke-0fork-mail` / `preflight-0fork` targets. Replace with
  deprecation warnings that redirect to `make bootstrap` /
  `make converge-site` / equivalent under the overlay.
- [ ] Extend `AGENTS.md` with a "when adding an overlay" checklist
  pointing at `scripts/` tooling.
- [ ] Consider a `make bootstrap-dry-run` that asserts the overlay
  resolves to a valid inventory without actually touching remote hosts.
