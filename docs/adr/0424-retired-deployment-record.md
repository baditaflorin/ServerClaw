# ADR 0424: Retired deployment record for the example.org environment

- Status: Proposed
- Implementation Status: Pending provisioning (server delivered; no host-level changes yet)
- Date: 2026-04-21
- Concern: portability, disaster-recovery, deployment-portability, operator-identity
- Tags: secondary deployment, separate deployment, proxmox, nested-virtualisation, identity-overlay, hetzner, retired-deployment
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
ADR answers: **is the platform actually portable?** Can a second operator
(or a disaster-recovery secondary deployment of the existing operator) stand up a semantic
equivalent of `example.com` on a new domain, on a new server, from the committed
code plus the two overlay files (`.local/identity.yml`,
`inventory/host_vars/proxmox-host.yml`), without hidden chat context?

Until now the portability claim rested entirely on ADR 0385 (operator identity
core) and ADR 0407 (generic-by-default). It was never exercised end-to-end.

### The test deployment

- **New domain**: `example.org` (test zone, Hetzner DNS, already exists in the
  operator's Hetzner account with 15 default records pointing at an unrelated
  host at `88.198.219.246`)
- **New server**: Hetzner AX41-NVMe #0000000
  - IPv4: `203.0.113.3/26`, gateway derivable via Hetzner subnet math
  - IPv6: `2001:db8::4/64`
  - Region: Helsinki (HEL1) — same region as prod, different rack
  - CPU: AMD Ryzen 5 3600, 6c/12t, SVM enabled (`/dev/kvm` present, 12 virt flags)
  - RAM: 62 GiB
  - Storage: 2 × 476.9 GB Samsung NVMe (raw, no RAID configured at provisioning)
  - OS: Debian 13 trixie (English)
- **Access**: SSH ed25519 key `llm-agents@platform_server`
  (MD5 `31:31:ba:17:cf:95:c6:90:81:a8:d6:41:9c:d2:02:a3`, SHA256
  `+wOwI8QKECFX9y2hlFMfBLP1m67PC0y9PYlO8+s0isQ`)
- **Host key pinned in `known_hosts`** (ed25519
  `9xWVsKZxKXoBR3O9369Ixj/Ke/qwiLQ5SBDli/STwVk`)

### Primary vs secondary resource envelope

| Resource | Prod (203.0.113.1) | Secondary deployment (203.0.113.3) | Ratio |
|----------|----------------------|------------------------|-------|
| Physical cores / threads | Unknown / likely 16–32 | 6c / 12t | ≈ 40 % |
| RAM | ≈ 128 GiB | 62 GiB | ≈ 48 % |
| NVMe | 2 × 512 GB (RAID1) | 2 × 512 GB (raw) | 100 % raw / same after md0 |
| Declared VM cores (sum) | 84 (oversubscribed) | N/A | — |
| VM count | 17 | ≤ 8 (collapsed) | ≤ 47 % |

**Conclusion:** a faithful 1:1 deployment does not fit. The secondary deployment must be a
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
simpler portability story ("git clone the repo on a Debian, start
installing"). `/dev/nvme0n1` keeps the existing Debian install + Proxmox
layered on top; `/dev/nvme1n1` is added as a plain PVE directory datastore
for VM disks.

If either NVMe fails, the secondary environment is unavailable. Acceptable for a portability test;
unacceptable for production.

Rationale for nested Proxmox despite the tight resource envelope:
- **Faithful secondary deployment**: same abstraction layer → Ansible playbooks behave the same
- **Portability evidence**: if the secondary deployment works, the platform *is* portable
- **Disaster recovery dry-run**: rehearses the real prod-loss recovery path
- **Isolation of the experiment**: the secondary environment runs in VMs that can be destroyed
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
secondary deployment. ADR must not claim otherwise.

### 3. Domain & DNS scope — apex takeover (confirmed 2026-04-21)

The operator explicitly authorised wiping the `example.org` apex. The previous
deployment at `88.198.219.246` (default Hetzner `your-server.de` mail infra,
autoconfig, SRV records) was **destroyed** to free the apex. A full zone dump
was captured first at
`.local/hetzner/retired-deployment-apex-pre-wipe-backup-2026-04-21.json` (15 records);
restoration is a single-script replay of that JSON if reversal is ever needed.

**Apex records after wipe** (confirmed live at 2026-04-21):

- `A    example.org     → 203.0.113.3`
- `AAAA example.org     → 2001:db8::4`
- `A    *.example.org   → 203.0.113.3`   (wildcard for service subdomains)
- `AAAA *.example.org   → 2001:db8::4`
- `NS   example.org     → ns1.your-server.de. / ns.second-ns.com. / ns3.second-ns.de.` (preserved)
- `SOA  example.org     → ns1.your-server.de.` (preserved)

Service identities land on `sso.example.org`, `chat.example.org`, `ops.example.org`,
`proxmox.example.org`, etc. — a semantic 1:1 mapping of the prod `*.example.com`
hostnames under the secondary deployment apex.

MX / DKIM / SPF / DMARC are intentionally **not** re-created at wipe time —
they are published as part of the `mail-platform` VM converge (step 5 of the
execution order) so the records match the actual DKIM selector in use.

### 4. Identity overlay

Create `.local/identity.yml.retired-deployment` in the main worktree (gitignored, not in
this worktree — `.local/` is sacred, ADR 0376). Select it at runtime via an
environment variable:

```bash
export PLATFORM_IDENTITY_OVERLAY=.local/identity.yml.retired-deployment
make converge-<service> env=secondary
```

Values overridden for the secondary deployment (apex scope):

```yaml
platform_domain: example.org
platform_operator_email: operator@example.org
platform_operator_name: "Platform Operator"
hetzner_dns_zone_name: example.org
hetzner_dns_zone_id: EXAMPLE0ZoneId00000000
management_ipv4: 203.0.113.3
management_gateway4: 203.0.113.66       # verified via `ip route` on host
management_ipv6: "2001:db8::4"
hetzner_ipv4_route_network: 203.0.113.192  # /26 network base
management_interface: enp41s0
host_public_hostname: debian-base-template
proxmox_node_name: debian-base-template
platform_guest_network_cidr: 10.10.10.0/24   # different from prod's 10.10.10.0/24
platform_tailscale_tailnet_name: retired-deployment-secondary  # new, isolated from prod tailnet
```

Full overlay at `.local/identity.yml.retired-deployment` (main worktree, not committed).

### 5. Email path for this ADR's "confirmation email" deliverable

The operator asked for a confirmation email from a newly-created address on
the secondary deployment to `operator@example.com`. The secondary deployment uses the **same mail path as
prod**: Stalwart mail stack on `mail-platform` VM as primary outbound, Brevo
API bridge (`.local/mail-platform/brevo-api-key.txt`) as the delivery transport
that actually hits Gmail (new Hetzner IP reputation is poor for direct SMTP to
Gmail, as documented in ADR 0041).

Concrete flow:
1. Stalwart hosts the mailbox `operator@secondary.example.org`
2. DKIM/SPF/DMARC TXT records published on `secondary.example.org` via Hetzner DNS API
3. rDNS set on `203.0.113.3` → `mail.secondary.example.org` via Hetzner Robot
   (requires manual step — no API for rDNS in Hetzner Robot for dedicated
   servers on the legacy API; flag for operator)
4. Outbound submission via Stalwart → Brevo bridge → Gmail

The confirmation email itself is **blocked on the mail-platform VM being
deployed**. It is not a one-liner.

### 6. Execution order (strict)

1. ✅ **DONE**: DNS token + SSH access verified (this session)
2. ⏳ Operator decides: subdomain (`secondary.example.org`) vs full apex takeover
3. ⏳ Bootstrap host: hostname, Tailscale join, base hardening
   (see `docs/runbooks/hetzner-bare-metal-bootstrap.md`)
4. ⏳ mdadm RAID1, install Proxmox VE
5. ⏳ Create `.local/identity.yml.retired-deployment`, add `secondary deployment` env to
   `inventory/group_vars/`
6. ⏳ Provision the 8 VMs via existing `proxmox_guest` role
7. ⏳ Converge `runtime-control` (Keycloak first — identity anchor)
8. ⏳ Converge `postgres`, `mail-platform`, `runtime-apps`, `monitoring`
9. ⏳ Converge `nginx-edge` + public DNS records (subdomain scope only)
10. ⏳ Provision `operator@secondary.example.org` mailbox, send confirmation email
11. ⏳ Write live-apply evidence + close workstream

---

## Consequences

### Positive
- First real test of the portability claim — validates or invalidates ADR 0385.
- Produces a disaster-recovery rehearsal artifact (VM snapshots can be captured).
- Surfaces concrete gaps (e.g. `install-proxmox.md` assumes bookworm, not trixie).
- Exercises the full Hetzner DNS API integration path on a second zone.

### Negative
- Collapsed topology means the secondary deployment cannot validate full prod behavior
  (no postgres replica, no coolify — those prod-only surfaces stay unverified).
- Running nested Proxmox on 12 threads / 62 GiB RAM is tight — expect
  noisy-neighbor-style slowdowns during converge storms.
- rDNS cannot be set via API — manual Robot step is a gate (flagged in runbook).
- `example.org` apex already serves something else; the secondary deployment is scoped to a
  subdomain. Any future apex takeover is a separate, destructive decision.

### Neutral
- This ADR does not claim the secondary deployment is production-grade. It is explicitly a
  deployment-portability exercise.

---

## Rejected alternatives

- **Docker-only collapsed topology (no Proxmox)**: faster, simpler, but does
  not exercise the Ansible Proxmox layer. Rejected because portability must
  include the substrate.
- **LXC-on-Debian without Proxmox**: similar objection.
- **Matching prod 1:1**: does not fit 62 GiB / 12 threads.
- **Apex takeover of example.org**: destructive, rejected pending explicit
  operator confirmation.
- **Send confirmation email via Brevo directly (no Stalwart)**: sidesteps the
  mail stack and defeats the point of proving the secondary deployment's mail path works.

---

## Operator decisions — resolution log

1. ✅ **Apex vs subdomain**: APEX. Wipe completed 2026-04-21 with backup.
2. ✅ **Hostname**: `debian-base-template`.
3. ✅ **Gateway**: `203.0.113.66`, `/26` subnet base `203.0.113.192`
   (verified via `ssh root@203.0.113.3 'ip route'` on 2026-04-21).
4. ✅ **RAID1** via mdadm before Proxmox install.
5. ✅ **Tailscale**: new isolated tailnet `retired-deployment-secondary`, separate from prod.
6. ⏳ **Account-holder name "Mr. Raabe"** on Hetzner emails — non-blocking
   but worth confirming it's not a reseller account.
7. ⏳ **Token rotation**: the DNS token shared in chat should be rotated
   once the secondary deployment is live.

---

## Verification

- `curl -H "Auth-API-Token: $TOKEN" https://dns.hetzner.com/api/v1/zones`
  returns `example.org` with id `EXAMPLE0ZoneId00000000` — ✅ verified 2026-04-21
- `ssh -i .local/ssh/hetzner_llm_agents_ed25519 root@203.0.113.3 hostname`
  returns `debian-base-template` — ✅ verified 2026-04-21
- `/dev/kvm` present on target host — ✅ verified 2026-04-21 (nested virt viable)
- No existing DNS records on `secondary.example.org` — ✅ verified (zone dump shows
  only apex, www, and default Hetzner mail records)
