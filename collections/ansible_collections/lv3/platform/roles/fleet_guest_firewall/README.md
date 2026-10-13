# fleet_guest_firewall

A small nftables role for fleet guests that `lv3.platform.linux_guest_firewall` cannot serve, because that role derives
its rules from the 0mcp `network_policy` / `proxmox_guests` data. It keeps the same rule vocabulary
(`protocol`, `ports`, `source`, `description`) so a rule can move between the two mechanisms without being rewritten.

The 0mcp `nginx` guest keeps using `linux_guest_firewall` (rule in `inventory/host_vars/proxmox-host.yml`). This role is
for the 0own `github-mirror` guest, where only the monitoring VM's tailnet address may reach tcp 9100 on `tailscale0`.

Safety: the file is validated with `nft -c` before it replaces the live one, at least one tcp rule must keep port 22
reachable, the ruleset is reloaded only when the file changed, and the play waits for SSH afterwards.
