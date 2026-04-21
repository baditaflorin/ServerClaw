# ADR 0424: Fork-Clone of the Platform onto a Hetzner AX41-NVMe at 0fork.com

- Status: Proposed
- Implementation Status: Pending provisioning (server delivered; no host-level changes yet)
- Date: 2026-04-21
- Concern: portability, disaster-recovery, fork-viability, operator-identity
- Tags: clone, fork, proxmox, nested-virtualisation, identity-overlay, hetzner, 0fork
- Depends on:
  - ADR 0385 (Operator Identity Core)
  - ADR 0407 (Generic-By-Default — `.local/` Deployment Values)
  - ADR 0409 (Host-Specific Overrides out of committed host_vars)
  - ADR 0376 (`.local/` Is Sacred — Incident Postmortem)
  - ADR 0419 (PR-Based Integration Flow)
- Relates to: ADR 0425 (420-ADR Platform-Build Retrospective)

---

## Context

The platform has been built over ~420 ADRs as an interactive pair-programming
session between one operator and an LLM agent. The central question this
ADR answers: **is the platform actually forkable?** Can a second operator
(or a disaster-recovery clone of the existing operator) stand up a semantic
equivalent of `lv3.org` on a new domain, on a new server, from the committed
code plus the two overlay files (`.local/identity.yml`,
`inventory/host_vars/proxmox-host.yml`), without hidden chat context?

Until now the forkability claim rested entirely on ADR 0385 (operator identity
core) and ADR 0407 (generic-by-default). It was never exercised end-to-end.

### The test deployment

- **New domain**: `0fork.com` (test zone, Hetzner DNS, already exists in the
  operator's Hetzner account with 15 default records pointing at an unrelated
  host at `88.198.219.246`)
- **New server**: Hetzner AX41-NVMe #2952989
  - IPv4: `65.109.84.223/26`, gateway derivable via Hetzner subnet math
  - IPv6: `2a01:4f9:3051:52d5::2/64`
  - Region: Helsinki (HEL1) — same region as prod, different rack
  - CPU: AMD Ryzen 5 3600, 6c/12t, SVM enabled (`/dev/kvm` present, 12 virt flags)
  - RAM: 62 GiB
  - Storage: 2 × 476.9 GB Samsung NVMe (raw, no RAID configured at provisioning)
  - OS: Debian 13 trixie (English)
- **Access**: SSH ed25519 key `llm-agents@proxmox_florin_server`
  (MD5 `31:31:ba:17:cf:95:c6:90:81:a8:d6:41:9c:d2:02:a3`, SHA256
  `+wOwI8QKECFX9y2hlFMfBLP1m67PC0y9PYlO8+s0isQ`)
- **Host key pinned in `known_hosts`** (ed25519
  `9xWVsKZxKXoBR3O9369Ixj/Ke/qwiLQ5SBDli/STwVk`)

### Prod vs clone resource envelope

| Resource | Prod (65.108.75.123) | Clone (65.109.84.223) | Ratio |
|----------|----------------------|------------------------|-------|
| Physical cores / threads | Unknown / likely 16–32 | 6c / 12t | ≈ 40 % |
| RAM | ≈ 128 GiB | 62 GiB | ≈ 48 % |
| NVMe | 2 × 512 GB (RAID1) | 2 × 512 GB (raw) | 100 % raw / same after md0 |
| Declared VM cores (sum) | 84 (oversubscribed) | N/A | — |
| VM count | 17 | ≤ 8 (collapsed) | ≤ 47 % |

**Conclusion:** a faithful 1:1 clone does not fit. The clone must be a
**collapsed topology** — same Proxmox substrate, fewer and smaller VMs.

---

## Decision

Deploy a **collapsed nested-Proxmox topology** on the AX41-NVMe, driven by the
same Ansible codebase, differentiated only by a new `.local/identity.yml`
overlay and `inventory/host_vars/proxmox-host.yml` overlay.

### 1. Substrate: Proxmox VE on top of the existing Debian 13 (no RAID, no rescue)

Follow `docs/runbooks/install-proxmox.md`, which already targets Debian 13 +
PVE 9.1 (confirmed working 2026-03-21, kernel 6.17.13-2-pve). **No mdadm RAID
is built** — the operator explicitly chose to trade disk redundancy for a
simpler forkability story ("git clone the repo on a Debian, start
installing"). `/dev/nvme0n1` keeps the existing Debian install + Proxmox
layered on top; `/dev/nvme1n1` is added as a plain PVE directory datastore
for VM disks.

If either NVMe fails, the clone is gone. Acceptable for a fork test;
unacceptable for production.

Rationale for nested Proxmox despite the tight resource envelope:
- **Faithful clone**: same abstraction layer → Ansible playbooks behave the same
- **Forkability proof**: if the clone works, the platform *is* forkable
- **Disaster recovery dry-run**: rehearses the real prod-loss recovery path
- **Isolation of the experiment**: the clone lives in VMs that can be destroyed
  without touching host config

### 2. Collapsed VM plan (≤ 8 VMs, fits 62 GiB)

| VM | vmid | Cores | RAM | Purpose | Collapses from prod |
|----|------|-------|-----|---------|---------------------|
| `nginx-edge` | 110 | 2 | 3 GiB | Public TLS termination | nginx |
| `runtime-control` | 192 | 3 | 8 GiB | Keycloak, step-ca, OpenBao, API gateway | runtime-control |
| `runtime-apps` | 122 | 4 | 16 GiB | Most application services (Outline, NetBox, Harbor, etc.) | runtime-apps + runtime-general + runtime-ai + runtime-comms |
| `postgres` | 150 | 3 | 12 GiB | Shared PostgreSQL | postgres + postgres-apps + postgres-data |
| `docker-build` | 130 | 2 | 4 GiB | Build + pre-push gate | docker-build |
| `monitoring` | 140 | 2 | 6 GiB | Grafana + Prometheus + Alertmanager + Uptime Kuma | monitoring |
| `backup` | 160 | 1 | 3 GiB | PBS agent, restic targets | backup |
| `mail-platform` | 181 | 1 | 3 GiB | Stalwart + Brevo bridge | dedicated mail (new) |

**Total requested**: 18 cores on 12 threads (1.5× oversub, fine for mostly-idle
workloads), 55 GiB RAM (headroom for PVE itself). Postgres-replica, coolify,
coolify-apps, artifact-cache are **dropped** — explicitly out of scope for the
clone. ADR must not claim otherwise.

### 3. Domain & DNS scope — apex takeover (confirmed 2026-04-21)

The operator explicitly authorised wiping the `0fork.com` apex. The previous
deployment at `88.198.219.246` (default Hetzner `your-server.de` mail infra,
autoconfig, SRV records) was **destroyed** to free the apex. A full zone dump
was captured first at
`.local/hetzner/0fork-apex-pre-wipe-backup-2026-04-21.json` (15 records);
restoration is a single-script replay of that JSON if reversal is ever needed.

**Apex records after wipe** (confirmed live at 2026-04-21):

- `A    0fork.com     → 65.109.84.223`
- `AAAA 0fork.com     → 2a01:4f9:3051:52d5::2`
- `A    *.0fork.com   → 65.109.84.223`   (wildcard for service subdomains)
- `AAAA *.0fork.com   → 2a01:4f9:3051:52d5::2`
- `NS   0fork.com     → ns1.your-server.de. / ns.second-ns.com. / ns3.second-ns.de.` (preserved)
- `SOA  0fork.com     → ns1.your-server.de.` (preserved)

Service identities land on `sso.0fork.com`, `chat.0fork.com`, `ops.0fork.com`,
`proxmox.0fork.com`, etc. — a semantic 1:1 mapping of the prod `*.lv3.org`
hostnames under the clone apex.

MX / DKIM / SPF / DMARC are intentionally **not** re-created at wipe time —
they are published as part of the `mail-platform` VM converge (step 5 of the
execution order) so the records match the actual DKIM selector in use.

### 4. Identity overlay

Create `.local/identity.yml.0fork` in the main worktree (gitignored, not in
this worktree — `.local/` is sacred, ADR 0376). Select it at runtime via an
environment variable:

```bash
export PLATFORM_IDENTITY_OVERLAY=.local/identity.yml.0fork
make converge-<service> env=clone
```

Values overridden for the clone (apex scope):

```yaml
platform_domain: 0fork.com
platform_operator_email: operator@0fork.com
platform_operator_name: "0fork Clone Operator"
hetzner_dns_zone_name: 0fork.com
hetzner_dns_zone_id: RmJf7JFvpQNfWdEZmhAeEK
management_ipv4: 65.109.84.223
management_gateway4: 65.109.84.193       # verified via `ip route` on host
management_ipv6: "2a01:4f9:3051:52d5::2"
hetzner_ipv4_route_network: 65.109.84.192  # /26 network base
management_interface: enp41s0
host_public_hostname: fork-pve-01
proxmox_node_name: fork-pve-01
platform_guest_network_cidr: 10.20.10.0/24   # different from prod's 10.10.10.0/24
platform_tailscale_tailnet_name: 0fork-clone  # new, isolated from prod tailnet
```

Full overlay at `.local/identity.yml.0fork` (main worktree, not committed).

### 5. Email path for this ADR's "confirmation email" deliverable

The operator asked for a confirmation email from a newly-created address on
the clone to `baditaflorin@gmail.com`. The clone uses the **same mail path as
prod**: Stalwart mail stack on `mail-platform` VM as primary outbound, Brevo
API bridge (`.local/mail-platform/brevo-api-key.txt`) as the delivery transport
that actually hits Gmail (new Hetzner IP reputation is poor for direct SMTP to
Gmail, as documented in ADR 0041).

Concrete flow:
1. Stalwart hosts the mailbox `operator@clone.0fork.com`
2. DKIM/SPF/DMARC TXT records published on `clone.0fork.com` via Hetzner DNS API
3. rDNS set on `65.109.84.223` → `mail.clone.0fork.com` via Hetzner Robot
   (requires manual step — no API for rDNS in Hetzner Robot for dedicated
   servers on the legacy API; flag for operator)
4. Outbound submission via Stalwart → Brevo bridge → Gmail

The confirmation email itself is **blocked on the mail-platform VM being
deployed**. It is not a one-liner.

### 6. Execution order (strict)

1. ✅ **DONE**: DNS token + SSH access verified (this session)
2. ⏳ Operator decides: subdomain (`clone.0fork.com`) vs full apex takeover
3. ⏳ Bootstrap host: hostname, Tailscale join, base hardening
   (see `docs/runbooks/hetzner-bare-metal-bootstrap.md`)
4. ⏳ mdadm RAID1, install Proxmox VE
5. ⏳ Create `.local/identity.yml.0fork`, add `clone` env to
   `inventory/group_vars/`
6. ⏳ Provision the 8 VMs via existing `proxmox_guest` role
7. ⏳ Converge `runtime-control` (Keycloak first — identity anchor)
8. ⏳ Converge `postgres`, `mail-platform`, `runtime-apps`, `monitoring`
9. ⏳ Converge `nginx-edge` + public DNS records (subdomain scope only)
10. ⏳ Provision `operator@clone.0fork.com` mailbox, send confirmation email
11. ⏳ Write live-apply evidence + close workstream

---

## Consequences

### Positive
- First real test of the forkability claim — validates or invalidates ADR 0385.
- Produces a disaster-recovery rehearsal artifact (VM snapshots can be captured).
- Surfaces concrete gaps (e.g. `install-proxmox.md` assumes bookworm, not trixie).
- Exercises the full Hetzner DNS API integration path on a second zone.

### Negative
- Collapsed topology means the clone cannot validate full prod behavior
  (no postgres replica, no coolify — those prod-only surfaces stay unverified).
- Running nested Proxmox on 12 threads / 62 GiB RAM is tight — expect
  noisy-neighbor-style slowdowns during converge storms.
- rDNS cannot be set via API — manual Robot step is a gate (flagged in runbook).
- `0fork.com` apex already serves something else; the clone is scoped to a
  subdomain. Any future apex takeover is a separate, destructive decision.

### Neutral
- This ADR does not claim the clone is production-grade. It is explicitly a
  fork-viability exercise.

---

## Rejected alternatives

- **Docker-only collapsed topology (no Proxmox)**: faster, simpler, but does
  not exercise the Ansible Proxmox layer. Rejected because forkability must
  include the substrate.
- **LXC-on-Debian without Proxmox**: similar objection.
- **Matching prod 1:1**: does not fit 62 GiB / 12 threads.
- **Apex takeover of 0fork.com**: destructive, rejected pending explicit
  operator confirmation.
- **Send confirmation email via Brevo directly (no Stalwart)**: sidesteps the
  mail stack and defeats the point of proving the clone's mail path works.

---

## Operator decisions — resolution log

1. ✅ **Apex vs subdomain**: APEX. Wipe completed 2026-04-21 with backup.
2. ✅ **Hostname**: `fork-pve-01`.
3. ✅ **Gateway**: `65.109.84.193`, `/26` subnet base `65.109.84.192`
   (verified via `ssh root@65.109.84.223 'ip route'` on 2026-04-21).
4. ✅ **RAID1** via mdadm before Proxmox install.
5. ✅ **Tailscale**: new isolated tailnet `0fork-clone`, separate from prod.
6. ⏳ **Account-holder name "Mr. Raabe"** on Hetzner emails — non-blocking
   but worth confirming it's not a reseller account.
7. ⏳ **Token rotation**: the DNS token shared in chat should be rotated
   once the clone is live.

---

## Verification

- `curl -H "Auth-API-Token: $TOKEN" https://dns.hetzner.com/api/v1/zones`
  returns `0fork.com` with id `RmJf7JFvpQNfWdEZmhAeEK` — ✅ verified 2026-04-21
- `ssh -i .local/ssh/hetzner_llm_agents_ed25519 root@65.109.84.223 hostname`
  returns `Debian-trixie-latest-amd64-base` — ✅ verified 2026-04-21
- `/dev/kvm` present on target host — ✅ verified 2026-04-21 (nested virt viable)
- No existing DNS records on `clone.0fork.com` — ✅ verified (zone dump shows
  only apex, www, and default Hetzner mail records)
