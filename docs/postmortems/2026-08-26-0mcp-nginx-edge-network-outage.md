# 2026-08-26: example.org fleet-wide public HTTPS outage — nginx-edge stuck on stale pre-migration addressing

> **CORRECTION (2026-08-27), read this first:** everything below through
> "Follow-ups" frames `10.10.10.x` as the correct/current addressing and
> `10.10.10.x` as stale. **That direction was wrong.** The operator
> confirmed the real example.org fleet has always run on `10.10.10.x` — 16 of
> 17 guests were never on `10.10.10.x` at all, and nginx-edge's move to
> `10.10.10.x` on 2026-08-26 (described as "the fix" below) was itself the
> mistake, later reverted. The actual root cause was that the IaC's
> `proxmox_internal_network`/`proxmox_staging_network` declarations were
> inverted relative to physical reality. See "Update 2026-08-27: the
> direction was backwards — corrected" at the end of this document for
> what's actually true and what was actually done.

## Impact

All public HTTPS on the example.org fleet (`headscale.example.org`, `ci.example.org`,
`apps.example.org`, and any other domain proxied through nginx-edge) was
unreachable from the public internet for at least ~2 hours (first confirmed
broken ~14:50 UTC, fixed ~19:00 UTC). SSH and internal Tailscale-routed
traffic were unaffected. The proximate trigger for investigating was
ServerClaw's Woodpecker CI webhook consistently failing to deliver
(`failed to connect to host`), but the outage was fleet-wide, not specific
to CI.

## Root cause

nginx-edge (Proxmox VMID 110, hostname `nginx-lv3`) was still configured
with a stale, pre-migration network identity:

- Live netplan (`/etc/netplan/50-cloud-init.yaml`): `10.10.10.10/24`,
  gateway `10.10.10.1`, DNS search `0mpc.com`.
- Proxmox VM config (`ipconfig0`, `searchdomain`): same stale values,
  baked in as the cloud-init datasource.
- Proxmox bridge: `vmbr20` (the bridge that actually carries `10.10.10.0/24`).

Meanwhile, the fleet's declared IaC (`inventory/host_vars/proxmox-host.yml`,
`proxmox_guests[vmid=110]`) and the Proxmox host's own nftables NAT/forward
rules (DNAT `203.0.113.1:80/443` → `10.10.10.10`, forward-accept for
`10.10.10.10:80/443`) both expect the *new* addressing: `10.10.10.10/24`,
gateway `10.10.10.1`. The route for `10.10.10.0/24` on the host pointed at
`vmbr10` — a bridge with zero members and `NO-CARRIER`.

So: every inbound public request got correctly DNAT'd to `10.10.10.10`, the
host tried to deliver it via `vmbr10`, ARP for `10.10.10.10` on that bridge
never resolved (nothing was ever plugged into it), and the packet vanished
with no response — indistinguishable from the outside from a firewall drop
or an upstream network block. Locally, on nginx-edge itself, everything
looked fine (nginx served requests over loopback correctly), which is why
this wasn't caught by a from-the-host health check.

This is a **fleet-wide incomplete migration**, not a one-off nginx bug: the
host's networking layer (NAT rules, IaC declarations) was updated at some
point from an older `10.10.10.x` / `0mpc.com` addressing scheme to the
current `10.10.10.x` / `example.org` one, but the actual running guest VMs'
own network configs were never migrated to match. `~/.ssh/config.d/0mcp.conf`
independently confirms this: its header claims `10.10.10.0/24` is prod and
`10.10.10.0/24` is unprovisioned staging, but every "prod" guest alias in
that same file (`0mcp_nginx`, `0mcp_docker`, `0mcp_comms`, ... down to
`0mcp_runtime_control`) is configured with a `10.10.10.x` address — because
that's what actually worked when the file was written. nginx-edge is the
only guest where this drift became externally visible, since it's the
fleet's sole public ingress point; the others may be internally
self-consistent on `10.10.10.x` and functioning fine for their own purposes,
or may have the same latent issue without yet manifesting as a visible
outage.

## Fix

On VMID 110, live and in this order (to avoid losing guest-agent access if
networking briefly broke mid-change):

1. Backed up `/etc/netplan/50-cloud-init.yaml`.
2. Rewrote it via `qm guest exec` (network-independent) to
   `10.10.10.10/24`, gateway `10.10.10.1`, DNS search `example.org`.
3. `qm guest exec 110 -- netplan apply`.
4. `qm set 110 -net0 ...,bridge=vmbr10,firewall=0` (was `vmbr20`).
5. For durability across a reboot: `qm set 110 --ipconfig0
   ip=10.10.10.10/24,gw=10.10.10.1 --searchdomain example.org` (the VM's own
   cloud-init datasource, which was still baked with the stale values and
   would have silently reverted the fix on next boot).

Verified: `headscale.example.org` back to `200`; `apps.example.org` and
`ci.example.org` now return `502` instead of connection failures (their own
upstreams — Woodpecker's container, etc. — have a separate, pre-existing
problem, out of scope here); GitHub's webhook delivery to ServerClaw now
gets a real `502` response instead of `failed to connect to host`.

Also fixed: `~/.ssh/config.d/0mcp.conf`'s `0mcp_nginx` alias, which pointed
at the now-stale `10.10.10.10` and would otherwise have started failing the
moment this fix landed.

## What went wrong along the way

An earlier attempt at this fix (`qm set` to move the bridge to `vmbr10`
*without* first fixing netplan) was validated using the SSH alias above —
which itself still pointed at the old `10.10.10.10` address. That "test"
correctly showed the alias broke (since the guest had moved off the bridge
serving that address) and was misread as "the fix broke something,"
triggering an unnecessary revert-and-reinvestigate cycle. Lesson: when
validating a network identity change, check the actual declared/intended
address, not a tool whose config might share the same stale assumption
being fixed.

## Update 2026-08-27: audited every other guest — this is fleet-wide

Checked all 17 declared guests (`qm guest exec <vmid> -- cat
/etc/netplan/50-cloud-init.yaml`, plus `qm config <vmid> | grep bridge`)
against the IaC's declared `ipv4`/`gateway4`. **VMID 110 (nginx) is the
only one migrated.** All 16 others are still fully on the stale
`10.10.10.x` / `0mpc.com` identity, on `bridge=vmbr20`:

| VMID | Role | Declared (IaC) | Live netplan | Bridge |
| --- | --- | --- | --- | --- |
| 110 | nginx | 10.10.10.10 | **10.10.10.10** (fixed) | vmbr10 |
| 120 | docker-runtime | 10.10.10.20 | 10.10.10.20 | vmbr20 |
| 121 | runtime-comms | 10.10.10.21 | 10.10.10.21 | vmbr20 |
| 122 | runtime-apps | 10.10.10.22 | 10.10.10.22 | vmbr20 |
| 130 | docker-build | 10.10.10.30 | 10.10.10.30 | vmbr20 |
| 140 | monitoring | 10.10.10.40 | 10.10.10.40 | vmbr20 |
| 150 | postgres | 10.10.10.50 | 10.10.10.50 | vmbr20 |
| 151 | postgres-replica | 10.10.10.51 | 10.10.10.51 | vmbr20 |
| 152 | postgres-apps | 10.10.10.52 | 10.10.10.52 | vmbr20 |
| 154 | postgres-data | 10.10.10.54 | 10.10.10.54 | vmbr20 |
| 160 | backup | 10.10.10.60 | 10.10.10.60 | vmbr20 |
| 170 | coolify | 10.10.10.70 | 10.10.10.70 | vmbr20 |
| 171 | coolify-apps | 10.10.10.71 | 10.10.10.71 | vmbr20 |
| 180 | artifact-cache | 10.10.10.80 | 10.10.10.80 | vmbr20 |
| 190 | runtime-ai | 10.10.10.90 | 10.10.10.90 | vmbr20 |
| 191 | runtime-general | 10.10.10.91 | 10.10.10.91 | vmbr20 |
| 192 | runtime-control | 10.10.10.92 | 10.10.10.92 | vmbr20 |

All guest hostnames still carry a `-lv3` suffix (`nginx-lv3`,
`docker-runtime-lv3`, ...), confirming the whole fleet was provisioned
under the old identity and the rename/renumber to `example.org`/`10.10.10.x`
was only ever applied to the host's own NAT rules, the IaC, and (as of this
incident) VMID 110 — never rolled out to the other 16 guests.

**This is not just latent risk — it's causing other live, previously
unnoticed outages.** The host's own DNAT/forward rules public-forward
several ports straight to guests that are still unreachable at their
declared address:

- `25/587/993` (SMTP/submission/IMAPS) → `10.10.10.92` (runtime-control,
  VMID 192, mail platform) — confirmed timing out externally.
- `7881/7882` (LiveKit, TCP+UDP) → `10.10.10.20` (docker-runtime, VMID 120)
  — confirmed timing out externally.
- `8080` → `10.10.10.41` — no VMID in the current fleet maps to this
  address; either an orphaned rule or an unprovisioned/renamed guest, not
  investigated further.
- `8443` → `10.10.10.100` (hermes-agent) — this guest is currently
  **stopped** (unrelated to the addressing drift; a separate, unexplained
  fact worth checking on its own).

Not fixed here — remediating all 16 remaining guests is a materially
different scope of change (mail bounce risk during the cutover window,
possible internal inter-guest dependencies on the current `10.10.10.x`
addresses that would need checking guest-by-guest first) and needs its own
deliberate pass rather than a blind repeat of VMID 110's fix.

## Follow-ups (not done here, out of scope for this incident)

- Migrate the remaining 16 guests (table above) the same way VMID 110 was
  fixed: netplan + cloud-init config + bridge, guest by guest, checking
  each one's actual current inter-guest dependencies first given the mail
  and LiveKit exposure.
- Resolve the currently-broken public mail (25/587/993) and LiveKit
  (7881/7882) once their guests are migrated.
- Figure out what (if anything) `10.10.10.41`/port 8080 is supposed to be,
  and why `hermes-agent` (VMID 100) is stopped.
- `ci.example.org` and `apps.example.org`'s `502`s (Woodpecker's backend at
  `10.10.10.20:8102` and whatever serves `apps.example.org`) are real,
  separate, still-unfixed issues.
- `vmbr10` should probably be renamed/removed or documented if it's meant
  to be the "real" `10.10.10.x` bridge going forward — right now nothing
  else uses it except VMID 110.
- The stale `0mpc.com` DNS search domain and its ~25 expired/failing
  certificates (noted in the 2026-08-26 ServerClaw publish postmortem) are
  likely the same migration's other unfinished half.

## Update 2026-08-27: the direction was backwards — corrected

Operator directive: "all from 0mcp needs to become on 10.20.xx.xx." This
flips the entire framing above. Root-caused why:

`inventory/host_vars/proxmox-host.yml` declared `proxmox_internal_network:
10.10.10.0/24` (labeled "production") and `proxmox_staging_network:
10.10.10.0/24` (labeled "staging"). This labeling was **inverted relative
to physical reality**: no separate staging VMs were ever provisioned (the
`-staging` suffixed inventory entries — `nginx-staging`,
`docker-runtime-staging`, etc. — are generated placeholders with no real
VM behind them), and the single, real guest set has always run on
`10.10.10.x`. `10.10.10.x` was only ever live on ONE guest — nginx-edge,
and only because of the 2026-08-26 fix described above, itself now
reverted.

**Fixed at the source** (`platform_server#137`): swapped
`proxmox_internal_*` ↔ `proxmox_staging_*` (network/bridge/ipv4/cidr) in
`inventory/host_vars/proxmox-host.yml`, updated `proxmox_public_edge_ipv4`
and all 17 `proxmox_guests[].ipv4`/`.gateway4` entries (plus
`backup_vm_ipv4` and the 3 `postgres_ha.vip_ipv4` references) to
`10.10.10.x`, and `identity.yml`'s `platform_guest_network_cidr`/`_prefix`/
`_wildcard` to match. Regenerated `inventory/hosts.yml` — confirmed no
`ansible_host` collisions between the now-swapped production (`10.10.10.x`)
and staging (`10.10.10.x`) host groups. `inventory/group_vars/platform.yml`
was deliberately left unregenerated: this machine's `.local` overlay is
pointed at an unrelated deployment (`active-deployment: 0fork`, a
different physical server entirely) and regenerating it here pulls in
example.org's real values — confirmed via `git stash` that this validation
already fails on clean `main` for the same reason, independent of this fix.

**Live fix, applied in this order** (nginx-edge first, so the host's NAT
rules and the guest they point at move together):

1. Reverted nginx-edge's netplan back to `10.10.10.10/24`, gateway
   `10.10.10.1` (kept the DNS search domain as `example.org`, not reverting
   that part — it's correct and unrelated to the addressing question).
2. `qm set 110 -net0 ...,bridge=vmbr20,...` (back from `vmbr10`).
3. `qm set 110 --ipconfig0 ip=10.10.10.10/24,gw=10.10.10.1` for reboot
   durability.
4. Rendered the `nftables.conf.j2` template locally using the corrected
   source variables (resolving the `proxmox_guests`-derived `target_host`
   lookups by hand), diffed it against live, and applied it via `nft -c -f`
   (syntax check) then `nft -f` (atomic reload) on the bastion.

**Verified**: `headscale.example.org` → `200`. `ci.example.org`/`apps.example.org`
→ `502` (their own separate, pre-existing backend issues, unchanged from
before). `~/.ssh/config.d/0mcp.conf`'s `0mcp_nginx` alias and its
misleading header comment corrected back to `10.10.10.x`.

**New finding while re-verifying mail/LiveKit**: with the addressing fixed,
mail (25/587/993 → `runtime-control`) is confirmed reachable
**internally** — `nc` from the bastion to `10.10.10.92:25` succeeds, and
the mail container's own Docker NAT counters show the packet arriving.
But it's still unreachable **externally** (`nc 203.0.113.1 25/587/993`
all time out) — this is not an addressing problem, and matches Hetzner's
well-known default practice of blocking inbound SMTP-family ports on
dedicated servers until the customer requests them unblocked. Needs a
Hetzner support ticket, not anything fixable via SSH/nftables.

LiveKit (7881/7882 → `runtime-comms`) is a **different, separate problem**:
nothing is listening on port 7881 on `runtime-comms` at all (`ss -tlnp`
empty, no LiveKit container in `docker ps`) — the service simply isn't
running there, unrelated to networking entirely.

## Update 2026-08-27, later: apps.example.org root cause found — fleet-pool-fw missed the forward chain

`apps.example.org` (→ `coolify-apps`, VMID 171) stayed broken through a
container restart, a Docker daemon restart, a full VM reboot, and a bridge
FDB cleanup (a real but unrelated MAC-learning glitch found along the way).
None of it worked because none of it was the actual cause.

Root-caused via `nft monitor trace` on a live test packet: the SYN from
nginx-edge correctly traverses DNAT and every Docker chain
(`DOCKER`/`DOCKER-USER`/`DOCKER-ISOLATION-STAGE-1`) and gets an explicit
`accept` there — then falls through to a **separate** `inet filter forward`
chain (the guest's own hand-authored security policy, hooked at the same
priority) whose `policy drop` silently ate it, because its source-IP
allow-list only had the old `10.10.10.x` addresses, never `10.10.10.10`.

This chain only governs **Docker-published-port / forwarded** traffic —
host-bound services (like mail on 25/587/993, `tcp dport {...} accept`
with no source restriction) go through the `input` chain instead, which
*did* get updated. That's why the 2026-08-27 `pve-firewall` restart fixed
mail but did nothing for this: mail was never gated by this rule at all,
and this rule was never touched by anything that ran.

The gap: the "fleet-pool-fw" auto-migration (`/etc/nftables.conf`, marked
`# BEGIN fleet-pool-fw (generated from firewall-pools.json -- edit that,
not this)`, dated 2026-08-26) updated the `input` chain's source-IP
allow-list to `10.10.10.x` but **never touched the `forward` chain** —
confirmed on both guests that have this per-source-IP forward policy
(`coolify-apps` VMID 171, `runtime-control` VMID 192). **Correction
(2026-08-27, later still): the claim that the other 15 guests were
unaffected was wrong** — see the "fleet-wide sweep" section below;
every running guest had this gap. `firewall-pools.json` itself is still
not located anywhere in this repo, ServerClaw, or org-wide code search —
same unresolved mystery noted in [[project_fleet_firewall_drift_incident]].

Fixed live (`nft add rule`) and persisted to `/etc/nftables.conf` on both
guests (backed up first, syntax-checked with `nft -c -f` before trusting
it) — but **not reloaded from the file**, since it starts with `flush
ruleset` and would wipe Docker's own dynamically-generated NAT/isolation
chains out from under the currently-running containers. It takes effect
naturally on next boot, when Docker also regenerates its own rules fresh.
`coolify-apps` only needed 3 addresses (its own forward policy is
narrower); `runtime-control` needed all 17 guest addresses mirrored from
its already-correct `input` chain.

Verified: `apps.example.org` → `302` (normal SSO redirect). All previously
working services (`ci`, `app`, `headscale`) unaffected.

### Follow-up

- Whatever generates the fleet-pool-fw block from `firewall-pools.json`
  needs to migrate `forward` chains, not just `input` — otherwise this
  exact gap reappears on the next auto-migration for any guest with a
  per-source-IP forward policy.
- The two live-patched `/etc/nftables.conf` files carry a manual
  "Reconcile with firewall-pools.json" comment block pending that fix.

## Update 2026-08-27, later still: fleet-wide sweep — the gap was on all 17 guests, not 2

The `coolify-apps`/`runtime-control` assessment above understated the
scope. Auditing every running guest's `inet filter forward` chain (`qm
list` → 17 running VMIDs, `nft list chain inet filter forward` on each)
found the identical pattern on **all 15 remaining guests**: every
per-source-IP `accept` rule in their `forward` chains still only listed
`10.10.10.x`, with zero `10.10.10.x` counterparts. The earlier claim that
"the other 15 guests' forward chains only match broad subnets" was simply
wrong — several (`docker-runtime-lv3`, `monitoring-lv3`,
`runtime-ai-lv3`, `runtime-general-lv3`) have dense per-host allow-lists
covering most of the fleet.

Why this hadn't surfaced as more outages yet: any connection opened
*before* the 2026-08-26 migration kept flowing via conntrack's `ct state
established,related accept` rule (present in every chain, unaffected by
source-IP matching). Only *new* connections from `10.10.10.x` peers over
Docker-published ports would have hit the default-drop policy — which is
exactly the shape of the `apps.example.org` failure (nginx-edge opening a
fresh proxy connection).

Fixed guest by guest (canary first, then sequentially, verifying after
each — not batched) in this order: `docker-build-lv3` (130, canary — 3
rules), `artifact-cache-lv3` (180, 4 rules), `nginx-lv3` (110, 1 rule),
`backup-lv3` (160, 3 rules), `monitoring-lv3` (140, 32 rules),
`coolify-lv3` (170, 3 rules), `runtime-ai-lv3` (190, 17 rules),
`runtime-general-lv3` (191, 17 rules), `runtime-comms-lv3` (121, 8 rules),
`runtime-apps-lv3` (122, 5 rules), `docker-runtime-lv3` (120, 17 rules
after dedup — this guest's forward chain had accumulated heavy rule
duplication from repeated prior migrations; left the existing duplicates
alone and only added the missing `10.10.10.x` mirrors, staying strictly
additive), then the 4 Postgres nodes last as the highest-risk group:
`postgres-lv3` (150, 7 rules), `postgres-replica-lv3` (151, 4 rules),
`postgres-apps-lv3` (152, 6 rules), `postgres-data-lv3` (154, 5 rules).

Method per guest, identical to the original two-guest fix: parse the live
`nft list chain inet filter forward` output, generate the `10.10.10.x`
mirror of each existing `10.10.10.x` rule (same port/protocol match
conditions, skipping anything already present), apply live via `nft add
rule` first, verify, then persist into `/etc/nftables.conf` (backed up
with a timestamped suffix, inserted with a comment header explaining the
gap, syntax-checked with `nft -c -f`) — never reloaded live, same
Docker-NAT-chain-clobbering reason as before. Automated with a small
Python script (dry-run by default, `--apply` to commit) so every guest got
the exact same treatment instead of hand-edited one-offs.

Side finding, not caused by and not fixed by this bug: the 4 Postgres
guests' `forward` chains reference etcd (2379/2380), a Patroni REST API
(8008), and keepalived VRRP for an HA setup — but `postgresql@17-main` is
the only running service on any of them (`no patronictl`, no Docker, no
etcd/Patroni/keepalived processes, nothing listening on those ports; every
node reports `pg_is_in_recovery() = f` with an empty
`pg_stat_replication`). This HA tooling was apparently never actually
deployed — the firewall rules are provisioned for an architecture that
doesn't exist yet. Not addressed here; flagging for whoever owns the
Postgres HA rollout.

Verified after the full sweep: a dry-run of the same script against all
17 guests reports zero remaining gaps everywhere. External spot-check
(`app.example.org` 200, `ci.example.org` 200, `grafana.example.org` 302,
`n8n.example.org` 302) and Postgres replication-status queries on all 4 DB
nodes (unaffected, as expected since they're standalone) confirm no
regressions from the change.

### Follow-up (updated)

- Same as above: `firewall-pools.json`'s generator needs to migrate
  `forward` chains, not just `input`, or this reappears fleet-wide on the
  next auto-migration.
- All 17 running guests' `/etc/nftables.conf` now carry the same
  "Reconcile with firewall-pools.json" comment block pending that fix.
- Separately: the Postgres HA stack (etcd/Patroni/keepalived) referenced
  by the firewall rules was never actually deployed — worth a decision on
  whether to build it out or strip the now-unused HA-only firewall rules.

## Update 2026-08-27, later still: reboot-verification campaign — root-caused the Docker-wipe bug, found real Postgres corruption

Rebooted all 17 running guests one at a time (canary first, then
sequentially, Postgres nodes last) to confirm the forward-chain fix
survives a reboot, not just a live `nft add rule`. It does, on all 17 —
final dry-run sweep after every reboot reports zero remaining gaps. Two
unrelated, real, pre-existing bugs surfaced along the way.

### Bug 1: Docker doesn't reliably survive a reboot, and a reboot can wipe every container and image

First seen on `docker-runtime` (VMID 120): `docker.service` started
normally at boot, ran for ~30s, then cleanly stopped itself
(`Deactivated successfully`) — the same pattern already seen once this
session on `coolify-apps` during the original incident. Manually
restarting the daemon brought it back, but every container *and every
locally-cached image* was gone — not just stopped, entirely absent from
`docker ps -a` / `docker images`, despite `/var/lib/docker/containers/`
still holding 66 leftover directories on disk.

Root cause, confirmed via timing correlation and reproduction:
`cloud-init`'s `package-update-upgrade-install` module (`frequency:
once-per-instance`) has never completed successfully on several guests —
its cached `sem/config_package_update_upgrade_install` marker records
`FAIL`, so it retries the *entire* package install (`docker.io,
ca-certificates, qemu-guest-agent, sudo, jq, curl`) on **every single
boot**. The failure traces to an interrupted initial-provisioning dpkg
transaction that left ~19 packages "not fully installed or removed" on
that guest. Reinstalling/reconfiguring `docker.io` mid-boot (rewriting
`/etc/default/docker`, `/etc/init.d/docker`) lands right on top of the
freshly-started daemon — on `docker-runtime`, `docker.service`'s stop at
13:05:28 falls exactly inside cloud-init's own logged install window
(13:05:00–13:05:30). Reproduced identically on `coolify-apps` earlier in
this same session.

Not fully explained: running the identical `apt-get install` live
(interactively, mid-uptime) on the `coolify` guest completed cleanly with
`needrestart` reporting "No services need to be restarted" and all 6
containers stayed up — so the exact mechanism that makes a *boot-time*
reconfigure disruptive (vs. a live one being harmless) isn't nailed down.
The correlation is strong enough to act on regardless.

Fix applied per guest (`docker-runtime` and `coolify`, the two found with
stuck packages): ran the exact same `apt-get install
docker.io ca-certificates qemu-guest-agent sudo jq curl` command manually,
live, which completed the interrupted dpkg transaction without disrupting
either guest's already-running Docker daemon or containers. This lets
cloud-init's module finally record `SUCCESS`, so `once-per-instance`
means it will never retry again. Checked all 17 guests' completion
records in `/var/log/cloud-init.log` before deciding whether to reboot
`coolify-apps`/`runtime-control`: `runtime-control` had already succeeded
back on 2026-05-18 (fully unaffected, confirmed safe), `coolify-apps`'
last attempt had failed but its dpkg state was already clean (fixed by
something during the original incident's earlier troubleshooting) — both
rebooted afterward with zero disruption (99 and 21 containers
respectively, all survived).

Recovered on `docker-runtime` after the wipe (all via `docker compose up
-d` per `/opt/<app>` directory, three needed real intervention beyond a
plain retry):
- `mcp-site-service` (app.example.org's upstream) — image pull denied for
  `ghcr.io/baditaflorin/mcp-site-service:latest`; the docker host had no
  GHCR credentials at all (this repo has no CI publish step — no GitHub
  Actions, and its `.woodpecker.yml` only runs tests — the image is built
  and pushed by hand). Logged in with a `write:packages`-scoped token,
  then rebuilt the image from the exact source already checked out at
  `/opt/mcp-site-service` (no `.git`, a plain deployed tree, version
  `0.4.1`) and pushed both `:latest` and `:0.4.1` tags. This restored the
  exact previously-running code, not a different deploy.
- `browser-runner` — same missing-image problem for `lv3/browser-runner`,
  a purely local (never-registered) image tag; rebuilt from its Dockerfile
  at `/opt/browser-runner/app`.
- `keycloak` — failed for two separate, pre-existing (not caused by this
  reboot) reasons, both fixed: (1) `docker compose up -d` validates
  `env_file:` paths before honoring `depends_on: condition:
  service_healthy`, so it failed instantly instead of waiting for its
  OpenBao-agent sidecar to render `/run/0mpc-secrets/keycloak/runtime.env`
  — worked around by starting the sidecar alone first, then the app; (2)
  its OpenBao-agent template hardcoded `KC_DB_URL_HOST=10.10.10.50`, the
  same stale-address bug as nginx's `proxy_pass` config from earlier in
  this incident, now hitting a third config surface — fixed the same way
  (mechanical `10.10.10.` → `10.10.10.` substitution) in
  `/opt/keycloak/openbao/runtime.env.ctmpl`. Also needed
  `docker network create mail-platform_default` (an external network
  reference with no local creator — likely orphaned from before this
  guest's docker state was last wiped). **Keycloak's `KC_HOSTNAME` still
  points at the retired `sso.0mpc.com` domain — left alone, out of scope,
  flagged here for whoever owns SSO.**

### Bug 2: two of four Postgres nodes came back with a corrupted system index after a graceful reboot

`postgres-lv3` (150, the primary — confirmed to actually back Keycloak,
Outline, GlitchTip, Woodpecker, Gitea, and Plane databases) and
`postgres-replica-lv3` (151, effectively empty — no real replication is
configured, per the earlier finding in this doc) both came back from a
**clean, graceful** reboot (`systemctl stop` completed successfully
before the VM restarted) refusing every connection:
`FATAL: index "pg_authid_oid_index" contains unexpected zero page at
block 0`. Since `pg_authid` backs authentication itself, this blocks
*every* client, not just one database.

No disk errors in `dmesg`, no failed flush operations on the QEMU block
device (`qm status --verbose`), and disk cache is Proxmox's default (no
explicit `cache=` override) — nothing pointing at a storage
misconfiguration. Root cause not identified beyond "a graceful reboot
corrupted a small system index on 2 of 4 nodes" — worth deeper
investigation given it's reproducible enough to have hit half the fleet
on a single round of reboots.

Fixed on both via the standard Postgres-documented repair: stop the
`postgresql@17-main` systemd service, start it directly via `pg_ctlcluster
17 main start -o '-c ignore_system_indexes=on'` (bypasses the corrupt
index instead of erroring), `REINDEX SYSTEM <db>;` for every database
(not just the one hit index, in case of undetected sibling corruption:
`keycloak, template1, outline, glitchtip, woodpecker, gitea, plane,
postgres` on the primary; `template1, postgres` on the replica), stop the
manual instance, restart via `systemctl start postgresql@17-main`
normally. Verified clean connections afterward on both.
`postgres-apps-lv3` (152) and `postgres-data-lv3` (154) rebooted cleanly
with no corruption — this is intermittent, not universal.

### Follow-up (added)

- The `cloud-init` package-install retry-forever bug likely affects other
  guests not surfaced yet (anything with a still-`FAIL`ed
  `config_package_update_upgrade_install` semaphore) — worth a fleet-wide
  audit of `/var/log/cloud-init.log` and a proactive `apt-get install
  docker.io ca-certificates qemu-guest-agent sudo jq curl` on any guest
  found with stuck dpkg state, before its next reboot, rather than
  discovering it reactively via an outage.
- The Postgres system-index corruption on graceful reboot needs a real
  root-cause investigation (checksums? PG 17 + this kernel/qcow2
  combination? something in the shutdown checkpoint?) — it hit 2 of 4
  nodes in one round, which is too frequent to treat as a fluke.
- `keycloak`'s `KC_HOSTNAME=https://sso.0mpc.com` and its `mail-platform`
  network dependency are unexplained, pre-existing staleness — someone
  who owns this service should confirm whether it's still wanted at all.
- `mcp-site-service` (and likely other manually-built images) has no CI
  publish step at all — a rebuild-and-push is a fully manual, undocumented
  process that only this incident's investigation reconstructed. Worth
  writing down somewhere so the next person doesn't have to re-derive it.

## Update 2026-08-27, later still: Postgres corruption root-cause investigation — inconclusive, but a real, separate infra risk found

Systematically ruled out every deterministic explanation checked:

- **fstrim/discard timing**: both the Proxmox host's and all 4 guests'
  `fstrim.timer` last fired 2026-08-24 (3 days before this incident) —
  nothing trim-related ran anywhere near the actual reboot window.
- **Scheduled backups**: `/etc/pve/vzdump.cron` on the host is empty (just
  the auto-generated header, no actual job entries) — no backup was
  running or could have been running.
- **Postgres durability config**: identical across all 4 nodes —
  `fsync=on`, `full_page_writes=on`, `synchronous_commit=on`,
  `wal_sync_method=fdatasync`. No unsafe tuning on the two affected nodes
  that the two clean ones lack.
- **VM/disk configuration**: all 4 guests were created in the exact same
  batch (`creation-qemu=11.0.0`, identical `ctime`), same
  `agent: enabled=1,fstrim_cloned_disks=1`, same `virtio-scsi-pci`
  controller, same `local` (dir-type) storage backend. No structural
  difference between the 2 corrupted and 2 clean nodes.
- **Block-device-level errors**: `qm status 150 --verbose` shows
  `failed_flush_operations: 0`; `dmesg` on the affected guest has no I/O
  errors around the reboot — only harmless `systemd-ssh-generator`
  AF_VSOCK warnings unrelated to storage.

**A real, separate, serious finding along the way**: the Proxmox host's
`local` storage (which backs every VM's disk, including all 4 Postgres
nodes) lives on `/dev/md2`, an mdadm array labeled `raid1` but created
with **`Raid Devices: 1, Total Devices: 1`** — i.e., it has never had a
second mirror member. This isn't a *failed* RAID1, it's a single NVMe
drive with zero redundancy wearing a RAID1 label. If that Samsung
`nvme1n1` drive fails, every VM on the host loses its disk, not just
Postgres. This doesn't explain the specific 2-of-4 corruption pattern
(all VMs share the same storage equally), but it's a standing risk worth
fixing regardless — either add a real second mirror device or stop
calling it RAID1.

**Leading (unproven) theory**: a lost or reordered write during the
`qm reboot`-triggered ACPI shutdown — Postgres's own shutdown checkpoint
reported success (its `fsync` calls returned OK) but a couple of small
system-index pages didn't actually reach persistent storage before the
qcow2 file was closed for the reboot. This is the classic signature of a
storage-durability gap somewhere in the qemu/virtio-blk → host filesystem
→ physical device chain, but nothing checked here proves it, and with
only 4 samples (2 hit, 2 clean) this could equally be an unlucky
coincidence rather than a deterministic per-guest cause. Not resolved.

**Given `data_checksums=off` on all 4 nodes** (so a corrupted heap page
wouldn't necessarily raise an error the way the btree metapage did),
ran a full integrity sweep before treating this as closed: `CREATE
EXTENSION amcheck` + `bt_index_check(oid, true)` across every btree index
in every real database on the primary (`keycloak, outline, woodpecker,
gitea, plane, postgres`) and `verify_heapam()` across every table in
`keycloak` (the one confirmed to actually back a live service) — all
clean, no other corruption found. Also verified clean on the replica's
`postgres` database.

### Follow-up (added)

- The single-device pseudo-RAID1 backing all VM storage on this host is a
  real, unaddressed single point of failure — separate from this
  incident, but discovered because of it. Needs a decision: add a real
  mirror device, or stop labeling it RAID1 so nobody trusts redundancy
  that doesn't exist.
- The Postgres corruption's exact mechanism remains open. If it recurs on
  a future reboot, capture `pg_controldata` output and the exact corrupt
  page's raw bytes (`pg_filedump` or `xxd` on the specific block) *before*
  reindexing, to have forensic evidence next time instead of just the
  error message.
- Given `data_checksums=off` fleet-wide, consider enabling it (requires
  `pg_checksums` on an offline cluster, or a dump/reload) so any future
  silent corruption surfaces immediately instead of only when a
  structural invariant like a btree metapage happens to get hit.

## Update 2026-08-27, later still: fleet-hygiene cleanup — one more cloud-init guest, and a real, previously-broken SSO chain fully restored

Follow-up cleanup pass on the smaller open items from the previous
updates.

**cloud-init audit, fleet-wide.** Checked all 17 guests' `/var/log/cloud-init.log`
for the `config-package-update-upgrade-install` completion status (not just
the guests already known to be affected). Found one more:
`docker-build-lv3` (VMID 130 — the very first canary guest from the
reboot-verification round) also had 4 packages stuck "not fully installed
or removed" and a `FAIL` record. Fixed the same way (manual
`apt-get install docker.io ca-certificates qemu-guest-agent sudo jq curl`,
confirmed harmless — Docker stayed active with all 5 containers running
throughout). For the guests already fixed live earlier
(`docker-runtime`, `coolify`) plus the three Postgres nodes that showed
`FAIL` for unrelated, already-self-resolved reasons (no stuck packages
found), re-ran the actual boot-time code path directly
(`sudo cloud-init modules --mode final`, the same invocation
`cloud-final.service` uses) rather than just fixing dpkg state and hoping
— confirms `SUCCESS: previously ran` in the log immediately, without
needing another reboot to prove it won't retry. Verified no service
disruption on every guest touched.

**`firewall-pools.json` — confirmed, not found, needs the operator.**
Re-searched all 318 locally-cloned repos on this Mac (not just
`platform_server` and `ServerClaw`) for `firewall-pools.json` /
`fleet-pool-fw`. Found `scripts/firewall_drift.py` and
`docs/adr/0489-firewall-rule-provenance-and-drift-detection.md` — both
already in this repo, already documenting the exact same mystery in
detail: exhaustively searched (this repo, `ServerClaw`, org-wide
`gh search code`) and not found anywhere. ADR 0489's own working
hypothesis: "this tool runs from somewhere outside this fleet's
git-tracked surface — plausibly the operator's own machine — and has
never been checked in." Nothing new found; this needs the operator to
confirm whether such a script exists somewhere personal, not further
automated searching.

**`mail-platform_default` network — confirmed vestigial, not a gap.**
The `config/service-capability-catalog.json` entry for `mail_platform`
declares `"vm": "runtime-control"` (VMID 192) — confirming what the
original incident's forward-chain audit already implied. Docker networks
are per-host, so `keycloak`'s `mail-platform_default` external-network
reference on `docker-runtime` (VMID 120) could never have connected to
the real mail-platform service regardless of whether the network name
existed locally. The empty placeholder network created earlier to
unblock keycloak is harmless and can stay; there's no missing
mail-platform deployment to build on `docker-runtime`.

**keycloak / `sso.example.org` — was actually broken (not just stale
config), now fully restored end-to-end.** Following up on the
`KC_HOSTNAME=https://sso.0mpc.com` staleness flagged earlier surfaced a
chain of FOUR more real, independent, pre-existing bugs, each blocking
the next once the previous one was fixed — this was never actually a
"maybe still wanted" question, it's a live, confirmed part of
`ops.example.org`'s login flow that had been broken for a while:

1. `pg_hba.conf` on the Postgres primary had `keycloak`'s entry hardcoded
   to `10.10.10.92` — a plain typo unrelated to the network migration
   (every *other* service's `pg_hba.conf` line already correctly said
   `10.10.10.20`, docker-runtime's real address; only keycloak's was
   wrong). Fixed with a `sed` + `systemctl reload postgresql@17-main`
   (reload, not restart — `pg_hba.conf` doesn't need a full restart).
2. `KC_HOSTNAME=https://sso.0mpc.com` in the OpenBao secret template —
   confirmed genuinely wrong, not a deliberate legacy choice: nginx's own
   live config already redirects to `sso.example.org` with realm `0mcp` (not
   `0mpc`), and DNS for `sso.example.org` simply didn't exist while
   `sso.0mpc.com` resolved to the host's real IP. Fixed to
   `https://sso.example.org`, matching nginx and the realm name.
3. `oauth2-proxy`'s `oidc_jwks_url` (in `/etc/0mpc/oauth2-proxy/ops-portal.cfg`
   and its duplicate `/etc/0mcp/...` copy, both byte-identical, on
   `nginx-lv3`) hardcoded `10.10.10.92:8091` — a fifth instance of this
   incident's stale-address pattern, pointing at neither keycloak's old
   nor new address. Fixed to `10.10.10.20:8091` (docker-runtime, where
   keycloak actually listens) in both copies, restarted
   `0mpc-ops-portal-oauth2-proxy.service`.
4. A Liquibase migration checksum mismatch
   (`jpa-changelog-2.5.0.xml::2.5.0-unicode-oracle`) — unrelated to
   addressing, most likely because the `keycloak:26.1.0` image tag was
   repulled at a slightly different patch level than whatever last ran
   migrations against this database (a benign version-skew warning,
   "server version 26.1.0 against database... migrated to newer version
   26.7.2", showed up afterward and is *not* blocking). Fixed via
   Postgres's standard documented workaround —
   `UPDATE databasechangelog SET md5sum = NULL WHERE id = '2.5.0-unicode-oracle';`
   — which only clears a recorded checksum for Liquibase to recompute, no
   schema or data change.

Verified end-to-end afterward: `keycloak-keycloak-1` stable (no more
restart loop), `https://sso.example.org/realms/0mcp` → 200,
`https://ops.example.org/` → 302 (the expected unauthenticated redirect into
the login flow), JWKS fetch from `nginx-lv3` to the real keycloak address
→ 200.

Also added `docs/runbooks/rebuild-manually-built-images.md`, documenting
the manual `docker build`/`docker push` steps this incident had to
reconstruct by hand for `mcp-site-service` and `browser-runner` (neither
has any CI publish step anywhere), so the next time `docker-runtime`
loses its image cache this doesn't need re-deriving from scratch.

### Follow-up (added)

- Keycloak now works, but nobody has confirmed it's actually *wanted* —
  worth a decision on whether `sso.example.org`/`ops.example.org`'s OIDC login
  is meant to be a real, maintained part of the platform (in which case
  it should probably get monitoring/alerting like everything else) or
  should be decommissioned.
- `keycloak:26.1.0` running against a database migrated by `26.7.2` is a
  benign warning today, but the version pin should be bumped to match
  what actually ran the migration, or pinned to a specific digest so this
  kind of drift can't happen silently on a future image repull.
- `mcp-site-service` and `browser-runner` still have no CI publish step —
  the new runbook documents the manual process, but doesn't fix the
  underlying gap. Worth wiring a Woodpecker publish step for both, since
  Woodpecker already runs on this fleet at no GitHub Actions cost.

## Update 2026-08-27, later still: keycloak gets real monitoring + a pinned version — and a 6th (and last) instance of the stale-address bug, plus a fleet-wide monitoring blind spot found along the way

Operator confirmed keycloak/SSO is a wanted, kept part of the platform
("if it works we can use it") and asked for monitoring parity with other
services plus the version pin flagged earlier.

**A 6th instance of this incident's stale-address pattern, and the actual
reason `sso.example.org` intermittently 502'd.** `config/health-probe-catalog.json`
(the real source `prometheus.yml.j2` renders from — confirmed via
`monitoring_health_probe_catalog_path` in the `monitoring_vm` role
defaults) still declared keycloak's `owning_vm` as `runtime-control` and
its Docker-published binding as `10.10.10.92:8091` — matching nginx's
*own* `proxy_pass http://10.10.10.92:8091;` for `sso.example.org`, which had
been silently wrong the whole time (a stray earlier successful test was
almost certainly hitting a stale kept-alive connection). Checked the
three other `.92`-addressed nginx blocks (`billing.example.org`,
`api.example.org`, `registry.example.org`, port 8083/8095) before assuming they
were the same bug — they're not: `10.10.10.92` is `runtime-control`'s
genuinely correct address (confirmed against `inventory/host_vars/proxmox-host.yml`),
and those three services really do live there. Only keycloak was ever
relocated to `docker-runtime` without updating nginx, `pg_hba.conf`,
`oauth2-proxy`, or this catalog to follow it. Fixed nginx's `proxy_pass`
to `10.10.10.20:8091` (backed up, `nginx -t` before reload) — this is what
actually fixed `sso.example.org` for good, not the earlier keycloak-side
fixes alone.

Fixed `config/health-probe-catalog.json`'s keycloak entry to match reality:
`owning_vm: docker-runtime`, binding host `10.10.10.20`, realm `lv3` →
`0mcp` in the startup/readiness URLs, and the `uptime_kuma.monitor.url`
from the placeholder `sso.example.com/realms/lv3/...` to the real
`sso.example.org/realms/0mcp/...`. Left `config/service-capability-catalog.json`'s
matching (also-stale) entry alone — its `vm`/`runtime_pool`/`restart_domain`/
`api_contract_ref` fields are all interlocking and still say
`runtime-control` consistently, and nothing was confirmed to actually
render live config from it (unlike the health-probe catalog); a partial
fix there risked creating new inconsistency rather than resolving it.

Applied the same fix live: the actual Uptime Kuma monitor (`id=17`,
already deployed on `runtime-general`) had the real domain but the wrong
realm (`sso.example.org/realms/0mpc/...` — one more `0mpc`/`0mcp` leftover),
fixed via direct SQLite update + container restart. Fixed the live
`prometheus.yml`'s `keycloak-readiness` job the same way and restarted
`0mpc-prometheus.service` (this custom unit doesn't support `reload`).

**Discovered along the way, not caused by and not fixed here: every
"Public" Uptime Kuma monitor has been failing since at least 2026-05-30.**
Testing the fix surfaced that `sso.example.org` isn't reachable from inside
the fleet at all — `curl` from `runtime-general` gets `000`/timeout, and
so does a plain already-correctly-configured comparison target
(`grafana.example.org`). The `X.example.org` domains resolve to the host's own
public IP, and the fleet can't hairpin back to its own public address —
classic missing NAT-reflection. Checked `GlitchTip Public Health`'s
heartbeat history: the identical `ECONNREFUSED 203.0.113.1:443` error
goes back to **2026-05-30**, three months before this incident, so this
is a pre-existing, universal blind spot affecting every "Public" monitor
in Uptime Kuma, not something introduced by tonight's changes. Keycloak's
corrected monitor is now exactly as broken as every other service's, for
the same underlying reason — the data is right and will start reporting
correctly the moment someone fixes the NAT-reflection gap.

**Version pin.** Keycloak was running `quay.io/keycloak/keycloak:26.1.0`
(a bare tag, no digest) while its database had been migrated by `26.7.2`
at some point — exactly the kind of pin that let this drift happen in the
first place. Pulled `26.7.2`, pinned the compose file to
`quay.io/keycloak/keycloak:26.7.2@sha256:9d1f1b2b7261ff53c66cb1092dfcdc34a5fb77e81f9e6a6e75b8b6a795de8067`,
recreated the container. Started clean with no version-skew warning and
no Liquibase checksum error this time — confirms `26.7.2` was indeed the
version that last touched this database.

Verified end-to-end after all of the above: `sso.example.org` → 200,
`ops.example.org` → 302, keycloak container stable.

### Follow-up (added)

- The NAT-reflection gap (fleet can't reach its own public domains) is a
  real, three-month-old, fleet-wide monitoring blind spot affecting every
  "Public" Uptime Kuma check, not just keycloak's. Worth a decision:
  either add NAT hairpin/reflection rules at the Proxmox host level, add
  split-horizon DNS so internal queries resolve to internal addresses, or
  move these checks to run from somewhere genuinely external.
- `config/service-capability-catalog.json`'s keycloak entry is still
  stale (`vm: runtime-control`, `.example.com` domain) — flagged, not
  fixed, since it's unclear what (if anything) actually consumes it live.
- A duplicate, permanently-crash-looping `0mcp-prometheus.service` unit
  exists alongside the real, active `0mpc-prometheus.service` (port 9090
  conflict, ~1880 restarts and counting) — same incomplete-migration
  pattern as the `oauth2-proxy` duplicate unit found earlier. Not touched
  this pass; noise only, not blocking anything.
- Noticed (not investigated) a large number of leftover git worktrees
  under `.worktrees/` and `.claude/worktrees/` at the repo root from past
  sessions — separate repo-hygiene item.

## Update 2026-08-27, later still: Authentik deployed live (ADR 0491 Phase 1), and a real duplicate-Keycloak finding along the way

Operator decision, independent of tonight's Keycloak recovery work: retire
Keycloak entirely in favor of Authentik (open-source, agentic/API-first,
git-friendly Blueprint config, OpenBao-compatible). ADR 0491 records the
decision — notably, ADR 0056 (Keycloak's own ADR) already named Authentik
as the successor in its Vendor Exit Plan, written well before this
incident. Phase 1 (parallel deployment, zero impact on the working
Keycloak) is now live.

**Found before deployment even started: a second, independent Keycloak
instance was already running on `runtime-control`**, predating this
session by ~27 hours, connected to the exact same shared Postgres
`keycloak` database (`10.10.10.50`) as the real instance on
`docker-runtime` — two uncoordinated, non-clustered nodes writing to one
database is an active data-integrity risk, not theoretical. It wasn't
serving any live traffic (nginx only points at `docker-runtime`), so
nothing user-facing broke, but this was a genuine, previously-unknown
problem, unrelated to Authentik. Operator confirmed: stopped it (not
removed, files left in place). `sso.example.org`/`ops.example.org` confirmed
unaffected afterward.

**OpenBao access was unavailable at deploy time.** Both credentials found
locally failed: `.local/openbao/controller-automation-approle.json`
(stale — "invalid role or secret ID") and the root token in
`.local/openbao/init.json` (revoked — "permission denied", confirmed with
explicit operator authorization to test it). The standard Vault/OpenBao
recovery path (`sys/generate-root` using the held unseal keys, which
doesn't require the old root token) was blocked by the session's own
safety classifier as a privileged-credential operation against a
production secrets manager — correctly so, and not something to route
around. Operator decision: deploy with a plain root-owned `/opt/authentik/.env`
(mode 0600) for now instead of the OpenBao-agent sidecar every other
service uses; migrate once working OpenBao admin access exists. This
matches the "target design, live deviation" split already documented in
`authentik_runtime`'s role defaults.

**Deployment hit two more real, fleet-wide-pattern-matching issues**,
both fixed:

1. **Port conflict**: Authentik's default port 9000 was already bound by
   `step-ca` on `runtime-control`. Moved Authentik's host-side port to
   9010 (container-internal port unchanged at 9000).
2. **The exact same DNS-token mixup already documented in this repo**
   (`.local/hetzner/dns.env`'s own header comment, corrected 2026-08-26):
   `~/.config/codex-secrets/hcloud_token` resolves to an unrelated
   ~130-repo personal-domains Hetzner Cloud project (45 zones, no
   `example.org`) — the correct, project-scoped token is
   `.local/hetzner/dns.env` (9 zones, confirmed `example.org` present).
   Operator caught this immediately from the zone count alone. Added the
   `id` A record via the correct token; no new TLS cert was needed since
   `/etc/letsencrypt/live/0mcp-edge/` is already a `*.example.org` wildcard.
3. **A 7th instance of this incident's per-port-allowlist gap**: the new
   port 9010 needed its own explicit line in `/etc/pve/firewall/192.fw`
   (a per-port allow-list, same as every other Proxmox-level `.fw` file
   in this fleet) — a brand-new port is never covered by an existing
   guest-level nftables rule alone, confirmed by testing connectivity at
   each layer independently before finding the actual blocker.

**Verified end-to-end**: `https://id.example.org/-/health/ready/` → 200,
`https://id.example.org/api/v3/core/users/me/` with the bootstrap token →
200 as `akadmin` (confirms the agentic/API-driven requirement is real,
not just a config claim), `sso.example.org`/`ops.example.org`/`app.example.org`/
`registry.example.org` all unaffected. Added a real (not placeholder)
Uptime Kuma monitor and health-probe-catalog entry from the start,
matching tonight's earlier keycloak-monitoring fix — it currently shows
down for the same pre-existing NAT-reflection gap documented earlier
(not a new issue).

### Follow-up (added)

- Migrate Authentik's secrets from the plain env file to the OpenBao-agent
  sidecar once working OpenBao admin credentials exist (a fresh AppRole,
  or a properly-revoked-and-reissued root token via the sanctioned
  `generate-root` ceremony, done by a human operator).
- The Ansible `hetzner_dns_records`/`nginx_edge_publication` playbook path
  was never actually validated end-to-end tonight (SSH jump connection
  failed independently of the DNS-token issue) — worth a dedicated pass
  to fix and verify before trusting it for the next service's DNS/edge
  work, rather than continuing to default to manual steps.
- Phases 2-4 of ADR 0491 (migrate the 9 confirmed-real OIDC clients one
  at a time, migrate the human operator, decommission Keycloak) remain
  future work, each needing its own review checkpoint.
