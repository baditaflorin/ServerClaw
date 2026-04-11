# Configure Tailscale Private Access

## Purpose

This runbook converges ADR 0014 by making the Proxmox host reachable on its Tailscale private IP for routine administration and, when approved in the tailnet, the subnet router for the private guest network `10.10.10.0/24`.

The steady-state operator path is:

- first: direct SSH to the Proxmox host over its Tailscale IP
- second: direct private-IP access to guests over Tailscale only when the subnet route is approved and needed

## Result

- `tailscaled` is installed on `proxmox-host`
- operator laptops can reach the Proxmox host on its Tailscale IP from any network
- the Proxmox host advertises `10.10.10.0/24` into the tailnet
- operator laptops reach guests directly on `10.10.10.0/24`
- the inventory defaults to direct guest SSH without a jump host
- the Proxmox host jump path remains available as break-glass

## Automation Surface

- make target: `make configure-tailscale`
- role: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/proxmox_tailscale/tasks/main.yml`
- host helper: `/usr/local/sbin/lv3-tailscale-up`

## Apply

Preferred unattended apply with an auth key passed only for the current run:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
TAILSCALE_AUTH_KEY=tskey-example make configure-tailscale
```

Interactive apply when you do not want to pass an auth key through automation:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
make configure-tailscale
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@203.0.113.1
sudo /usr/local/sbin/lv3-tailscale-up
```

If the host is not already attached to the tailnet, the helper prints the Tailscale login URL.

## Tailnet Approval Requirements

- the Proxmox host should appear in Tailscale as `proxmox-host-subnet-router`
- approve the advertised route `10.10.10.0/24` unless tailnet auto-approvers are already configured
- if you later switch to a tagged auth key, update tailnet `tagOwners` before rerunning the helper

## Operator Onboarding

1. Install Tailscale on the operator laptop and sign in to the same tailnet as the Proxmox host.
2. Verify direct host administration first:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95
```

3. Accept the route to `10.10.10.0/24` only if direct guest access is required.
4. On Linux laptops, enable route acceptance explicitly:

```bash
sudo tailscale up --accept-routes=true
```

5. Reach the build VM directly over the routed private subnet:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@10.10.10.30
```

6. Once that works, use the normal guest inventory without a jump host override.

## Verification

Host-side verification:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95
sudo tailscale ip -4
sudo tailscale status
```

Operator-path verification for the host:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'hostname'
```

Operator-path verification for direct guest access:

```bash
ping -c 3 10.10.10.30
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@10.10.10.30 'hostname && ip -4 addr show'
ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/hosts.yml docker-build -m command -a 'hostname' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519
```

Expected result:

- the laptop reaches the Proxmox host over `100.118.189.95` from any network
- when the subnet route is approved, the laptop reaches `10.10.10.30` directly without `ProxyJump`
- guest SSH still lands on `ops`
- the Ansible ad hoc command succeeds with the default inventory path

## Break-Glass Fallback

Use the old Proxmox jump path only when Tailscale is unavailable or route approval is still pending.

Direct SSH fallback command:

```bash
ssh -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@203.0.113.1 -W %h:%p' \
  -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  ops@10.10.10.30
```

Ansible fallback command:

```bash
ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/hosts.yml docker-build -m command -a 'hostname' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```
