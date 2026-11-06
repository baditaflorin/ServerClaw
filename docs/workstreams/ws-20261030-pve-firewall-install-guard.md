# WS-20261030: The per-VM Proxmox firewall install can no longer delete live rules

## Status

In progress. Nothing is applied: no host was contacted, no play ran against a live hypervisor, no `[live-apply]` marker. The tests run the guard against fixtures and the role against a temporary "live" directory with stand-ins for `qm` and `pve-firewall`.

## Why

`ansible-playbook playbooks/guest-network-policy.yml --tags proxmox-vm-firewall` (the proxmox_network role, ws-0541) rendered each VM's policy to a staging copy `/root/.lv3-vm-<vmid>.fw` and installed it over `/etc/pve/firewall/<vmid>.fw` without merging. The live files have other writers than `vm.fw.j2`: hand-authored rules with comments, an `AUTO-MIGRATED` set, and on VM 191 of 0mcp a `# BEGIN fleet-pool-fw` block generated from `firewall-pools.json`.

On 2026-10-30 about 07:57 UTC that slice was applied on 0mcp after a `--check --diff` that showed 19 added lines and no removal. The diff had compared the render with the staging copies, not with the live files, and the copy step is skipped in check mode. The apply removed about 25 production rules for about three minutes (Prometheus 9100 scrape accepts on ten VMs, the `creators` nginx rule to Creator Atlas on VM 122, the VM 191 to VM 154 PostgreSQL ssh tunnel, the keystore failover chain, cAdvisor 9280, the whole `fleet-pool-fw` block) and network-policy drift went from 0 to 11 VMs. The whole directory was restored from a backup taken before the run, `diff -r` was clean and drift was 0 again.

A second defect made check mode untrustworthy in the same way: `qm config` is skipped in check mode and a skipped command reports `rc=0`, so a check run treated every declared guest as existing, including ones the real run skips.

## Change

`roles/proxmox_network/files/pve_fw_guard.py` (standard library only; Python 3.9 or newer on the hypervisor) is now the only code that writes a live per-VM file. The role calls it twice, `plan` (read only) and `apply`, with the same flags, so the check-mode answer is the real run's answer.

- **Diff against the live file, per VM, before every install.** The report prints one unified diff (live to render) per VM, a headline (`unchanged`, `NEW file`, `additive`, `REMOVES n live rule/option line(s) and m managed block(s)`) and one `!! REMOVED [section] <line>` per removed line, tagged with the managed block it sat in. `--check --diff` prints exactly this; the render is written to the staging copy in check mode too (`check_mode: false`, `diff: false` on that task, it is scratch Proxmox never reads), so the comparison tests what the real run would install.
- **Refusal before any write.** A removal is a rule, option, alias or ipset line, in any section, that the live file has and the render does not (a disabled `|IN ACCEPT` line and a changed rule's old line included), or a `# BEGIN <label>` ... `# END <label>` block the render does not carry. The play fails at a dedicated assert (`REFUSED, nothing was written`) and `apply` re-checks on its own with the same flags, so removing the assert does not remove the guard. One refused VM stops the whole install, including the additive VMs of the same run, and nothing is written, not even a backup. `-e proxmox_network_allow_rule_removal=true` allows it for one run (default `false`; the variable is declared in the role defaults and argument spec and a test pins that no inventory file sets it). Additions, a new file (VM 155's first install), spacing, order, repeated lines, trailing `# comment`s and comment lines are not removals.
- **Backup and restore command.** Before the first write the guard copies every live file it is about to replace to `/root/fw-backup-<UTC timestamp>/<vmid>.fw`, writes `restore.sh` (copy each file back with `cp -p`, delete the files the run created, `pve-firewall restart`) and the play prints `Restore them with: sh /root/fw-backup-<ts>/restore.sh`. The install is read back after each write; on a failure the files already written are put back.
- **Naming the VMs.** `-e proxmox_network_firewall_vmids=155` (or `155,191`, or a JSON list) limits the render, the comparison and the install to those VMs; naming a guest that does not exist fails. Without it a single VM whose live file holds lines the render lacks (on 0mcp today VM 191, and the VMs whose live hand edits the inventory does not carry yet) would stop the whole slice, and VM 155's additive file could never be installed through it.
- **Check mode plans the real run's guests.** `Read current guest configurations` (`qm config`, read only) has `check_mode: false`, so a guest that does not exist yet is not planned.
- The staging, live and backup directories are role variables (`proxmox_network_firewall_stage_dir`, `_live_dir`, `_backup_root`) with the production paths as defaults; they exist so the tests can run the real role against a temporary directory.

Also in this change: `docs/runbooks/configure-guest-network-policy.md` (a warning at the top of "Render only the per-VM Proxmox firewall files", the corrected steps, a new "The install guard" section) and `docs/runbooks/pbs-0own-backups.md` (the 0mcp job `fleet-nightly-0mcp` runs with fleecing on `local-nvme`; the job is set by hand with `pvesh` and is in no role). The fleecing change itself was made on the hypervisor on 2026-10-30 about 07:50 UTC and verified on VM 155; only its record is in this change.

## Verification and rollback

- `tests/test_pve_firewall_install_guard.py` (fixtures in `tests/fixtures/pve_firewall_guard/`): the guard refuses the incident shape (VM 191: hand-authored rules, an AUTO-MIGRATED set, a disabled rule, a `fleet-pool-fw` block) with every live file unchanged and no backup directory; `plan` and `apply` give the same refusal and `plan` writes nothing; additions, a new file and an unchanged file are allowed, backed up and restorable (the generated `restore.sh` is run); a second install changes nothing and takes no backup; 15 parametrised removal and non-removal cases; a failed write rolls the earlier writes back; a missing or empty render is an error, not an empty desired state; static pins on the role (order, `check_mode`, the operator variable only on the command line, no other task writes the live directory).
- The same file runs the real role with `ansible-playbook --tags proxmox-vm-firewall` on localhost against a temporary directory with stand-ins for `qm` and `pve-firewall`: `--check --diff` fails on a removal and prints the live diff, writes nothing and calls nothing; a real run fails the same way; `-e proxmox_network_allow_rule_removal=true` backs up, installs and prints the restore command; an additive run installs a new VM file, the second run changes nothing and does not restart `pve-firewall`; naming VM 155 installs it while VM 191 still holds extra rules; naming a guest that does not exist fails.
- Mutation check: a guard that never flags a removal, a render without `check_mode: false`, an install without the backup, and an `apply` that ignores the operator variable are each caught by a test.
- `test_proxmox_network_vm_firewall_tag.py` and `test_proxmox_network_role.py` were updated for the new tasks (the scoped selection is the guards plus the per-VM tasks, none of which reach host networking or a guest's power state); both still pass, including the `--list-tasks` run through Ansible itself.
- Roll back by reverting this change: the role then installs the render over the live file again (the behaviour that caused the incident), so revert only together with a decision not to run the slice.

## Live apply

None. The guard takes effect the next time the slice or the full play runs on a hypervisor. The first use, if it is for VM 155 on 0mcp: run the `--check --diff` with `-e proxmox_network_firewall_vmids=155`, read the diff, run it for real, then `diff -r /root/fw-backup-<ts> /etc/pve/firewall` and `scripts/netpolicy.py drift --live`. The live 0mcp hypervisor is already correct (drift 0, VM 155's file installed by hand on 2026-10-30); this change does not touch it.

## Not in this change

- Making the inventory render carry the live-only lines (the Prometheus 9100 accepts, the tailnet accepts on VM 140, the `fleet-pool-fw` block of VM 191): until it does, the render is not the source of truth for those VMs and the slice is used for the VMs the inventory fully describes.
- Putting the 0mcp backup job under a role or inventory file.
- Merging live comments into the installed file (comments the render lacks are dropped on install, counted in the report and kept in the backup).
