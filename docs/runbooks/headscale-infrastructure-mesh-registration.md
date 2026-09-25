# Runbook: Headscale Infrastructure Mesh Network Registration

**Purpose**: Register Proxmox infrastructure nodes to the Headscale VPN mesh network, enabling secure remote access to 100.64.0.0/10 infrastructure addresses.

**When to Use This**:
- First-time setup of a Proxmox deployment with Headscale
- Adding new VMs/hosts to the mesh network
- Re-registering nodes after Headscale resets
- Troubleshooting infrastructure connectivity

**Prerequisites**:
- Headscale server running and accessible at `headscale.{platform_domain}`
- Direct SSH/console access to the Proxmox hypervisor or target VM
- Registration key from Headscale admin

---

## Overview

The Headscale mesh network provides:
- **Secure mesh VPN**: All infrastructure nodes can reach each other at 100.64.x.x addresses
- **Remote access**: Your client machine (MacBook) can reach infrastructure without public IPs
- **Zero-trust networking**: All traffic encrypted, no port forwarding needed

**Network topology**:
```
Your Client (MacBook)
    ↓ (Tailscale VPN)
Headscale Gateway (100.64.0.1)
    ↓
Proxmox Hosts & VMs (100.64.x.x)
    └─ runtime-control (10.10.10.92)
    └─ postgres-vm (10.10.10.60)
    └─ nginx-edge (10.10.10.10)
    └─ [other infrastructure]
```

---

## Step 1: Obtain Registration Key from Headscale Admin

**Location**: On the Headscale server, request a new registration key

If you have Headscale admin access:
```bash
# SSH to headscale server
ssh headscale.example.org

# Generate a new registration key
headscale preauthkeys create --user default --reusable --expiration 24h
```

**Output** (example):
```
Key: JQb6Y-VqYZn7zzFVWhkxZlvp
```

**Key properties**:
- `--reusable`: Can be used by multiple nodes
- `--expiration 24h`: Valid for 24 hours (adjust as needed)
- Default user: `default` (or specify `--user USERNAME` for other users)

**Save this key** - you'll use it in the next step.

---

## Step 2: Register Infrastructure Node to Headscale Mesh

### Option A: Register via Proxmox Hypervisor Console

**Step A1: Access Proxmox hypervisor directly**

```bash
# SSH to Proxmox host (requires bootstrap SSH key or direct console access)
ssh -i .local/ssh/bootstrap.id_ed25519 root@proxmox-host-ip

# Or use Proxmox web UI console at https://proxmox-host-ip:8006
```

**Step A2: Register the Proxmox host node itself**

```bash
# On the Proxmox hypervisor, register it as a Headscale node
headscale nodes register \
  --key JQb6Y-VqYZn7zzFVWhkxZlvp \
  --user default

# Output:
# Node registered: proxmox-host
# Mesh IP: 100.64.0.2 (or similar)
```

### Option B: Register a Specific VM

**Step B1: SSH into the target VM**

```bash
# Through Proxmox host (requires SSH key setup)
ssh -i .local/ssh/bootstrap.id_ed25519 \
  -o ProxyCommand="ssh -i .local/ssh/bootstrap.id_ed25519 root@proxmox-host-ip -W %h:%p" \
  root@10.10.10.92

# Or access via Proxmox web UI console for the VM
```

**Step B2: Register the VM to Headscale**

```bash
# On the target VM
headscale nodes register \
  --key JQb6Y-VqYZn7zzFVWhkxZlvp \
  --user default

# Output:
# Node registered: runtime-control-vm
# Mesh IP: 100.64.0.3 (or similar)
```

---

## Step 3: Verify Node Registration

### From Headscale Server

```bash
# SSH to Headscale server
ssh headscale.example.org

# List all registered nodes
headscale nodes list

# Output:
# ID | Hostname          | IP Address      | Last Seen
# 1  | proxmox-host      | 100.64.0.2      | 2 minutes ago
# 2  | runtime-control   | 100.64.0.3      | 1 minute ago
```

### From Your Client Machine

**Step 3A: Authenticate your client to Headscale**

```bash
# On your MacBook
tailscale up --login-server=https://headscale.example.org

# Follow the browser link to authenticate:
# https://headscale.example.org/register/YOUR-KEY
```

**Step 3B: Verify mesh connectivity**

```bash
# From your MacBook, ping infrastructure nodes
ping 100.64.0.2    # Proxmox host
ping 100.64.0.3    # Runtime control VM
ping 100.64.0.1    # Headscale gateway itself

# Expected: successful pings with low latency (< 100ms)
```

---

## Step 4: Use Mesh Network to Access Infrastructure

### SSH Through Mesh Network

**SSH to Proxmox hypervisor via mesh**:
```bash
ssh -i .local/ssh/bootstrap.id_ed25519 root@100.64.0.2
```

**SSH to infrastructure VM via mesh**:
```bash
ssh -i .local/ssh/bootstrap.id_ed25519 ops@100.64.0.3
```

### Run Ansible Playbooks via Mesh

**Update inventory to use mesh IPs** (in `.local/identity.yml` or dynamically):
```yaml
ansible_host: 100.64.0.3  # Use mesh IP instead of 10.10.10.x
```

**Run convergence playbook**:
```bash
# From your MacBook (with Headscale VPN connected)
make converge-nginx-edge env=production
```

Ansible will SSH through the Headscale mesh to reach infrastructure.

---

## Troubleshooting

### Registration fails: "Cannot connect to Headscale"

**Cause**: Headscale server not reachable from the node

**Fix**:
```bash
# On the infrastructure node, verify Headscale is reachable
curl -I https://headscale.example.org/
# Should return HTTP 200

# If DNS fails, check:
cat /etc/resolv.conf

# If firewall blocks, check:
sudo ufw status
sudo ufw allow 443/tcp  # HTTPS for Headscale
```

### Node appears in `headscale nodes list` but won't connect

**Cause**: Node registered but not actively maintaining connection

**Fix**:
```bash
# On the infrastructure node, install Tailscale agent
apt-get update && apt-get install -y tailscale

# Start Tailscale service
systemctl enable tailscale
systemctl start tailscale

# Join mesh with registration key
tailscale up --login-server=https://headscale.example.org \
  --auth-key JQb6Y-VqYZn7zzFVWhkxZlvp
```

### Client can't reach infrastructure mesh IPs

**Cause**: Client not connected to Headscale mesh

**Fix**:
```bash
# On your MacBook, check Tailscale status
tailscale status

# Should show:
# 100.64.0.2    proxmox-host         Derp(...)
# 100.64.0.3    runtime-control      Derp(...)

# If offline, reconnect:
tailscale up --login-server=https://headscale.example.org
```

### Registration key expired

**Symptom**: `Error: invalid auth key` when trying to register

**Fix**: Request a new registration key from Headscale admin (repeat Step 1)

---

## Multi-Deployment Setup (example.com vs example.org)

If managing multiple Proxmox deployments:

### For each deployment, create separate Headscale namespaces:

```bash
# On Headscale server
headscale users create lv3
headscale users create 0fork

# Generate separate keys for each
headscale preauthkeys create --user lv3 --reusable
headscale preauthkeys create --user 0fork --reusable
```

### Register nodes to their respective namespaces:

```bash
# LV3 deployment nodes
headscale nodes register --key LV3_KEY --user lv3

# 0fork deployment nodes
headscale nodes register --key 0FORK_KEY --user 0fork
```

### View namespace-specific nodes:

```bash
headscale nodes list --user lv3
headscale nodes list --user 0fork
```

---

## Reference: Full Registration Flow

```bash
# 1. On Headscale server: Create registration key
headscale preauthkeys create --user default --reusable --expiration 24h
# Output: JQb6Y-VqYZn7zzFVWhkxZlvp

# 2. On infrastructure node: Register to mesh
headscale nodes register --key JQb6Y-VqYZn7zzFVWhkxZlvp --user default
# Output: Node registered: example-host, Mesh IP: 100.64.0.5

# 3. On Headscale server: Verify registration
headscale nodes list
# Shows: example-host | 100.64.0.5 | 30 seconds ago

# 4. On your client: Authenticate to Headscale
tailscale up --login-server=https://headscale.example.org
# Visit: https://headscale.example.org/register/YOUR-KEY

# 5. On your client: Verify connectivity
tailscale status
ping 100.64.0.5
ssh root@100.64.0.5  # Should work

# 6. Use mesh for infrastructure access
make converge-nginx-edge env=production  # Uses SSH through mesh
```

---

## Related Documentation

- **ADR 0480**: Universal Secret Masking (credentials in mesh environment)
- **ADR 0407**: Deployment-Specific Values (platform_domain configuration)
- **Postmortem 2026-05-05**: Multi-Deployment Certificate Validation & Headscale integration

---

## Version History

- **2026-05-06**: Initial runbook creation with example.org Headscale integration
