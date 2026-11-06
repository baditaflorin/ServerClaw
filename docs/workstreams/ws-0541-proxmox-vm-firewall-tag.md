# WS-0541: A tag that renders only the per-VM Proxmox firewall files

## Status

In progress. The pull request is open and not merged; nothing is applied and no host is contacted. No `[live-apply]` marker.

## Goal

The per-VM Proxmox firewall files (`/etc/pve/firewall/<vmid>.fw`) were rendered only by the `proxmox_network` role, the first play of `playbooks/guest-network-policy.yml`. A run limited to a guest skips that play, and a full run replays the whole hypervisor network (interfaces, nftables, forwarding, guest NIC flags, guest restarts) and refuses the committed placeholder addresses. On 2026-10-29 one OpenBao rule for the agent-history guest had to be appended to `/etc/pve/firewall/192.fw` by hand (recorded in `docs/runbooks/configure-agent-history.md`, ws-0540). This change gives the repo a safe, scoped way to render only those files, so that hand edit is no longer needed.

## Change

- `roles/proxmox_network/tasks/main.yml`: the seven per-VM firewall tasks carry the tag `proxmox-vm-firewall` (create `/etc/pve/firewall`, read `qm config`, record existing guests, render `vm.fw.j2`, install on difference, `pve-firewall compile`, conditional `pve-firewall restart`). The input validation and both SAFETY GUARD asserts carry `always`, so the placeholder-address refusal runs in the scoped run and cannot be skipped by any tag selection. Everything else (interfaces, nftables, forwarding, conntrack helper, `net0` enablement, `pve-firewall` service enablement, SSH reachability, guest stop/start/wait) stays untagged and does not run in a scoped run. The restart condition reads the `net0` register through an explicit `default`, because that task's register is never defined in a scoped run.
- `playbooks/guest-network-policy.yml` (and the identical collection copy): the second play (`lv3_guests`) gathers facts unless `proxmox-vm-firewall` is the only selected tag. Fact gathering ignores `--tags`, so without this the scoped run would connect to every guest.
- Decision on the guest stop/start branch: it does not run in a scoped run. Its trigger set includes any guest whose SSH port is unreachable, which has nothing to do with a rule change; a rule change must never power-cycle a guest. A guest whose `net0` flag changes still needs the full play.
- `tests/test_proxmox_network_vm_firewall_tag.py`: pins the tagged set (guards plus exactly the seven tasks, in order), that every task is classified once, that the guards are `always`, that nothing outside the slice carries the tag, that scoped tasks do not mention interfaces, nftables, forwarding or guest power, that scoped tasks only read variables a scoped run still defines, the restart condition, the playbook gather-facts expression and the two playbook copies; plus one test that asks `ansible-playbook --list-tasks` (skipped when Ansible is absent).
- `docs/runbooks/configure-guest-network-policy.md`: a section "Render only the per-VM Proxmox firewall files" (commands, what it does, what it does not do, the overwrite and `--check` caveats), and a corrected note on `--limit proxmox-host`, which still replays the whole role.
- `roles/proxmox_network/README.md`: the scoped run and the rule for adding a task.
- `docs/runbooks/configure-agent-history.md`: trap 4 no longer says a scoped way does not exist; it points to the new runbook section.
