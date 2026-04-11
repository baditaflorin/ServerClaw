# Configure ntopng Private Flow Visibility

## Purpose

This runbook converges ADR 0059 by installing `ntopng` on the Proxmox host, capturing the private guest bridge plus edge-adjacent traffic, and exposing the UI only through the host Tailscale address.

The initial collection design is:

- capture `vmbr10` for east-west guest traffic and guest egress visibility
- capture `vmbr0` for public-edge and ingress context
- keep the UI private at `http://100.118.189.95:3001`
- avoid public DNS publication and long-term external flow export on day one

## Command

```bash
make converge-ntopng
```

## What the playbook does

1. Adds the official ntop APT repository for Debian 13.
2. Installs `redis-server` and `ntopng` on `proxmox-host`.
3. Renders repo-managed ntopng config under `/etc/ntopng/ntopng.conf.d/90-lv3.conf`.
4. Defines local networks for `10.10.10.0/24` and the Tailscale management range.
5. Generates and stores a managed ntopng admin password at `/etc/lv3/ntopng/admin-password`.
6. Stores the admin-password hash in Redis and marks the default password as rotated.
7. Exposes ntopng only through the existing host Tailscale proxy pattern on port `3001`.
8. Updates the Proxmox firewall allow-list so the private proxy port is reachable only from declared management sources.
9. Verifies the proxied ntopng REST surface, monitored interface list, and visible traffic on `vmbr10`.

## Operator Access

The steady-state operator path is the host Tailscale address:

- URL: [http://100.118.189.95:3001](http://100.118.189.95:3001)
- username: `admin`
- password source: `/etc/lv3/ntopng/admin-password` on the Proxmox host

Retrieve the password:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo cat /etc/lv3/ntopng/admin-password'
```

There is intentionally no public hostname for ntopng.

## Verification

Syntax-check the dedicated ntopng playbook:

```bash
make syntax-check-ntopng
```

Verify the runtime services on the host:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo systemctl is-active redis-server ntopng'
```

Verify the operator-only proxied interface list:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'PASS=$(sudo cat /etc/lv3/ntopng/admin-password); curl -fsS -u admin:${PASS} http://100.118.189.95:3001/lua/rest/v2/get/ntopng/interfaces.lua'
```

Generate a small amount of private-bridge traffic and verify interface counters:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'ping -c 3 10.10.10.10 >/dev/null; PASS=$(sudo cat /etc/lv3/ntopng/admin-password); IFID=$(curl -fsS -u admin:${PASS} http://100.118.189.95:3001/lua/rest/v2/get/ntopng/interfaces.lua | jq -r '\''.rsp[] | select(.ifname=="vmbr10") | .ifid'\''); curl -fsS -u admin:${PASS} "http://100.118.189.95:3001/lua/rest/v2/get/interface/data.lua?ifid=${IFID}"'
```

Inspect the top hosts on the private bridge:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'PASS=$(sudo cat /etc/lv3/ntopng/admin-password); IFID=$(curl -fsS -u admin:${PASS} http://100.118.189.95:3001/lua/rest/v2/get/ntopng/interfaces.lua | jq -r '\''.rsp[] | select(.ifname=="vmbr10") | .ifid'\''); curl -fsS -u admin:${PASS} "http://100.118.189.95:3001/lua/rest/v2/get/interface/top/hosts.lua?ifid=${IFID}"'
```

Expected result:

- the ntopng UI is reachable only on the Tailscale address and proxy port
- the monitored interface list includes `vmbr10` and `vmbr0`
- `vmbr10` counters and top-host data show live private-network activity

## Notes

- The first implementation keeps ntopng host-local to avoid introducing nProbe or a mirrored traffic fabric.
- The first implementation does not publish ntopng through the public edge and does not export flows to a long-term external store.
