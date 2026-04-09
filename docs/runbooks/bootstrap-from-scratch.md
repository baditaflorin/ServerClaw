# Bootstrap from Scratch

**ADR:** 0386
**Last verified:** 2026-04-09

This runbook takes you from "I have a server" to "platform fully operational."
It is the single document you need to read.

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **Server** | Dedicated or virtual x86_64 server with Debian 13 (Trixie) |
| **RAM** | 32 GB minimum (16 GB absolute minimum for reduced services) |
| **Disk** | 500 GB NVMe recommended |
| **Network** | Public IPv4 address, SSH access |
| **Domain** | A domain you control (for DNS records and TLS) |
| **Dev machine** | macOS or Linux with Ansible, Python 3.12+, Docker, SSH |

## Quick Start (Docker Development)

If you just want to try the platform locally without a server:

```bash
git clone <repo-url> && cd proxmox_florin_server
make init-local              # Generate SSH keys and secrets
make docker-dev-up           # Start 4 containers (8 GB RAM)
make docker-dev-converge     # Deploy services via Ansible
```

See `docker-dev/README.md` for details.

---

## Full Server Bootstrap

### Step 1: Clone and Initialize

```bash
# Clone the repo
git clone <repo-url> && cd proxmox_florin_server

# Install git hooks and dependencies
make setup

# Generate the .local/ overlay with SSH keys and secrets
make init-local
```

After `make init-local` completes, it prints a list of external secrets you
must provide (API keys, domain registrar tokens, etc.). Fill those in before
proceeding.

### Step 2: Choose Your Provider Profile

Review the provider profiles in `config/provider-profiles/`:

| Profile | File | When to use |
|---------|------|-------------|
| **Hetzner Dedicated** | `hetzner-dedicated.yaml` | Hetzner bare-metal server |
| **Generic Debian** | `generic-debian.yaml` | Any Debian 13 server |
| **Home Lab** | `homelab.yaml` | Local development or home server |

Each profile lists the exact steps for that provider. The steps below
follow the generic path.

### Step 3: Prepare the Server

1. Ensure the server is running **Debian 13** (Trixie)
2. Ensure **root SSH access** works
3. Inject the bootstrap SSH key:

```bash
# Copy the generated public key to the server
ssh-copy-id -i .local/ssh/bootstrap.id_ed25519.pub root@<SERVER_IP>

# Verify key-based access works
ssh -i .local/ssh/bootstrap.id_ed25519 root@<SERVER_IP> 'echo OK'
```

### Step 4: Update Inventory

Copy the inventory template and customize:

```bash
cp inventory/hosts.yml.example inventory/hosts.yml
```

Edit `inventory/hosts.yml`:
- Replace `your-proxmox-host` with your hostname
- Replace `<SERVER_IP>` with your server's IP address
- Rename guest hostnames to match your naming convention
- Adjust guest IP addresses if your subnet differs from `10.10.10.0/24`

### Step 5: Install Proxmox VE

```bash
make install-proxmox
```

This runs `playbooks/site.yml` with the Proxmox installation tags. It:
- Adds Proxmox repositories
- Installs the PVE kernel and packages
- Creates the `ops` user with sudo
- Configures networking (bridges for guest VMs)
- Sets up Tailscale/Headscale VPN (if configured)
- Hardens SSH access

**Verify:**

```bash
make verify-bootstrap-proxmox
```

Expected output: Proxmox VE version, storage pools, ops user present, KVM available.

### Step 6: Configure Network and Access

```bash
make configure-network
make configure-tailscale     # Optional: VPN access
make harden-access
```

### Step 7: Provision Guest VMs

```bash
make provision-guests
```

This creates all guest VMs defined in your inventory via the Proxmox API.

**Verify:**

```bash
make verify-bootstrap-guests
```

Expected output: All guests show `REACHABLE` with their OS version.

### Step 8: Full Platform Convergence

```bash
make converge-site
```

This is the big one. It deploys all services across all VMs:
PostgreSQL, Keycloak (SSO), OpenBao (secrets), Nginx (edge proxy),
Grafana (monitoring), and all application services.

For a faster first pass, converge only the critical path:

```bash
make bootstrap-minimal
```

**Verify:**

```bash
make verify-platform
```

### Step 9: Post-Bootstrap

1. **DNS:** Create A records pointing `*.yourdomain.com` to your server's public IP
2. **TLS:** Certificates are managed by step-ca; verify with `make validate-certificates`
3. **SSO:** Log into Keycloak at `https://auth.yourdomain.com` and create operator accounts
4. **Monitoring:** Access Grafana at `https://grafana.yourdomain.com`

---

## Troubleshooting

### "Permission denied (publickey)"

The bootstrap SSH key isn't on the target host. Run:

```bash
ssh-copy-id -i .local/ssh/bootstrap.id_ed25519.pub root@<SERVER_IP>
```

### ".local/ directory already exists"

Use `make init-local FORCE=true` to create missing files without overwriting existing ones.

### "Preflight .env scanner fails"

Some `.local/` files trip the preflight scanner. Temporarily rename them:

```bash
mv .local/open-webui/provider.env .local/open-webui/provider.env.bak
mv .local/serverclaw/provider.env .local/serverclaw/provider.env.bak
# Run your make target
# Then restore:
mv .local/open-webui/provider.env.bak .local/open-webui/provider.env
mv .local/serverclaw/provider.env.bak .local/serverclaw/provider.env
```

### Guest VM not reachable

1. Verify the VM is running: `ssh ops@<PROXMOX_IP> 'qm list'`
2. Check the VM's IP matches inventory: `ssh ops@<PROXMOX_IP> 'qm guest cmd <VMID> network-get-interfaces'`
3. Check firewall rules aren't blocking the bridge network

### Convergence fails mid-run

Ansible is idempotent. Simply re-run the failed target:

```bash
make converge-site  # Safe to re-run
```

For a specific service:

```bash
make converge-<service-name>
```
