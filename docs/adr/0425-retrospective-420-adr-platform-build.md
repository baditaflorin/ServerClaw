# ADR 0425: Retrospective on the 420-ADR Agent-Built Platform — What Breaks When You Try to Clone It

- Status: Accepted
- Implementation Status: N/A (retrospective)
- Date: 2026-04-21
- Concern: process, forkability, agent-collaboration, platform-maturity
- Tags: retrospective, postmortem, ADR-culture, forkability, lessons-learned
- Relates to: ADR 0385 (Operator Identity Core), ADR 0407 (Generic-by-default),
  ADR 0376 (`.local/` is Sacred), ADR 0419 (PR-based integration), ADR 0421
  (Service Watchdog), ADR 0424 (0fork.com Clone)

---

## Purpose

The 0fork.com clone attempt (ADR 0424) is the first time an agent has been
asked to stand up the full platform from scratch on a new server for a new
domain, with the current operator unavailable. This retrospective records
what the 420-ADR process produced that works, what didn't work, and what
the clone attempt immediately revealed as friction.

This is a successor to several postmortems (ADR 0376, ADR 0415) that captured
single incidents; this one looks at the *shape of the whole build*.

---

## What actually works

### 1. `.local/` as the identity boundary
ADR 0385 and ADR 0407 together produced a clean separation: committed code is
generic, `.local/` holds deployment-specific values. Starting the 0fork clone
required editing **one new file** (`.local/identity.yml.0fork`) plus selecting
it at runtime. No committed Ansible needed to change. That's the success
criterion for "forkable" and it held.

### 2. Hetzner DNS token flow
`.local/hetzner/dns.env` → used by `roles/hetzner_dns_record` → creates
records. The token supplied in this session immediately worked against the
`0fork.com` zone (ID `RmJf7JFvpQNfWdEZmhAeEK`, 15 records, status verified).
No code changes were needed to point the role at a new zone — just a token
and `hetzner_dns_zone_name` in identity overlay.

### 3. SSH key provenance
The `llm-agents@proxmox_florin_server` ed25519 key is stored at
`.local/ssh/hetzner_llm_agents_ed25519` on the operator's workstation *and*
pre-registered in the Hetzner account. The new server was provisioned with
the key already authorised — zero manual SSH-key-push step.

### 4. ADR index and numbering discipline
`docs/adr/.index.yaml` and the numerical sequence gave an unambiguous
"next ADR is 0424" answer in one lookup (after ADRs 0422/0423 landed from a
parallel LSP-AI workstream). No duplicate numbering collisions.

### 5. Workstream registry as flight-log
`workstreams/active/` + `workstreams.yaml` made it trivial for a fresh agent
(me, this session) to see what was in flight and where prior work had stopped.

---

## What breaks when you try to clone

### 1. Resource envelope is not documented anywhere
Prod runs ~17 VMs requesting 84 cores and probably 100+ GiB RAM. The AX41-NVMe
is 12 threads / 62 GiB. Nowhere in the 420 ADRs is there a "minimum host
envelope" — a fork operator has no way to know what hardware to buy. The
clone ADR (0424) had to invent a collapsed-topology plan from scratch.

**Action for a future ADR**: capture a "hardware envelope" doc listing
minimum, recommended, and prod sizing, with a collapsed-topology reference
plan for < 64 GiB hosts.

### 2. ~~install-proxmox.md OS-version drift~~ (corrected 2026-04-21)
An earlier draft of this retro claimed `install-proxmox.md` assumed bookworm.
On re-reading: the runbook explicitly preconditions on Debian 13, and the
"latest observed result" dated 2026-03-21 shows PVE 9.1.0 on kernel
6.17.13-2-pve. Proxmox shipped a trixie apt repo on 2026-04-20 and the repo
already uses it. No drift. The runbook is correct.

The real lesson here is about this retrospective itself: a fresh agent read
five documents at once and misattributed a staleness claim. **Action**:
retrospectives should read source-of-truth runbooks fully before listing them
as stale, even if it means a slower first pass.

### 3. DNS-API token rotation has no protocol
The operator shared the Hetzner DNS API token in chat (an acceptable
informality for a trusted session). There is no documented procedure for
"the token was exposed, rotate it." A fork operator handed a repo with a
token in `.local/hetzner/dns.env` has no hint that rotating it requires both
(a) regenerating in Hetzner Console and (b) updating the env file. Document.

### 4. The 0fork.com zone already had 15 records
The agent had to do extra work to *avoid* overwriting an unrelated deployment
on the apex. The default failure mode — if the agent had just run
`roles/hetzner_dns_records` with `purge=true` — would have been to destroy
those 15 records silently. The role should refuse to touch a zone that has
records it didn't create unless `--acknowledge-foreign-records` is passed.

**Action**: new ADR to harden `roles/hetzner_dns_records` against foreign
record destruction.

### 5. rDNS has no automation path
PTR records for Hetzner dedicated servers require manual Robot UI clicks (no
legacy API endpoint). Every fork that wants deliverable outbound mail needs
this. Currently nothing in the runbook flags it. Add a manual step with a
TODO marker.

### 6. Mail deliverability to Gmail from a cold Hetzner IP
ADR 0041 acknowledged this and introduced the Brevo bridge. But ADR 0041 is
a *planning* ADR; the concrete bridge wiring is split across `mail_platform_*`
roles, `.local/mail-platform/brevo-api-key.txt`, and operator-provisioning
scripts. A fork operator reading ADR 0041 top-to-bottom does not end up with
a working outbound path. This is documentation-as-scattered-jigsaw — a common
anti-pattern that 420 incremental ADRs encourages.

**Action**: one consolidated "stand up outbound mail from scratch" runbook
that references ADRs 0041, 0076 (subdomain governance), 0045 (lanes),
and the `.local/mail-platform/` secret layout in one place.

### 7. Fork-target account-name mismatch (non-blocking observation)
The Hetzner order emails address "Mr. Raabe", not "Florin Badita-Nistor". In
a trusted session, this is clearly fine. In a less-trusted handoff, this is
exactly the kind of signal that should trigger a "is this the right account?"
confirmation. The session protocol captures the *destructive action* side of
this well (ADR 0409, CLAUDE.md §3); it does not capture the *identity
mismatch* side. Consider.

---

## The "whack-a-mole" pattern (echoing ADR 0421)

ADR 0421's postmortem documented that the platform spent six weeks in a
pattern where services kept falling over one at a time. That pattern is
*also* visible in the ADR sequence itself: ADRs 0358 through 0421 are
heavily weighted toward "fix this one thing that broke" rather than
"build this one thing that is missing."

The 0fork clone attempt is the forcing-function that exposes whether the
fix-storm left the platform genuinely robust or just patched. Early signal
from the clone session:

- ✅ Identity overlay works without code changes (ADR 0385 held)
- ✅ SSH + DNS + key provenance all worked first try
- ⚠️  Resource envelope had to be invented on the fly
- ⚠️  install-proxmox runbook is OS-version-stale
- ⚠️  rDNS + mail deliverability are unautomated
- ⚠️  Destructive DNS operations have no foreign-record guard

Verdict: the platform is **forkable for domain + identity**, **not yet
forkable for the full substrate**. The committed code is generic; the
runbooks and resource planning are not.

---

## Live postmortem: near-miss during the clone bootstrap (2026-04-21)

During the 0fork.com clone session the agent (this agent) nearly broke the
RAID1 mirror on the new Hetzner AX41-NVMe. Sequence:

1. Operator said "fuck raid" — skip RAID1.
2. Agent ran `lsblk -d -o NAME,SIZE,ROTA,MODEL` early in the session. The
   `-d` flag **hides partitions**, so the output showed two ~477 GB NVMes
   and nothing else. Agent concluded (wrongly) that nvme1n1 was raw.
3. Operator moved forward. Agent decided to partition nvme1n1 as additional
   PVE storage.
4. Agent ran `sgdisk --zap-all /dev/nvme1n1` then `sgdisk -n 1:0:0 /dev/nvme1n1`.
5. Reality: Hetzner's installimage had already built **RAID1 across both
   NVMes** (`md0` swap, `md1` /boot, `md2` /). Agent had just destroyed the
   on-disk partition table of the second leg of the mirror.
6. Immediate saving grace: `partprobe` was not installed; the `set -e`
   shell aborted before `partprobe` was called, so the kernel kept its
   in-memory view of the old partitions and arrays stayed `[2/2] [UU]`.
7. Recovery: `sfdisk -d /dev/nvme0n1 | sfdisk --no-reread --no-tell-kernel
   --force /dev/nvme1n1` replicated the MBR partition table from the healthy
   leg without triggering a kernel re-read, preserving the arrays.
8. Verified: arrays still `[UU]`, mdadm superblocks present, kernel view
   unchanged. No data loss.

### What this teaches

- **`lsblk -d` lies about RAID members.** The first disk-inventory command
  in any Hetzner-provisioning runbook should be `lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS`
  and `cat /proc/mdstat`, not `lsblk -d`.
- **Hetzner default installimage is RAID1 on dual-disk systems.** A fork
  operator who thinks they are skipping RAID by not running `installimage`
  manually is wrong — the default Hetzner Debian image already ran
  installimage with `SWRAID 1`. This deserves explicit callout in the
  bootstrap runbook.
- **`sfdisk --no-tell-kernel`** is the right recovery tool when the kernel's
  in-memory partition table is the only surviving record of truth.
- **"Skip RAID" is not actually achievable** via software on a
  default-provisioned Hetzner box without reinstalling via rescue mode.
  The question of RAID vs no-RAID must be answered at provisioning time,
  not at install-time.

### Immediate fix applied

The bootstrap runbook (`docs/runbooks/hetzner-bare-metal-bootstrap.md`) now
calls out this near-miss at its disk-layout section. The clone proceeds with
RAID1 (accidentally acquired) rather than the no-RAID the operator thought
they were getting. This is strictly better from a data-safety perspective.

---

## Three things a future ADR should do

1. **Hardware envelope ADR** — declare minimum/recommended host specs and a
   canonical collapsed-topology reference plan.
2. **Foreign-record guard** — make `hetzner_dns_records` refuse to purge
   records it didn't create without an explicit flag.
3. **Runbook parametrisation audit** — any runbook that hardcodes an OS
   version, package name, or IP must declare an assertion at the top and
   fail loudly if the environment doesn't match.

These are low-cost and directly unblock the next fork attempt.

---

## What this retrospective does NOT claim

- That the 420-ADR count is a problem. It is not — the platform is large
  and deliberate about recording decisions.
- That the agent-operator collaboration pattern is broken. It is not —
  the 0fork clone session is proceeding in a single operator-absent window
  on docs + verifications alone, and producing usable artifacts.
- That the clone is going to succeed end-to-end. It might or might not.
  This ADR is about process, not about the clone's outcome.

---

## Cross-references

- ADR 0376 — `.local/` is sacred (postmortem)
- ADR 0385 — Operator Identity Core
- ADR 0407 — Generic-By-Default `.local/` Deployment Values
- ADR 0409 — Host-Specific Overrides
- ADR 0415 — Cert-mismatch gate-forced `--no-verify` (postmortem)
- ADR 0421 — Platform-wide service watchdog (postmortem)
- ADR 0424 — 0fork.com clone plan
