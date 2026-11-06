# Configure Guest Network Policy

## Purpose

This runbook converges ADR 0067 by enforcing the canonical guest network policy on both layers that matter:

- Proxmox VM firewalls on the host
- guest-local `nftables` policy on every managed VM

## Entrypoints

- syntax check: `make syntax-check-guest-network-policy`
- preflight: `make preflight WORKFLOW=converge-guest-network-policy`
- converge: `make converge-guest-network-policy`

For a Proxmox-host-only run that skips the guest-local nftables play on every
VM, limit the run to the host:

```bash
make converge-guest-network-policy env=production EXTRA_ARGS='--limit proxmox-host --check --diff'
make converge-guest-network-policy env=production EXTRA_ARGS='--limit proxmox-host'
```

That still runs the whole `proxmox_network` role on the host: it replays
`/etc/network/interfaces`, `/etc/nftables.conf`, forwarding and the conntrack
helper, sets the `net0` firewall flag of any guest where it differs, and stops
and starts any guest whose SSH port does not answer. To change only the per-VM firewall files, use
the tag in the next section instead.

The target defaults Ansible host-key checking to enabled; keep it enabled for
live applies. `EXTRA_ARGS` is appended to the governed scoped-runner command,
so the host-only limit also applies to its execution-scope and mutation audit.

## Render only the per-VM Proxmox firewall files

> **Warning: the render is not the whole live file.** The files in
> `/etc/pve/firewall/` have other writers than `vm.fw.j2`: hand-authored rules
> with comments, an `AUTO-MIGRATED` set, and blocks that other tools generate
> (`# BEGIN fleet-pool-fw` ... `# END fleet-pool-fw`, built from
> `firewall-pools.json`, on VM 191 of 0mcp). Replacing a file with the render
> deletes all of them. On 2026-10-30 an apply of this slice on 0mcp did exactly
> that: about 25 production rules (Prometheus 9100 scrapes on ten VMs, the
> Creator Atlas nginx rule, the VM 191 to VM 154 PostgreSQL tunnel, the keystore
> failover chain, the whole pool block) were gone for three minutes until the
> directory was restored from a backup, and the `--check --diff` before it had
> shown 19 added lines and no removal, because it compared the render with the
> staging copy and not with the live file. The play now compares with the live
> file and refuses to remove anything on its own: read "The install guard"
> below before the first run on a host. The inventory is not automatically the
> source of truth for those VMs: a rule the check shows as "pending" can be the
> render lagging behind a live hand edit, not work waiting to be applied.

Use this when the allow matrix in `inventory/host_vars/proxmox-host.yml` changed
for one or more guests (a new inbound rule, a new guest) and nothing else on the
hypervisor should move. It is the supported replacement for appending a line to
`/etc/pve/firewall/<vmid>.fw` by hand.

```bash
make converge-guest-network-policy env=production EXTRA_ARGS='--tags proxmox-vm-firewall --limit proxmox-host --check --diff'
make converge-guest-network-policy env=production EXTRA_ARGS='--tags proxmox-vm-firewall --limit proxmox-host'
```

Run it with the same identity, topology and inventory overlays as a full run
(see `docs/runbooks/converge-proxmox-firewall-policy.md` for the variables). The
overlays are required: the role's placeholder-address guard runs in this slice
too and refuses the committed RFC 5737 addresses.

**The 0mcp invocation.** The 0mcp identity overlay sets `management_interface` to
the WAN bridge (`vmbr0`), and the role's SAFETY GUARD that refuses a management
interface aliasing the WAN bridge refuses that value on every run, this slice
included, even though the slice never writes it. Pass the verified physical uplink
for the run (on 0mcp, `enp7s0`):

```bash
make converge-guest-network-policy env=production EXTRA_ARGS='--tags proxmox-vm-firewall --limit proxmox-host -e management_interface=enp7s0 --check --diff'
make converge-guest-network-policy env=production EXTRA_ARGS='--tags proxmox-vm-firewall --limit proxmox-host -e management_interface=enp7s0'
```

In this slice the value is read only by the input validation and by that guard
(`vm.fw.j2` does not use it), so the override changes nothing the slice renders.
Do not carry it over to a full run unless it is the verified uplink for that run,
because the full play writes `/etc/network/interfaces` from it. The guard was kept
as it is on purpose: it protects the one write that can lock the host out, and
loosening it for a run that never makes that write deserves its own review (a
split of the guard, so that this slice does not depend on a variable it never
writes, is a possible follow-up).

What it does, in order:

1. Runs the role's input validation and the two SAFETY GUARD asserts (placeholder
   management address, management interface aliasing the WAN bridge). They carry
   the `always` tag, so neither this tag selection nor `--skip-tags
   proxmox-vm-firewall` can skip them.
2. Reads `qm config` for every declared guest and keeps the ones that exist (also
   in `--check` mode, so a check run plans the same guests as the real run). With
   `-e proxmox_network_firewall_vmids=155` (or `155,191`) it keeps only the named ones;
   naming a guest that does not exist fails the run.
3. Renders `vm.fw.j2` to `/root/.lv3-vm-<vmid>.fw`, also in `--check` mode (the
   staging copy is scratch that Proxmox never reads), so the next step compares
   the live files with the render the real run would install.
4. Compares every render with the LIVE `/etc/pve/firewall/<vmid>.fw` and prints,
   per VM, a unified diff (live to render) plus one `!! REMOVED` line for every
   rule or option line, and every managed block, that the install would delete.
   This step is read only and runs in `--check` mode. It fails the run, before
   anything is written, if any VM would lose something and the operator did not
   pass `-e proxmox_network_allow_rule_removal=true`.
5. Installs the renders that differ (`files/pve_fw_guard.py apply`): first a
   backup of every file it is about to replace, then the write, read back. Skipped
   in `--check` mode.
6. Runs `pve-firewall compile`, and `pve-firewall restart` only when at least one
   file changed.

What it does not do:

- It does not touch `/etc/network/interfaces`, `/etc/nftables.conf`, forwarding,
  the conntrack helper or its unit, or the `pve-firewall` service enablement. It
  assumes `pve-firewall` is already enabled and running, as on the live host.
- It does not set `firewall=1` on a guest's `net0`. A file for a guest whose NIC
  does not carry `firewall=1` is installed but inactive: check with
  `qm config <vmid> | grep ^net0` and run the full play if the flag is missing.
- It never stops or starts a guest. The full play's restart branch (a guest whose
  `net0` flag was just changed, or whose SSH port is unreachable) does not run.
- It does not run the guest-local nftables play: with `proxmox-vm-firewall` as
  the only tag the second play gathers no facts and connects to no guest.
- It does not merge. A file that is installed becomes the render: whatever the
  inventory does not declare is gone, so the guard (below) refuses the install
  whenever that would delete a rule line or a managed block, and only comments
  that the render lacks are dropped silently (the diff counts them and the backup
  keeps them). A VM whose live file carries lines the inventory does not know
  (on 0mcp on 2026-10-30: VM 191 with its `fleet-pool-fw` block, and the VMs that
  carry hand-added Prometheus 9100 or tailnet accepts) cannot go through this
  slice until those lines are declared in the allow matrix. Name the VMs you do want
  (`-e proxmox_network_firewall_vmids=155`); the others are neither
  rendered nor compared.
- Before 2026-10-30 `--check --diff` compared the render with the staged
  `/root/.lv3-vm-<vmid>.fw` of the previous run, not with the live file, planned a
  file for every declared guest (a skipped `qm config` reports `rc=0`) and
  skipped the copy, so a destructive change looked additive. It now answers the
  question the real run answers: same guests, diff against the live files, same
  refusal. It still installs nothing.

## The install guard

`roles/proxmox_network/files/pve_fw_guard.py` (standard library only, run on the
hypervisor by the role) is the only code that writes a live per-VM file. It plans
every selected VM first and writes only if no VM is refused, so one refused VM
stops the whole install, including the additive VMs of the same run.

What counts as a removal, and refuses:

- any rule, option, alias or ipset line, in any section (`[OPTIONS]`, `[RULES]`,
  `[IPSET ...]`, `[ALIASES]`, `[group ...]`), that the live file has and the render
  does not, a disabled rule (`|IN ACCEPT ...`) included. A rule whose port,
  source or action changed counts too: the old line is removed.
- a managed block, `# BEGIN <label>` ... `# END <label>`, that the render does
  not carry, even if the block holds only comments.

What does not: added lines, a new file (VM 155 before its first install), spacing,
rule order, a repeated line, a trailing `# comment` on a rule, and comment lines.

If a removal is intended, run the same command again with
`-e proxmox_network_allow_rule_removal=true`. Pass it on the command line for that
one run; never put it in an inventory or an overlay. The report still lists every
removal and says `REMOVAL ALLOWED`.

Before the first write of a run the guard copies every live file it is about to
replace to `/root/fw-backup-<UTC timestamp>/<vmid>.fw` on the hypervisor and
writes `restore.sh` next to them. The play prints both, for example:

```text
Installed 2 firewall file(s) (140, 155); copies of the files they replaced are in /root/fw-backup-20261030T120000Z
Restore them with: sh /root/fw-backup-20261030T120000Z/restore.sh
```

`restore.sh` copies each saved file back (`cp -p`), removes a file the run created
(a VM that had none), and runs `pve-firewall restart`. A run that refused, failed
the comparison, or found nothing to change takes no backup (there is nothing to
restore). If a write fails half way the guard puts the files it already wrote back
itself. A VM that is refused with `rc=2` is not a failure of the play's tooling:
the diff above the message is the answer.

Reading a refusal: the `!! REMOVED [RULES] ...` lines are the live lines the render
lacks. Either add them to `network_policy` for that guest in
`inventory/host_vars/proxmox-host.yml` (then the render carries them and the next
check shows an additive diff), or leave that VM out with
`proxmox_network_firewall_vmids`.

The dry run against the live files, the real run and the roll back, for one VM:

```bash
make converge-guest-network-policy env=production EXTRA_ARGS='--tags proxmox-vm-firewall --limit proxmox-host -e management_interface=enp7s0 -e proxmox_network_firewall_vmids=155 --check --diff'
make converge-guest-network-policy env=production EXTRA_ARGS='--tags proxmox-vm-firewall --limit proxmox-host -e management_interface=enp7s0 -e proxmox_network_firewall_vmids=155'
# rollback, on the hypervisor, with the path the play printed
sh /root/fw-backup-<UTC timestamp>/restore.sh
```

After any apply, as before: `diff -r /root/fw-backup-<ts> /etc/pve/firewall` shows
only what you intended, `scripts/netpolicy.py drift --live` stays at 0 drifted VMs
and no scrape target went down.

Verify after an apply: `pve-firewall compile` printed no error (the play ran
it), `cat /etc/pve/firewall/<vmid>.fw` shows the new line, and the intended
connection works from the intended source peer.

## Preconditions

1. The controller SSH key exists at `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519`.
2. The Proxmox host is reachable at `100.118.189.95`.
3. Every managed guest is reachable through the Proxmox jump path.
4. The canonical allow matrix in `inventory/host_vars/proxmox-host.yml` has been reviewed before apply.

## What The Workflow Changes

1. Renders one Proxmox firewall file per managed VM under `/etc/pve/firewall/<vmid>.fw`.
2. Enables `firewall=1` on each VM `net0` interface without rewriting unrelated VM hardware settings.
3. Maintains the Proxmox host conntrack-zone helper needed for `fwbr+` bridge traffic to preserve NATed guest egress after VM firewalls are enabled.
4. Compiles and restarts `pve-firewall` on the Proxmox host when the per-VM policy changes.
5. Renders `/etc/nftables.conf` on each guest from the same canonical `network_policy` data for both local services and Docker-published forwards.
6. Reloads guest `nftables` and verifies that SSH reconnects cleanly after the policy change.

## Keeping a guest out of the `all_guests` fan-out

A rule with `source: all_guests` expands to every other managed guest, in three
renderers that must agree: the guest nftables (`nftables.conf.j2`, input and
forward chains), the Proxmox VM firewall file (`vm.fw.j2`) and
`scripts/firewall_drift.py`, which mirrors both. A guest that should not appear in
that expansion carries `network_policy_all_guests: false` in its `proxmox_guests`
entry in `inventory/host_vars/proxmox-host.yml` (the default is `true`). Rules that
name the guest explicitly (`source: <guest name>`) are not affected.

Today only the agent-history store (VM 155) opts out: it holds every secret an
agent ever saw and must not reach the NATS, Mailpit, Redpanda, n8n, directus and
other ports that services open to "all guests". The one flow it needs into another
guest is OpenBao `tcp 8201` on `runtime-control`, declared by name. After changing
the flag, re-render both layers for every guest that has an `all_guests` rule: the
slice above for the Proxmox files, and the guest play for the guest nftables (for
example `--limit runtime-control`, check and diff first), then run
`scripts/netpolicy.py drift --policy config/network-policy/0mcp.yaml --live` and
expect no drifted VM. `tests/test_network_policy_all_guests_flag.py` pins the flag
in all three places.

## Canonical Policy Source

- policy source: [inventory/host_vars/proxmox-host.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/host_vars/proxmox-host.yml)
- flow reference: [docs/runbooks/network-policy-reference.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/runbooks/network-policy-reference.md)
- playbook: [playbooks/guest-network-policy.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/playbooks/guest-network-policy.yml)

## Verification

Run these checks after converge:

1. `make syntax-check-guest-network-policy`
2. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo pve-firewall compile >/dev/null && sudo ls /etc/pve/firewall/*.fw'`
3. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'nc -z -w 2 10.10.10.50 5432'`
4. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.50 'nc -z -w 2 10.10.10.20 8080'`

## Notes

- The workflow is intentionally host-first, then guest-side, so the outer firewall layer is active before guest-local defence in depth.
- Unlisted inter-guest flows are denied by default.
- Public ingress and host-side Tailscale proxy paths remain governed by the same host inventory and must be kept in the allow matrix.
