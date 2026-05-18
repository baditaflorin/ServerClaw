# ADR 0488: Single Deployment Per Repo Checkout — Generic-By-Default, Envelope-Sized

**Status**: ACCEPTED
**Date**: 2026-05-17
**Decision**: Each clone of this repo is one deployment, on one Proxmox host, with one apex domain. The multi-deployment substrate (ADRs 0437, 0439, 0440, 0441, 0442, 0443, 0445, 0446, 0448, 0456, 0457, 0458, 0459, 0460, 0462, 0470, 0480, 0481) is retired. Capacity-aware sizing (ADR 0482) becomes the only sizing path and writes directly to `inventory/host_vars/proxmox-host.yml`.

---

## Context

### What the multi-deployment substrate set out to do

ADRs 0437-0481 built a layer on top of the generic-by-default platform (ADR 0407) so that a single repo checkout could simultaneously host two deployments — `example.com` (operator's primary) and `0fork.com` (public clone) — without one polluting the other. The mechanism: a slug per deployment, `.local/deployments/<slug>/` for everything deployment-specific, `make whoami` to identify, `_require-deployment` Make prereqs to enforce, `host_pinning_guard` Ansible role to fail loud if you ran a play against the wrong host.

### Why we are unwinding it

The substrate works as designed. The problem is that the design was wrong for this codebase's actual usage.

1. **Two physical servers, not two virtual deployments on one checkout.** `0fork.com` lives on Hetzner `65.109.84.223`. `example.com` lives on Hetzner `203.0.113.1`. They were never co-located. The substrate solved "two slugs in one repo" but the real shape was "two boxes, each with their own repo checkout would be fine."

2. **The cost of the abstraction was paid every operation.** Every `make converge-*` carries `_require-deployment`. Every script has a `--deployment <slug>` arg or reads `.deployment` markers. CLAUDE.md opens with a deployment-context check before anything else. New agents spend their first turn on `make whoami` instead of working.

3. **The 2026-05-15 0fork outage was caused by drift the substrate could not see.** The 0fork host filled its root filesystem; 16 of 18 VMs paused with `io-error`; the public edge went dark for 48 hours. None of `whoami`, `host_pinning_guard`, the cert validator, or the per-deployment receipts noticed. They were all checking that *operations went to the right deployment*. None of them were checking that *the deployment was alive*. That is ADR 0484's job (self-verification contracts) — which works fine without a slug.

4. **DNS drift went undetected for the same reason.** `example.com` A-record had been mistakenly pointed at the dead 0fork box. The substrate had no opinion on which IP a domain *should* resolve to — it only validated certificates after assuming the IP was right. So `example.com` was dark in DNS for an unknown number of days while the substrate happily said "your deployment is correctly identified."

5. **Forkability is the real goal, and forkability already lives in `.local/identity.yml`.** ADR 0385 established that operators rebrand the platform by editing one file: `.local/identity.yml`. ADR 0407 made the committed code generic. Both of those work *better* without the multi-deployment layer, because there is exactly one file to edit, not a `.local/deployments/<slug>/identity.yml` and a worktree marker and a CLI flag and an env var to remember.

### What needs to change at the same time

Two things that the multi-deployment substrate hid, and that we want surfaced after the collapse:

- **Capacity-aware sizing must drive provisioning.** Today `scripts/resolve_topology.py` writes a per-deployment `topology.yml` that the provisioner does not read. `qm create` still pulls from `inventory/host_vars/proxmox-host.yml` (which carries hand-tuned VM sizes that were correct on prod hardware in 2024 and are wrong on a fresh box with different RAM/disk). The collapse is the right moment to wire the resolver's output into the canonical inventory.

- **Public-mirror genericity tightens.** ServerClaw is the public mirror. Today the committed codebase already uses `example.com` in docs and `{{ platform_domain }}` in templates (ADR 0407). After the collapse, the *one* deployment that exists in the committed repo is the canonical example — and it must read fully from `.local/identity.yml`. There must be no path where `example.com`, `0fork.com`, `65.109.84.223`, or `203.0.113.1` appear in committed code outside ADR archives.

---

## Decision

### 1. One repo checkout, one deployment, one apex

A clone of this repo is configured for exactly one deployment. The operator edits `.local/identity.yml` (the file from ADR 0385) and runs `make bootstrap`. There is no concept of "active deployment" because there is no other deployment to be inactive against.

The reference deployment in the committed codebase is `0fork.com` (the surviving box; lv3 is decommissioned per separate decision). All committed examples, fixtures, and documentation use `example.com` and `203.0.113.x` placeholders per ADR 0407. The publish-to-ServerClaw pipeline (which sanitises `example.com → example.com` today) is simplified — its only job becomes sanitising whatever real values may have crept into committed files, not maintaining a private↔public diff of identity scaffolding.

### 2. The substrate is removed, not soft-disabled

Removing the multi-deployment layer means actually deleting it from the tree, not gating it behind a flag. A flagged version would still impose its mental cost on agents reading the code.

Removed in full:

| Removed | Replaced by |
|---|---|
| `mk/multi-deployment.mk` | nothing — converge targets just run |
| `scripts/deployment.py` | nothing |
| `scripts/migrate_to_multi_deployment.py` | nothing (one-shot, already run) |
| `.local/deployments/<slug>/` | `.local/identity.yml` directly (ADR 0385's original layout) |
| `host_pinning_guard` Ansible role | nothing — one box, no risk of wrong-host |
| `reference-deployments/` catalog + templates | nothing |
| `config/contracts/deployment-v1/profile.schema.json` and `connection.schema.json` | dropped (multi-deploy concepts) |
| `config/contracts/deployment-v1/identity.schema.json` and `topology.schema.json` | **kept** — still useful for single-deploy validation |
| `tests/fixtures/deployments/{minimal,host-pinned,multi-host}/` | dropped |
| `tests/test_adr_0439_multi_deployment.py`, `tests/test_adr_0440_phase2_generators.py`, `tests/test_ws0461_cert_validator_multi_deployment.py`, `tests/test_ws0472_deployment_fixture_matrix.py` | dropped |
| Per-deployment receipt subdirectories | flattened to `receipts/live-applies/` |
| `.deployment` worktree markers | gitignored, stop being written |
| CLAUDE.md §0 (the `make whoami` ritual) | deleted |
| 17 ADRs (0437, 0439-0443, 0445-0448, 0456-0460, 0462, 0470, 0480, 0481) | marked `Status: Superseded by ADR 0488` |
| Workstreams `ws-0481`, `ws-0482-0fork-platform-not-bootstrapped`, `ws-0486-hands-off-bootstrap` (the slug-aware parts) | retired; ws-0483/0484/0485 rebased to drop deployment scaffolding from `owned_surfaces` |

The 17 ADRs are preserved as historical record. The platform-manifest validator (ADR 0420) is updated so they do not register as "active decisions" against the current code.

### 3. Capacity-aware sizing becomes the only sizing path (ADR 0482 actualized)

The `scripts/capacity_probe.py` → `scripts/resolve_topology.py` chain is rewired:

- `capacity_probe.py` reads SSH target from `.local/identity.yml` (not `.local/deployments/<slug>/connection.yml`). Output: `.local/capacity.yml`.
- `resolve_topology.py` consumes `.local/capacity.yml` + `config/sizing-policy.yml` (per-service min/max envelopes) + `.local/identity.yml` (which services are wanted). Output: a generated fragment `inventory/host_vars/proxmox-host.generated.yml`.
- `inventory/host_vars/proxmox-host.yml` becomes a thin file that `include_vars`'s the generated fragment, plus any operator overrides above it.
- `make bootstrap` (ADR 0483) runs `probe-capacity` → `resolve-topology` → `generate-platform-vars` → `provision-guests` in that order.

A fresh clone on a new Hetzner box with 64 GB RAM and a single 1 TB NVMe produces a topology where postgres gets enough RAM, no VM disk image exceeds the available physical space, and the provisioner sees a coherent inventory. The 2026-05-15 outage (postgres-vm allocated a 640 GB raw image on a 436 GB host filesystem because the inherited prod sizing was wrong for the new hardware) becomes mechanically impossible.

### 4. Generic-by-default is enforced, not advised

ADR 0407 said "use `example.com` in docs, `{{ platform_domain }}` in templates." This ADR upgrades that from convention to enforcement:

- A pre-commit hook (extending `scripts/audit_sanitization.py`) blocks commits where committed files outside `docs/adr/` mention `example.com`, `0fork.com`, `65.109.84.223`, `203.0.113.1`, or any operator-specific identity.
- All identity values resolve through `.local/identity.yml` (`platform_domain`, `platform_operator_email`, etc.). A converge target with no `.local/identity.yml` exits with `error: edit .local/identity.yml to configure your deployment (see docs/getting-started.md)` — not with a half-baked converge against placeholder values.
- The `reference-deployments/` directory is removed; the *committed code itself* is the reference deployment template. To fork: clone, fill in `.local/identity.yml`, `make bootstrap`.

### 5. Receipts and workstreams stay, scoped to one deployment

`receipts/live-applies/` keeps the flat layout that existed before ADR 0440 added `by-deployment/`. Workstreams keep their `deployment:` field for a one-release transition window, but it is informational only (no validator enforces it) and is removed in the release after this one.

---

## Consequences

### Positive

- **Agents start working immediately.** No `make whoami` ritual, no worktree marker check, no `_require-deployment` failure mode to diagnose.
- **Forkability is one file.** `cp -r repo myfork && edit .local/identity.yml && make bootstrap`. Documented exactly the way ADR 0385 originally intended.
- **The 2026-05-15 outage class becomes mechanically impossible.** Capacity-aware sizing on every bootstrap means VM disks fit their host. Self-verification (ADR 0484) catches storage pressure as a post-condition.
- **~5,000 lines deleted, ~3,200 lines of ADR text marked Superseded.** Less code to maintain, smaller surface for the publish pipeline to sanitise.
- **Public-mirror diff shrinks.** Fewer file-rewrites between private and public means more reviewable releases.

### Negative

- **No more two-deployments-per-checkout.** If we ever genuinely want to run two parallel deployments off one repo again, we re-introduce the substrate. The 17 superseded ADRs remain as the design notebook for that day.
- **example.com is end-of-life as a deployment.** Its box at 203.0.113.1 either gets repurposed or wiped. The committed code no longer carries lv3-specific topology.
- **`make bootstrap` against an existing deployment must be idempotent.** ADR 0485 (convergence idempotency tests) becomes load-bearing rather than aspirational; we must implement it in this release.
- **Operators with multiple Proxmox boxes maintain one checkout per box.** This matches how every other Ansible-managed infrastructure project at this scale operates, but it is a change from the substrate's promise.

### Migration order (this PR)

This ADR is delivered in one branch, mergeable in stages if review prefers:

1. **Deletion stage:** remove `mk/multi-deployment.mk`, `scripts/deployment.py`, `scripts/migrate_to_multi_deployment.py`, `host_pinning_guard` role, `reference-deployments/`, multi-deploy test files and fixtures. Strip `_require-deployment` from every Make target. Drop `include $(REPO_ROOT)/mk/multi-deployment.mk` from `Makefile`.
2. **Identity collapse stage:** move `.local/deployments/0fork/identity.yml` content to `.local/identity.yml` on the operator's machine (manual, not in this PR — `.local/` is gitignored). Delete `.local/deployments/` from the substrate plan. Remove `PLATFORM_IDENTITY_OVERLAY` env-var handling.
3. **Capacity-aware rewire stage:** repoint `capacity_probe.py` and `resolve_topology.py` at `.local/identity.yml` and `inventory/host_vars/proxmox-host.generated.yml`. Add `make generate-platform-vars` step that includes the generated fragment.
4. **Documentation stage:** rewrite CLAUDE.md (delete §0, simplify §1, fold relevant parts of §0 into a one-line "the deployment is configured in `.local/identity.yml`"). Mark superseded ADRs. Update `README.md` getting-started.
5. **Enforcement stage:** extend `scripts/audit_sanitization.py` to block operator-specific strings in committed files outside `docs/adr/`.

### Out of scope

- Decommissioning the lv3 box (operational task, separate change ticket).
- Rebuilding the 0fork box from scratch on the simplified branch (operational task — uses this branch but is not part of it).
- DNS flip for `example.com` (registrar change, not a repo change).

---

## Related ADRs

- **Supersedes**: 0437, 0439, 0440, 0441, 0442, 0443, 0445, 0446, 0448, 0456, 0457, 0458, 0459, 0460, 0462, 0470, 0480, 0481
- **Builds on**: 0385 (one identity file), 0407 (generic-by-default), 0420 (receipt schema)
- **Actualizes**: 0482 (capacity-aware sizing now drives provisioning), 0483 (hands-off bootstrap simplified), 0484 (self-verification covers the gap multi-deployment didn't), 0485 (idempotency tests become load-bearing)
