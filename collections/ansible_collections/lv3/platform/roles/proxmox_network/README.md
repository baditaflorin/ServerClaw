# proxmox_network

Applies the Proxmox host bridge, NAT, nftables, and per-VM firewall baseline.

Inputs: management interface settings, bridge names, internal network values, ingress-forwarding topology, guest inventory, and canonical `network_policy` rules. Guest inventory entries may set `proxmox_firewall_enabled: false` when a VM should rely on its in-guest firewall instead of the Proxmox `fwbr*` bridge path.
Outputs: `/etc/network/interfaces`, `/etc/nftables.conf`, `/etc/pve/firewall/<vmid>.fw`, a managed conntrack helper for `fwbr+` traffic, and active forwarding/NAT plus Proxmox VM firewall state.

## Scoped run: only the per-VM firewall files

`--tags proxmox-vm-firewall` runs a narrow slice of the role (for example `ansible-playbook playbooks/guest-network-policy.yml --tags proxmox-vm-firewall --limit proxmox-host`; the operator steps are in `docs/runbooks/configure-guest-network-policy.md`):

- It does: create `/etc/pve/firewall`, read `qm config` for each declared guest (also in `--check` mode), select the guests to manage (`-e proxmox_network_firewall_vmids=155`, default: every guest that exists), render `vm.fw.j2` to `/root/.lv3-vm-<vmid>.fw` (also in `--check` mode), compare each render with the LIVE `/etc/pve/firewall/<vmid>.fw` and print the diff, install the renders that differ, `pve-firewall compile`, and `pve-firewall restart` only when at least one file changed.
- The install guard (`files/pve_fw_guard.py`): the live files also hold rules the render does not know (hand-authored rules, a migrated set, managed blocks such as `# BEGIN fleet-pool-fw`), so the run fails before writing anything when a VM's live file has a rule or option line, or a managed block, that the render would remove, unless the operator passes `-e proxmox_network_allow_rule_removal=true`. Additive installs and new files go through. Every file the run replaces is first copied to `/root/fw-backup-<UTC timestamp>/` with a `restore.sh`, and the play prints the restore command. `--check` gives the same answer as the real run and writes nothing live. See "The install guard" in `docs/runbooks/configure-guest-network-policy.md`; `tests/test_pve_firewall_install_guard.py` pins it.
- It always runs the input validation and both SAFETY GUARD asserts (tag `always`), so the RFC 5737/3849 placeholder-address refusal applies exactly as in a full run, and no tag selection, including `--skip-tags proxmox-vm-firewall`, skips them. The identity overlay is therefore still required.
- It does not touch `/etc/network/interfaces`, `/etc/nftables.conf`, forwarding, the conntrack helper or its service, the `pve-firewall` service enablement, a guest's `net0` firewall flag, or a guest's power state. In particular the full run's "stop and start guests that need firewall activation" branch never runs in a scoped run: that branch also fires for any guest whose SSH port is unreachable, which is not wanted when only a rule changed.
- The matching second play of `guest-network-policy.yml` gathers no facts when `proxmox-vm-firewall` is the only selected tag (fact gathering ignores `--tags`), so the scoped run reaches the Proxmox host only.

Adding a task to this role: decide on purpose whether it belongs to the scoped slice. `tests/test_proxmox_network_vm_firewall_tag.py` lists every task under one of three headings (guards, per-VM firewall, outside the slice) and fails on a task that is in none of them.
