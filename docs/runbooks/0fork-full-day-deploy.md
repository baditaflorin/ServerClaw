# Runbook: 0fork Full-Day Deployment (ADR 0431)

**Audience:** An operator standing up a fork-clone of this platform on a
newly-provisioned Hetzner dedicated server, end-to-end, as
infrastructure-as-code.

**Outcome:** One acceptance email delivered from
`operator@<your-fork-domain>` to the operator's Gmail inbox. No manual SSH
into the target during the deploy itself.

**Companion ADRs:**
- [ADR 0424](../adr/0424-fork-clone-onto-hetzner-ax41.md) — scope and VM plan
- [ADR 0430](../adr/0430-topology-host-vars-local-overlay.md) — host_vars overlay
- [ADR 0431](../adr/0431-0fork-full-day-deployment.md) — the orchestrator

---

## Prerequisites

Before the one-command deploy, you must have:

1. **Hetzner server provisioned** with SSH access. Follow
   [hetzner-bare-metal-bootstrap.md](hetzner-bare-metal-bootstrap.md)
   through step 3 (host key pinned, hostname set, `/dev/kvm` present).
2. **Hetzner DNS zone** for the fork domain (e.g. `0fork.com`) with the apex
   wipe + A/AAAA/wildcard records in place (see ADR 0424 §3).
3. **Four overlay files** in `.local/` on the control workstation:

   | File | Purpose |
   |------|---------|
   | `.local/identity.yml.0fork` | Scalar overlay (domain, IPs, operator email) — see ADR 0424 §4 |
   | `.local/host_vars/proxmox-host.yml` | Topology overlay (`proxmox_guests`) — see ADR 0430 |
   | `.local/hetzner/dns.env` | `HETZNER_DNS_TOKEN=<token>` + `HETZNER_DNS_ZONE=<zone>` |
   | `.local/ssh/hetzner_llm_agents_ed25519` | Bootstrap SSH key matching Hetzner's stored public key |

Each is gitignored (ADR 0376). The orchestrator reads them from the main
worktree via `scripts/resolve_local_overlay_root.sh`.

---

## Step 1 — Preflight

```bash
make preflight-0fork
```

This validates:
- All four overlay files exist.
- `load_topology_host_vars()` successfully parses the host_vars overlay
  and the result contains a non-empty `proxmox_guests` list.

If any check fails, the target prints which file is missing and exits
non-zero. Fix the gap before proceeding.

---

## Step 2 — One-command deploy

```bash
make deploy-0fork
```

This runs `playbooks/0fork-full-day.yml`, which imports in order:

1. `proxmox-install.yml` — Proxmox repository, kernel, platform, access,
   **Hetzner WAN bridge via `proxmox_network`**, Tailscale, **Headscale
   install via `proxmox_headscale`**, guest creation, host security,
   control-loops, backups.
2. `site.yml` — full service convergence under `env=clone`: data tier,
   security, observability, automation, communication, platform-apps
   (Keycloak, OpenBao, step-ca, API gateway, mail-platform, etc.).
3. `mail-platform-send-gmail.yml` — acceptance email to
   `{{ platform_operator_email }}`.

Expect a multi-hour runtime (hundreds of Ansible tasks, dozens of
services). Progress is visible in stdout; every task is idempotent, so
partial failures can be resumed with `make converge-0fork-chain`.

---

## Step 3 — Acceptance

If step 2 completed successfully, the probe already ran. To re-send the
acceptance email on demand (e.g. after a mail-platform redeploy):

```bash
make smoke-0fork-mail
```

Success criteria:
- Ansible output shows `outbound_status=200` from the local mail gateway.
- An email arrives in the operator's Gmail inbox with subject
  `LV3 platform transactional mail probe`.

If the gateway returns 200 but no email arrives, the issue is downstream
(SPF/DKIM/DMARC, Brevo API credentials, rDNS). Check
`/opt/mail-platform/gateway/data/state.json` on `runtime-control` for the
last delivery attempt record.

---

## Re-runs and partial replays

| Situation | Target |
|-----------|--------|
| Overlay-only edit (new VM, changed IP) | `make converge-0fork-chain` |
| Mail-platform redeploy only | `make converge-mail-platform env=clone` |
| Just re-send the acceptance email | `make smoke-0fork-mail` |
| Rotate Hetzner DNS token | `make rotate-hetzner-dns-token` (see below) |

All targets are idempotent. The orchestrator does not checkpoint; a
mid-run failure requires re-invoking either the full `deploy-0fork` or
the narrower `converge-0fork-chain` to resume.

---

## Rotating the Hetzner DNS token (ADR 0424 item 7)

After the fork is live, the DNS token that was shared during bootstrap
should be rotated.

```bash
# Create a replacement token in the Hetzner console first.
export HETZNER_DNS_API_TOKEN_NEW="<new-token>"
make rotate-hetzner-dns-token
```

The playbook verifies both tokens resolve the same zone, persists the new
token to `.local/hetzner/dns.env`, and prints a reminder to revoke the
old one manually in the Hetzner console (revocation has no API).

---

## Failure modes and where to look

| Symptom | Likely cause | Where to look |
|---------|--------------|---------------|
| `MISSING: .local/identity.yml.0fork` | Overlay never created | ADR 0424 §4 for the full scalar list |
| `overlay missing proxmox_guests` | host_vars overlay lacks the `proxmox_guests` key | ADR 0430; commit an example in your overlay |
| `HETZNER_DNS_API_TOKEN` not set | `.local/hetzner/dns.env` missing or malformed | `grep HETZNER_DNS_TOKEN .local/hetzner/dns.env` |
| SSH auth fails to the target | Wrong key fingerprint on Hetzner's side | `docs/runbooks/hetzner-bare-metal-bootstrap.md` §0 |
| `proxmox-install` fails at `proxmox_network` | Hetzner bridge gateway mismatch | Verify `management_gateway4` in `.local/identity.yml.0fork` matches `ip route` on the host |
| Mail probe returns 200 but no inbox delivery | DNS/DKIM/SPF or Brevo transport issue | `runtime-control:/opt/mail-platform/gateway/data/state.json` |

For anything not covered here, search `docs/adr/.index.yaml` for the
service name and read its ADR + per-service runbook.

---

## What this runbook explicitly does NOT do

- **It does not provision the Hetzner server.** That is a separate manual
  step (order the box, receive the provisioning email, verify the host
  key) per the bare-metal bootstrap runbook.
- **It does not set rDNS** on the Hetzner IP. Hetzner's legacy Robot API
  does not expose rDNS for dedicated servers; set it in the Robot web UI.
  Without it, outbound mail deliverability will be degraded.
- **It does not touch production (`env=production`).** The orchestrator
  is hardcoded to `env=clone`. Prod operators continue to use the
  per-service `converge-*` targets.
