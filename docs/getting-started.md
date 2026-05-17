# Getting Started — Fork to Running Platform

This repo is forkable. A clone, one config file, and `make bootstrap` should take
you from a bare Proxmox host to a running platform on your own apex domain.

Per [ADR 0488](adr/0488-single-deployment-per-repo-checkout.md), one repo
checkout configures exactly one deployment.

## Prerequisites

1. A Proxmox VE 8 or 9 host, reachable by SSH (root or an `ops` user with sudo).
2. An apex domain you control (this guide uses `example.com`).
3. DNS pointed at the Proxmox host's public IPv4.
4. A local machine with `uv`, `make`, `python3.12+`, and `ssh` installed.

## Step 1 — clone the repo

```bash
git clone https://github.com/baditaflorin/ServerClaw.git myplatform
cd myplatform
```

## Step 2 — author `.local/identity.yml`

`.local/` is gitignored — it is where deployment-specific configuration lives
on your machine. Create the directory and the identity file:

```bash
mkdir -p .local/ssh
```

Drop your SSH private key for reaching the Proxmox host into
`.local/ssh/bootstrap.id_ed25519` (or use any filename — you'll point at it
from `identity.yml`).

Then write `.local/identity.yml`:

```yaml
# Identity — what makes this deployment yours
platform_domain: example.com
platform_operator_email: you@example.com
platform_operator_name: "Your Name"

# SSH transport to the Proxmox host (capacity_probe.py reads this)
proxmox_host_ssh:
  addr: 203.0.113.10        # the Proxmox host's public IPv4 or DNS
  port: 22                  # SSH port
  user: root                # SSH user
  key: bootstrap.id_ed25519 # filename under .local/ssh/, or absolute path

# Optional: which service profiles to enable
# (See config/sizing-policy.yml for available profile names.)
```

If you want to opt into specific service profiles, also create
`.local/profile.yml`:

```yaml
profiles:
  - core       # postgres, nginx, runtime-control — required minimum
  - devtools   # gitea, woodpecker, harbor — optional dev surface
# extra_services: [...]
# disabled_services: [...]
```

## Step 3 — bootstrap

```bash
make bootstrap
```

This runs the 14-step chain:

1. **probe-capacity** — SSHes the Proxmox host, reads RAM / CPU / disk / NVMe
   capabilities, writes `.local/capacity.yml`.
2. **resolve-topology** — fits the service set into the available envelope,
   writes `.local/topology.yml` and `inventory/host_vars/proxmox-host.generated.yml`.
3. **generate-platform-vars** — derives the rest of the inventory from your
   identity and the resolved topology.
4. **provision-guests** — creates VMs at sizes matching the host.
5-13. Service-by-service convergence in dependency order (postgres → runtime →
   edge → apps).
14. **self-check** — runs every invariant in `config/post_conditions.yml`
   against the live deployment. Anything tagged `final-smoke` must pass.

If a step fails the chain stops; fix and run `make bootstrap-resume`.

## Step 4 — verify

```bash
make self-check
```

prints a per-service pass/fail line. Exit code 0 means the deployment matches
its declared post-conditions.

## What goes where

| Path | Edited by | Lifecycle |
|---|---|---|
| `.local/identity.yml` | you (operator) | committed by you, never to public repo |
| `.local/capacity.yml` | `make probe-capacity` (generated) | regenerated each bootstrap |
| `.local/topology.yml` | `make resolve-topology` (generated) | regenerated each bootstrap |
| `inventory/host_vars/proxmox-host.generated.yml` | `make resolve-topology` (generated) | committed-style file, regenerated |
| `inventory/host_vars/proxmox-host.yml` | `make generate-platform-vars` (generated) | derived from identity + generated fragment |
| `config/sizing-policy.yml` | platform maintainers | per-service-class RAM/CPU/disk envelopes |
| `config/post_conditions.yml` | platform maintainers + you | invariants for `make self-check` |

## Common pitfalls

- **`.local/identity.yml not found`** — you skipped Step 2. Every script that
  reads identity prints the path it expected.
- **`proxmox_host_ssh.addr` missing** — your `identity.yml` has the platform
  identity but not the SSH transport block. Add the block under Step 2.
- **VM disk wants more space than the host has** — `resolve-topology` should
  shrink classes proportionally. If it OVERFLOWs, your enabled profile set is
  too rich for the host; trim `.local/profile.yml`.
- **`No such storage 'local'`** — your Proxmox storage pool name doesn't match
  the default. Override `proxmox_default_storage` in `inventory/host_vars/proxmox-host.yml`.

## Updating later

```bash
git fetch && git merge origin/main      # pull upstream platform changes
make bootstrap                          # idempotent — re-runs only what changed
```

A failed step leaves a receipt under `.local/receipts/`. `make bootstrap-status`
shows where the chain is.

## Forking the public mirror

The public mirror at <https://github.com/baditaflorin/ServerClaw> is a strict
sanitised reflection of this repo. To fork:

```bash
gh repo fork baditaflorin/ServerClaw --clone --remote
cd ServerClaw
# follow the steps above
```

Your `.local/` directory is yours to commit (to a private repo) or keep local.
The committed code uses `example.com` and `203.0.113.x` placeholders; your
identity values never leak upstream.
