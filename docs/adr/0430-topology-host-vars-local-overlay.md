# ADR 0430: Local Overlay for `inventory/host_vars/proxmox-host.yml`

- Status: Accepted
- Implementation Status: Partial (PR 1 of N — generators only; see §Roadmap)
- Date: 2026-04-21
- Concern: forkability, deployment-specific values, generic-by-default
- Tags: forkability, overlay, iac, adr-0407-extension, adr-0424-unblock
- Relates to: ADR 0407 (`.local/` deployment values), ADR 0376 (`.local/` is sacred),
  ADR 0424 (0fork.com clone), ADR 0425 (420-ADR retrospective)

---

## Context

ADR 0425 identified that the platform is **forkable for domain + identity, not
yet forkable for the full substrate**. The 0fork.com clone attempt exposed the
concrete shape of the gap: `inventory/host_vars/proxmox-host.yml` hardcodes
prod-specific IPs, VMIDs, and hostnames into its `proxmox_guests` list. A fork
operator cannot reuse the committed file as-is — the fork has the same service
names (`nginx`, `runtime-control`, `postgres`, …) but different physical VMs
on a different subnet.

Before this ADR, the only mechanism for per-deployment overrides was
`.local/identity.yml`, which merges *scalar* values (strings, ints, bools) into
`host_vars` via `generate_platform_vars.py`. Lists and nested mappings — most
notably `proxmox_guests` — had no overlay path. A fork operator had to either:

1. Edit the committed file (breaks prod).
2. Fork the repo and diverge the file (defeats the shared-platform promise).
3. Maintain a parallel out-of-band inventory (duplicates ~1600 lines).

None are acceptable.

## Decision

Introduce a local overlay file at `.local/host_vars/proxmox-host.yml`. When
present, its top-level keys **replace wholesale** the matching keys in the
committed `inventory/host_vars/proxmox-host.yml`. Absent overlay = unchanged
committed behaviour (zero prod-impact).

Overlay semantics:

- **Replacement**, not deep-merge. If overlay defines `proxmox_guests: [...]`,
  the committed list is discarded entirely. This is unambiguous and safer for
  structured keys (e.g. port assignments, nested route tables) where a partial
  merge would be surprising.
- Keys the overlay does not mention are left untouched from the committed base.
- The overlay file is **never committed**. `.local/` is gitignored (ADR 0376)
  and a pre-commit hook enforces it.

Canonical loader: `platform.repo.load_topology_host_vars()`. Returns the merged
dict. Callers who need the raw committed file path still have
`TOPOLOGY_HOST_VARS_PATH`.

## Scope of this first PR

Only the two primary generators consume the overlay:

- `scripts/generate_platform_vars.py` — produces
  `inventory/group_vars/platform.yml`
- `scripts/generate_inventory.py` — produces `inventory/hosts.yml`

All other callers of `TOPOLOGY_HOST_VARS_PATH` (≈15 scripts, enumerated in a
follow-up) still read the committed file directly. This is intentional for
this first PR: both files they consume downstream (`platform.yml` and
`hosts.yml`) now reflect the overlay, so derived artifacts are correct.
Direct readers that need overlay-aware behaviour (e.g. live-apply tooling,
failure-domain policy) will be migrated one-per-PR.

## Consequences

### Positive
- A fork operator can now supply `.local/host_vars/proxmox-host.yml` with
  their `proxmox_guests` list and everything `platform.yml`-derived picks it
  up (DNS records, service topology, hairpin matrix, TLS certs).
- Zero behaviour change when no overlay is present: prod-safe.
- The overlay is a single file — no scattered parallel inventories.
- Committed host_vars stays as the canonical reference and example.

### Negative
- A new concept to explain to operators (one more overlay layer alongside
  `.local/identity.yml`).
- Wholesale replacement of `platform_port_assignments` or similar structured
  keys requires the operator to copy the full dict — merging would be more
  convenient but would create subtle surprises for keys the operator forgot.
- Consumers of `TOPOLOGY_HOST_VARS_PATH` that don't route through the new
  loader will see committed-only values. Drift can develop between
  overlay-aware and overlay-blind tooling until all callers are migrated.

### Neutral
- The overlay is *additive* to ADR 0407 (identity.yml). Operators keep identity
  scalars in one file and topology structures in another — cleaner separation
  than collapsing into one.

## Roadmap

This ADR is Partial because only generators consume the overlay in this PR.
Follow-up PRs (each one independently reviewable) migrate direct readers:

| Consumer | Follow-up PR | Notes |
|----------|--------------|-------|
| `scripts/environment_topology.py` | PR 4 (merged) | Used by live-apply preflight |
| `scripts/agent_tool_registry.py` | PR 4 (merged) | Agent-tool IP resolution |
| `scripts/validate_repository_data_models.py` | PR 5 (merged) | Schema drift checks |
| `scripts/failure_domain_policy.py` | PR 5 (merged) | Failure-domain reasoning |
| `scripts/service_health_tool.py` | PR 5 (merged) | Health-probe targets |
| `scripts/fixture_manager.py` | PR 6 (deferred) | Test fixtures stay committed-only so generated fixtures remain deterministic across forks (per ADR allowance) |
| `scripts/generate_cross_cutting_artifacts.py` | PR 6 (merged) | Hairpin/TLS/SSO publication |
| `scripts/control_plane_lanes.py` | PR 7 | Lane ownership |
| `scripts/validate_ephemeral_vmid.py` | PR 7 | VMID uniqueness |
| `scripts/generate_ops_portal.py` | PR 7 | Portal rendering |
| `scripts/generate_status_docs.py` | PR 7 | Status page rendering |
| `scripts/immutable_guest_replacement.py` | PR 8 | Guest replacement tooling |
| `scripts/live_apply_preflight_tool.py` | PR 8 | Live-apply preflight |

Each migration is mechanical: `load_yaml(TOPOLOGY_HOST_VARS_PATH)` becomes
`load_topology_host_vars()`. Tests verify overlay behaviour per call site.

## Alternatives considered

1. **Deep-merge overlay** — rejected. Surprise-prone for nested mappings
   where operator omits a key they thought was "implicit".
2. **Environment-selected host_vars files** (`proxmox-host.0fork.yml`
   committed alongside `proxmox-host.yml`) — rejected. Forks should not need
   to commit deployment values to the public platform repo; violates ADR 0407.
3. **Full templating** (Jinja2 in host_vars, rendered at generate time) —
   rejected. Adds a rendering step and complicates debugging. Overlay is a
   simpler model that covers the 0fork case.

## Implementation notes

- `load_topology_host_vars()` is worktree-aware via `shared_repo_root()` and
  the `.claude/worktrees/<name>/` pattern — agents in worktrees see the
  operator's overlay from the main checkout without extra configuration.
- The loader raises `TypeError` on a non-mapping overlay; no silent fallback
  to committed values on malformed input.
- Test coverage: `tests/test_generate_inventory.py` adds three cases covering
  no-overlay, replacement, and malformed-overlay behaviour.

## Cross-references

- ADR 0376 — `.local/` is sacred (never commit, pre-commit hook enforcement)
- ADR 0407 — Generic-by-default `.local/` deployment values (scalar overlay)
- ADR 0409 — Host-specific overrides (Ansible-time extra-vars merge)
- ADR 0424 — 0fork.com clone plan
- ADR 0425 — 420-ADR retrospective (identified this gap)
