# ADR 0437: Overlay-Aware `make bootstrap` — Single Command for Any Fork

> **Superseded by [ADR 0488](0488-single-deployment-per-repo-checkout.md)** (2026-05-17). The multi-deployment substrate is retired; each repo checkout now configures exactly one deployment via `.local/identity.yml`.


- Status: Superseded by ADR 0488
- Implementation Status: Complete
- Date: 2026-04-22
- Concern: forkability, operator-onboarding, one-command-deploy, iac-end-to-end, dry-principle
- Tags: bootstrap, overlay, fork-clone, adr-0386-extension, adr-0431-consolidation
- Relates to / supersedes:
  - ADR 0386 (`make bootstrap` staged bootstrap contract) — this ADR extends
    that contract with overlay awareness
  - ADR 0407 (generic-by-default / `.local/` overlay)
  - ADR 0424 (example.org clone on Hetzner AX41-NVMe)
  - ADR 0430 (`.local/host_vars/proxmox-host.yml` overlay)
  - ADR 0431 (0fork full-day deployment wrapper) — subsumed into `make
    bootstrap`; the fork-specific `deploy-0fork` / `converge-0fork-chain` /
    `smoke-0fork-mail` targets become deprecated shims

---

## Context

`make bootstrap` is the documented one-command install path in `CLAUDE.md`
and the public `README.md`:

```bash
git clone ServerClaw && cd ServerClaw
make init-local
make generate-inventory
# edit inventory/group_vars/all/identity.yml
make bootstrap
```

That contract is what lets a new operator `git clone` → working deployment
without reading 400 ADRs first.

While bootstrapping the example.org clone on a Hetzner AX41-NVMe we discovered
that the contract is **broken for forks**. Four concrete gaps surfaced when
trying to run `make bootstrap` against a host that wasn't the author's
production Proxmox:

1. **`scripts/generate_inventory.py` ignores the identity overlay.** It only
   reads `inventory/host_vars/proxmox-host.yml` — the committed production
   file. Even with `PLATFORM_IDENTITY_OVERLAY=.local/identity.yml.0fork` set,
   the generated `inventory/hosts.yml` still contains 10.10.10.X production
   IPs instead of the fork's 10.20.10.X CIDR.
2. **`BOOTSTRAP_KEY` is hardcoded** to `.local/ssh/bootstrap.id_ed25519`.
   The 0fork clone uses `hetzner_llm_agents_ed25519`; no override path
   short of editing the Makefile.
3. **`env=clone` is not threaded through Stages 2–4** of `make bootstrap`
   (`install-proxmox`, `configure-network`, `harden-access`,
   `provision-guests`). Only `converge-site` honours `$(env)` via
   `$(ANSIBLE_SCOPED_RUN) --env $(env)`. Early-stage plays default to
   `env=production`, so `playbook_execution_host_patterns` resolves to
   production hosts that don't exist on the fork.
4. **`proxmox_guest_ssh_connection_mode=proxmox_host_jump` is not set.**
   Without it, ansible tries to SSH to guests over 10.20.10.X directly
   from the operator workstation — which isn't routable until the mesh
   VPN is live.

The workaround had been to define parallel 0fork-specific Make targets
(`deploy-0fork`, `converge-0fork-chain`, `smoke-0fork-mail`,
`rotate-hetzner-dns-token`). That works for 0fork specifically but it:

- Violates the "one canonical path" intent of ADR 0386.
- Makes every future fork operator re-invent the wrapper with their own
  overlay filename.
- Drifts from the documented `make bootstrap` install instructions.

## Decision

`make bootstrap` becomes overlay-aware. The single environment variable
`PLATFORM_IDENTITY_OVERLAY` is the only switch.

### Operator contract

**Production (unchanged):**
```bash
make bootstrap
```

**Any fork:**
```bash
PLATFORM_IDENTITY_OVERLAY=.local/identity.yml.<fork> make bootstrap
```

No other environment variables required. No fork-specific Make targets.

### What changes inside `make bootstrap` when the overlay is set

At the top of the Makefile, a conditional block detects the overlay and
reconfigures four things:

| Variable | Production default | Overlay mode |
|---|---|---|
| `ANSIBLE_INVENTORY` | `inventory/hosts.yml` | `.local/inventory/hosts.yml` (regenerated) |
| `BOOTSTRAP_KEY` | `.local/ssh/bootstrap.id_ed25519` | `.local/ssh/hetzner_llm_agents_ed25519` |
| `env` | `production` | `clone` |
| `ANSIBLE_OVERLAY_EXTRA` | empty | `-e env=clone -e proxmox_guest_ssh_connection_mode=proxmox_host_jump` |
| `LV3_PROXMOX_HOST_ADDR` | unset (ansible falls back to the committed tailscale IP) | parsed from overlay's `management_ipv4` so ansible targets the fork's public IP during pre-mesh bootstrap |

All four stage targets (`install-proxmox`, `configure-network`,
`harden-access`, `provision-guests`) and the three verify targets
(`verify-bootstrap-proxmox`, `verify-bootstrap-guests`, `verify-platform`)
have `$(ANSIBLE_OVERLAY_EXTRA)` appended to their `ansible-playbook`
invocations. The extra is empty in production, so production behaviour is
unchanged.

### `scripts/generate_inventory.py` changes

Three new CLI flags:

- `--host-vars-overlay PATH` — merges an overlay host_vars dict on top of
  the base file. Semantics: top-level scalars replace base; `proxmox_guests`
  replaces the base list wholesale (matches the ADR 0430 convention that the
  `.local/host_vars` overlay is a full topology swap).
- `--out PATH` — output path for `--write`/`--check`. Defaults to
  `inventory/hosts.yml` so nothing breaks, but overlay mode writes to
  `.local/inventory/hosts.yml` instead — the fork's IPs never pollute the
  committed production inventory.

The generator stays purely functional: given (base, overlay, out_path) it
is deterministic and check-able. Production uses the two-argument form
(`--write` alone); overlay mode uses all three.

Stage 1 of `make bootstrap` calls `make generate-inventory` unconditionally;
in overlay mode that target passes the overlay flags automatically.

### Deprecation of `deploy-0fork` family

The four targets `deploy-0fork`, `converge-0fork-chain`, `smoke-0fork-mail`,
and `preflight-0fork` become thin deprecation shims that:

1. Print a deprecation warning referencing this ADR.
2. Execute the equivalent `make bootstrap` / `make converge-site` /
   `make smoke-mail` flow under the overlay.

`rotate-hetzner-dns-token` stays — it is genuinely 0fork-specific operator
tooling, not a bootstrap concern.

The ADR 0431 playbook `playbooks/0fork-full-day.yml` is redundant (it just
imports `proxmox-install.yml + site.yml + mail-platform-send-gmail.yml`, and
`site.yml` already imports `proxmox-install.yml`). It remains committed as
documentation of the 2026-04-21 deploy sequence but is no longer invoked by
the default path.

## Consequences

**Positive**

- The one-command contract from `CLAUDE.md` and `README.md` is now true
  for forks, not just for the author's environment.
- No duplicated Makefile targets per fork. Adding a new fork is just a
  new `.local/identity.yml.<name>` + `.local/host_vars/proxmox-host.yml`.
- Production behaviour is identical to before — the overlay block is only
  active when `PLATFORM_IDENTITY_OVERLAY` is set.
- `inventory/hosts.yml` stays pinned to production topology, so publishing
  to the public ServerClaw mirror continues to show the reference
  deployment without leaking fork-specific IPs.

**Negative / caveats**

- Two sources of truth for the guest network (`inventory/host_vars/` vs
  `.local/host_vars/`). Mitigated by ADR 0430's wholesale-replacement
  convention — the overlay is never merged field-by-field for
  `proxmox_guests`.
- Operators who `export PLATFORM_IDENTITY_OVERLAY` in their shell and
  forget it will silently switch to fork mode for every Make invocation.
  Mitigation: the overlay-mode banner in Stage 1 of bootstrap prints the
  overlay path, and `make generate-inventory` likewise announces which
  file it's writing to.
- `generate-inventory`'s default behaviour is unchanged, but the docs in
  `CLAUDE.md` / `AGENTS.md` must be updated to mention the overlay flag so
  agents don't get surprised by the new `--host-vars-overlay` / `--out`
  CLI.

## Validation

- Production path: `make generate-inventory --check` continues to pass
  against the committed `inventory/hosts.yml`. `make -np` in production
  mode shows `ANSIBLE_INVENTORY=inventory/hosts.yml`,
  `BOOTSTRAP_KEY=.local/ssh/bootstrap.id_ed25519`, `env=production`,
  `ANSIBLE_OVERLAY_EXTRA=` (empty).
- Fork path: `PLATFORM_IDENTITY_OVERLAY=.local/identity.yml.0fork make -np`
  shows `ANSIBLE_INVENTORY=.local/inventory/hosts.yml`,
  `BOOTSTRAP_KEY=.local/ssh/hetzner_llm_agents_ed25519`, `env=clone`,
  `ANSIBLE_OVERLAY_EXTRA=-e env=clone -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`,
  `LV3_PROXMOX_HOST_ADDR=203.0.113.3`.
- `PLATFORM_IDENTITY_OVERLAY=.local/identity.yml.0fork make generate-inventory`
  produces a `.local/inventory/hosts.yml` whose 17 guest entries resolve
  to 10.20.10.X on the fork's internal bridge.

End-to-end live-apply validation is pending on the 0fork clone (see
`docs/postmortems/2026-04-22-fork-bootstrap-gap.md`).
