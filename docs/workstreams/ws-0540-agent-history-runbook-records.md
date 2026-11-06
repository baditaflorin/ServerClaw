# WS-0540: Record the first agent-history provisioning run and the VM 130 trim

## Status

In progress. The pull request is open and not merged; nothing is applied. No `[live-apply]` marker.

## Goal

VM 155 was provisioned on 2026-10-29. The invocation that worked and the traps met on the first run lived only in a session's notes, and the memory and builder-slot cut of VM 130 that made room for the guest was applied live with no record in git. This change writes both down. Docs and one inventory number only: nothing is applied and no host is contacted.

## Change

- `docs/runbooks/configure-agent-history.md`: a new section "Provisioning record and traps (first run, 2026-10-29)" with the working `make provision-agent-history-vm` invocation (generic placeholders, no real address, key or tailnet name), the overlay inventory, and seven traps (the cut-off first boot and how to rescue a guest, empty apt lists, tailscale enrolment and Tailnet Lock, the two firewall layers for OpenBao, the docker.io conflict, dropped images, the locked LUKS volume); preconditions 6 and 7 corrected (the co-owner removal is ws-0538; a fresh worktree does work); the purpose paragraph no longer says nothing has been run.
- The hypervisor firewall line added by hand on 2026-10-29 (`IN ACCEPT -source 10.10.10.55/32 -p tcp -dport 8201` in `/etc/pve/firewall/192.fw`) is recorded with the reason it was not rendered: `proxmox_network` is the first play of `guest-network-policy.yml`, which `--limit runtime-control` skips, and a full run replays the whole hypervisor network. The declared rule renders exactly that line (checked by rendering `vm.fw.j2` against the inventory); a full run also adds six `all_guests` ports for the new guest. A scoped way to render only the per-VM files does not exist (the tasks carry no tag): left as a follow-up.
- `inventory/host_vars/proxmox-host.yml`: VM 130 `memory_mb` 12288 -> 10240 with a comment (the live floor and the owner's declared capacity; the live maximum stays 20 GiB until a restart).
- `config/0mcp/docker-build-lv3/README.md`: the memory and slot facts (balloon floor 10 GiB since 2026-10-29, slots 7 -> 3: ci.0exec agent 90 = 1, slot-2 = 1, slot-3 retired, ci.0mcp agent = 1), measured effect, backups, traps and rollback; says that `files/` was not refreshed.
- `docs/adr/0494-agent-history.md`: the Activation header line says the guest was provisioned.
