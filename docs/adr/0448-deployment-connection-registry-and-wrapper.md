# ADR 0448: Per-Deployment Connection Registry & Wrapper

> **Superseded by [ADR 0488](0488-single-deployment-per-repo-checkout.md)** (2026-05-17). The multi-deployment substrate is retired; each repo checkout now configures exactly one deployment via `.local/identity.yml`.


- Status: Superseded by ADR 0488
- Implementation Status: Implemented (Phase 1 — connection registry, deployment.connection CLI, run_with_deployment.sh wrapper, topology role auto-fill)
- Date: 2026-04-28
- Concern: multi-deployment-ergonomics, ssh-config-as-code, operator-surface, agent-friction
- Tags: multi-deployment, connection, ssh, makefile, ergonomics
- Implements: subset of [ADR 0442 — Multi-Deployment Make Interface](0442-multi-deployment-make-interface-and-worktree-binding.md)
- Depends on:
  - ADR 0440 (Per-Deployment Identity & Artifact Isolation) — implemented (ws-0445)
  - ADR 0445 Phase 1 (Multi-Deployment Hardening) — `MULTI_DEPLOYMENT_ENABLED=1` opt-in landed
- Supersedes (partially): the per-target SSH-key constants in `Makefile`
  (`ZERO_FORK_SSH_KEY`, `ZERO_FORK_DNS_ENV`, `LV3_PROXMOX_HOST_ADDR`/`PORT`
  scattered across one-off targets).

---

## Context

ADRs 0440–0442 sketch the long arc of "N independent deployments from one
checkout". 0445 Phase 1 landed the data-isolation half (every deployment
has `.local/deployments/<slug>/{identity,topology,profile}.yml`) and the
opt-in Makefile shim (`MULTI_DEPLOYMENT_ENABLED=1` resolves
`DEPLOYMENT` and threads `--deployment $(DEPLOYMENT)` into the
generators).

Two ergonomics gaps remain before "I want to converge ops-portal on the
0fork.com server" is a one-line operator command:

1. **SSH connection metadata is not per-deployment data.** Today an
   operator running anything against the 0fork box has to remember:
   `LV3_PROXMOX_HOST_ADDR=65.109.84.223`, `LV3_PROXMOX_HOST_PORT=2222`,
   `LV3_BOOTSTRAP_SSH_PRIVATE_KEY=.local/ssh/bootstrap.id_ed25519` (the
   ops-on-VM key, *not* the Hetzner-host root key). Forgetting any one
   of those produces an opaque `Connection to UNKNOWN port 65535 timed
   out` that took ~30 minutes to diagnose during the v0.179.5 ops.0fork
   recovery (2026-04-28). The `Makefile` papers over this with named
   constants (`ZERO_FORK_SSH_KEY`, `ZERO_FORK_DNS_ENV`) — one set per
   deployment, hardcoded into the committed file. Every new deployment
   = another set of constants and another bespoke target.

2. **`.local/deployments/<slug>/topology.yml` schema is too strict.**
   `scripts/generate_platform_vars.py:411` requires every
   `proxmox_guests[*]` entry to carry `role`. The committed
   `inventory/host_vars/proxmox-host.yml` provides `role` for every
   guest, but the per-deployment overlay (designed to add or override
   only what differs from committed) ends up needing to copy the entire
   structural skeleton just to clear the validator. The 0fork overlay
   shipped with bare `{name, vmid, ipv4}` entries and silently fails
   `--deployment 0fork --write` end-to-end.

Both of these block the user-stated goal: "I need to allow one or more
domains and servers to be used from this repo."

## Decision

### 1. Connection registry: `.local/deployments/<slug>/connection.yml`

A new per-deployment file (gitignored under `.local/`) describing how
to reach the deployment's Proxmox host and its guest VMs:

```yaml
# .local/deployments/<slug>/connection.yml
schema_version: 1

proxmox_host:
  addr: 65.109.84.223           # public address of the Proxmox host
  port: 2222                    # SSH port (Hetzner default 22, hardened to 2222 here)
  user: ops                     # admin user on the Proxmox host
  key: bootstrap.id_ed25519     # path under .local/ssh/ — key for SSH'ing root@<proxmox>

guest_ssh:
  user: ops                     # admin user inside guest VMs
  key: bootstrap.id_ed25519     # path under .local/ssh/ — key for ops@<vm> via ProxyCommand
  jump_user: ops                # may differ from proxmox_host.user
  jump_via: proxmox_host        # always — guests are reached by ProxyCommand through the host

# Optional — for one-shot bootstrapping flows that need direct DNS API access.
extras:
  hetzner_dns_token_path: hetzner/dns.env  # under .local/, optional
```

The schema is committed at
`config/contracts/deployment-v1/connection.schema.json` so all
deployments validate the same way.

### 2. `Deployment.connection` field + `connection` CLI subcommand

`scripts/deployment.py`'s `Deployment` dataclass gains a `connection:
dict[str, Any]` field, populated from `connection.yml` on `load()`.
Existing callers continue to work (the field is optional and defaults
to `{}` when the file is absent — matching the soft-load pattern
already used for `identity` / `topology` / `profile`).

A new CLI subcommand emits the connection details in operator-friendly
formats:

```bash
$ python3 scripts/deployment.py connection --slug 0fork --format=env
LV3_PROXMOX_HOST_ADDR=65.109.84.223
LV3_PROXMOX_HOST_PORT=2222
LV3_PROXMOX_HOST_USER=ops
LV3_BOOTSTRAP_SSH_PRIVATE_KEY=/abs/path/.local/ssh/bootstrap.id_ed25519
PLATFORM_IDENTITY_OVERLAY=/abs/path/.local/deployments/0fork/identity.yml

$ python3 scripts/deployment.py connection --slug 0fork --format=json
{ ... }
```

### 3. `scripts/run_with_deployment.sh` wrapper

A thin shell wrapper that resolves the active (or `--deployment`-passed)
slug, loads the env-var block above, and `exec`s any inner command
with that environment. Usage:

```bash
./scripts/run_with_deployment.sh --deployment 0fork \
    make configure-edge-publication env=production

./scripts/run_with_deployment.sh \
    ansible-playbook -i inventory/hosts.yml playbooks/public-edge.yml
```

This is **deliberately not a Makefile change**: ws-0445 phase 1 owns
the Makefile surface and is iterating on the multi-deployment shim.
Putting the wrapper in `scripts/` lets both efforts merge without
conflict; once ws-0445 phase 2 lands `make use-deployment slug=<slug>`,
this wrapper will be invoked from it (or merged into it).

### 4. Topology role auto-fill

`scripts/generate_platform_vars.py` defaults a `proxmox_guests[*]`
entry's `role` to its `name` when absent. This matches the committed
`proxmox-host.yml` convention (every guest's `role` equals its `name`
in production) and lets per-deployment overlay topologies remain
minimal. The committed schema continues to require `role`; the change
is one line in the loader, not the schema.

## Consequences

- Adding a new deployment is now: drop a directory under
  `.local/deployments/<slug>/` with the four YAML files, and every
  operator command works through the wrapper. No Makefile edits, no
  per-deployment constants, no env-var dance.
- `.local/deployments/<slug>/connection.yml` is the canonical place to
  look for "how do I reach this deployment". When ssh fails, the
  diagnostic question is always "is my connection.yml right?" — not
  "which of the five LV3_* env vars did I forget?".
- 0fork's topology.yml passes `--deployment 0fork --write` without
  needing to copy the full proxmox-host.yml schema.
- The wrapper is intentionally a leaf — it does not parse Makefile
  syntax, does not introduce new Make targets, and does not modify
  inventory. It composes with whatever ws-0445 phase 2 ships next.

## Migration

Existing deployments (`prod`, `0fork`):

1. Create `.local/deployments/<slug>/connection.yml` from the values
   currently hardcoded for that deployment.
2. Drop the per-deployment `LV3_PROXMOX_HOST_ADDR/PORT/...` env exports
   from operator runbooks; replace with `run_with_deployment.sh`.

The `Makefile`'s `ZERO_FORK_*` constants are not removed in this ADR —
they continue to work; this ADR just provides a generic alternative.
ws-0445 phase 2 (or a follow-up) can deprecate them once the wrapper
has soaked.

## References

- [ADR 0440 — Per-Deployment Identity & Artifact Isolation](0440-per-deployment-identity-and-artifact-isolation.md)
- [ADR 0442 — Multi-Deployment Make Interface](0442-multi-deployment-make-interface-and-worktree-binding.md)
- [ADR 0445 — Phase 1 Multi-Deployment Hardening](0445-phase1-multi-deployment-hardening.md)
- 2026-04-28 ops.0fork.com recovery (v0.179.5 release notes) — the
  ~30-minute SSH diagnostic that motivated this ADR.
