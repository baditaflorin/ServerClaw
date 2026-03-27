# Configure Headscale

This runbook converges ADR 0144 by deploying Headscale on the Proxmox host, publishing it at `https://headscale.lv3.org` through the existing NGINX edge VM, and migrating the LV3 management mesh from the hosted Tailscale control plane to the repo-managed Headscale control plane.

## Preconditions

- `make validate` passes on the repo state being applied.
- The Proxmox host is still reachable over the current private path before cutover starts.
- The NGINX edge VM is healthy and can already publish `lv3.org` hostnames.
- You have the bootstrap SSH key at `.local/ssh/hetzner_llm_agents_ed25519`.
- You are prepared to keep one Proxmox SSH session open during host migration.

## Repository Converge

Run the targeted Headscale converge:

```bash
make converge-headscale
```

This does the following:

1. installs the pinned Headscale package on `proxmox_florin`
2. renders `/etc/headscale/config.yaml`
3. installs the managed ACL file from `config/headscale-acl.hujson`
4. starts and verifies the `headscale` systemd unit
5. republishes the NGINX edge so `headscale.lv3.org` proxies to `10.10.10.1:8080`

## Bootstrap Users And Keys

Create the first named user and the controller API key on the Proxmox host:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@<current-mesh-ip> sudo headscale --config /etc/headscale/config.yaml users create 'ops@'
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@<current-mesh-ip> sudo headscale --config /etc/headscale/config.yaml apikeys create --expiration 720h
```

Persist the API key locally:

```bash
mkdir -p .local/headscale
chmod 700 .local/headscale
printf '%s\n' '<generated-api-key>' > .local/headscale/api-key.txt
chmod 600 .local/headscale/api-key.txt
```

Create the reusable host key for the Proxmox node:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@<current-mesh-ip> sudo headscale --config /etc/headscale/config.yaml preauthkeys create --user 'ops@' --reusable --expiration 24h
```

Create a reusable user key for operator laptops:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@<current-mesh-ip> sudo headscale --config /etc/headscale/config.yaml preauthkeys create --user 'ops@' --reusable --expiration 24h
```

## Migration Order

Keep the current Proxmox SSH session open and migrate in this order:

1. move the Proxmox host to Headscale
2. verify the new Headscale-assigned host IP and route advertisement
3. move the operator workstation to Headscale
4. rerun `make converge-headscale` so the repo-managed route approval is reconciled against the newly enrolled host
5. verify direct host SSH and guest reachability over `10.10.10.0/24`

Recommended host cutover command:

```bash
sudo tailscale logout
sudo tailscale up \
  --login-server=https://headscale.lv3.org \
  --auth-key='<proxmox-host-key>' \
  --hostname='proxmox-florin-subnet-router' \
  --accept-dns=false \
  --advertise-routes='10.10.10.0/24' \
  --snat-subnet-routes=true \
  --ssh=false \
  --stateful-filtering=false
```

Recommended workstation cutover command on macOS:

```bash
'/Applications/Tailscale.app/Contents/MacOS/Tailscale' logout
'/Applications/Tailscale.app/Contents/MacOS/Tailscale' up --login-server=https://headscale.lv3.org --auth-key='<operator-key>' --accept-dns=false
```

## Verification

Verify the control plane itself:

```bash
curl -I https://headscale.lv3.org/health
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@<new-headscale-ip> sudo headscale --config /etc/headscale/config.yaml nodes list
```

Verify the route and ACLs from the operator workstation:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@<new-headscale-ip> hostname
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@10.10.10.30 hostname
ping -c 3 10.10.10.30
```

Expected outcome:

- `headscale.lv3.org/health` returns `200`
- `headscale nodes list` shows the workstation plus the Proxmox host under the `ops@` user
- the Proxmox host advertises `10.10.10.0/24`
- the operator workstation can reach `10.10.10.30`

## Rollback

If the Headscale control plane is healthy but node migration fails, keep the host on the current control plane and fix the policy or key issue before retrying.

If the host migration breaks access, use the still-open SSH session to return the host to the previous control plane immediately:

```bash
sudo tailscale logout
sudo /usr/local/sbin/lv3-tailscale-up
```

Do not close the original session until the new Headscale IP has been verified end to end.
