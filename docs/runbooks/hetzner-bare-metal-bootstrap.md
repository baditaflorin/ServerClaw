# Runbook: Hetzner Bare-Metal Bootstrap for a Fork Clone

Target audience: an agent or operator standing up a new Hetzner dedicated
server as a fork-clone of this platform. Companion to ADR 0424.

**Base OS assumption**: Debian 13 (trixie). If Hetzner provisions a different
base OS, stop and update this runbook — do not guess.

---

## 0. Prerequisites (on workstation, before touching the box)

- The SSH private key matching the public key Hetzner has on file, at
  `.local/ssh/hetzner_llm_agents_ed25519` (key comment
  `llm-agents@platform_server`).
- Hetzner DNS API token stored at `.local/hetzner/dns.env`:
  ```
  HETZNER_DNS_TOKEN=<token>
  HETZNER_DNS_ZONE=<zone, e.g. example.org>
  ```
- The server's public IPv4, IPv6, and host-key fingerprint from the
  provisioning email.

### Verify, don't trust

```bash
# 1. Private key fingerprint matches the provisioning email's MD5
ssh-keygen -E md5 -lf .local/ssh/hetzner_llm_agents_ed25519

# 2. Host key fingerprint matches (mitigates MITM on first connect)
ssh-keyscan -t ed25519 -T 10 <IPv4> | ssh-keygen -lf -

# 3. DNS token actually works against the target zone
curl -s -H "Auth-API-Token: $(grep HETZNER_DNS_TOKEN .local/hetzner/dns.env | cut -d= -f2)" \
  https://dns.hetzner.com/api/v1/zones | python3 -c \
  "import json,sys; [print(z['name'], z['id']) for z in json.load(sys.stdin)['zones']]"
```

All three must pass. **If any do not, stop and escalate.**

---

## 1. Pin host key and probe system inventory

```bash
ssh-keyscan -t ed25519 -T 10 <IPv4> >> ~/.ssh/known_hosts
ssh -i .local/ssh/hetzner_llm_agents_ed25519 root@<IPv4> \
  'hostname; cat /etc/os-release | head -3; free -h | head -2; lsblk -d; ls /dev/kvm'
```

Record the output in the workstream YAML for this clone. If `/dev/kvm` is
missing on a nested-Proxmox target, stop — virt extensions are not enabled
(Hetzner AX41 has SVM by default; this should never fail, but verify).

---

## 2. Rename host

```bash
ssh ... root@<IPv4> 'hostnamectl set-hostname <new-hostname>'
```

Proposed convention: `debian-base-template` for the first clone, increment for
subsequent. Update `/etc/hosts` accordingly (the Ansible role
`base_host_identity` handles this once Ansible is able to reach the box).

---

## 3. Disk layout — Hetzner default is ALREADY RAID1 (surprise)

**Critical**: Hetzner's default Debian 13 installimage builds `SWRAID 1`
across both NVMes without asking. The default layout is:

- `md0` (swap) mirrors `nvme0n1p1` ↔ `nvme1n1p1`
- `md1` (`/boot`) mirrors `nvme0n1p2` ↔ `nvme1n1p2`
- `md2` (`/`) mirrors `nvme0n1p3` ↔ `nvme1n1p3`

This means "skip RAID" is **not achievable post-provisioning** without a
rescue-mode reinstall. The only true no-RAID path is to boot the new server
into rescue mode, run `installimage` with `SWRAID 0`, and let it rewrite
the OS.

### Mandatory first check (before any partitioning!)

```bash
ssh root@<IPv4> 'lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS; echo; cat /proc/mdstat'
```

**Do NOT run `lsblk -d`** — the `-d` flag hides partitions and RAID members,
which on 2026-04-21 led an agent to conclude a mirror leg was "raw" and
attempt to repartition it. Recovery was possible only because
`partprobe` was not installed. See the ADR 0425 live postmortem for full
sequence.

### Consequence for this runbook

Accept the RAID1 the box came with. Do not attempt to reclaim either NVMe
as separate storage. PVE's default `local` directory storage at
`/var/lib/vz` uses `md2` and has ~443 GiB available — plenty for the
collapsed-topology VM plan.

If a fork operator genuinely needs no-RAID (e.g. to maximize usable space),
that is a pre-provisioning decision: order the server with rescue-mode access,
run `installimage SWRAID 0` manually before even booting into the installed
system.

---

## 4. Mesh VPN — Headscale, not external Tailscale

This platform runs its own Headscale instance as a platform service (see
prod `headscale.example.com`; clone target `headscale.example.org`). There is no
external Tailscale preauth key.

During bootstrap, operate over **public-IP SSH**. Once the clone's
Headscale service is deployed (part of the platform converge, after the
runtime-control VM is up), register the bare-metal host and the operator
workstation as Headscale clients using preauth keys issued by the clone's
own Headscale admin.

```bash
# LATER — after Headscale is deployed on the clone
# 1. On the Headscale server (inside a VM):
headscale preauthkeys create --user <operator> --reusable=false --expiration 1h

# 2. On the bare-metal host:
curl -fsSL https://tailscale.com/install.sh | sh   # tailscaled client works with headscale
tailscale up --login-server=https://headscale.example.org --authkey=<key> \
  --hostname=debian-base-template --ssh
```

Until that point, all SSH uses the public IP. This is fine for bootstrap;
the public IP is already firewalled by Hetzner's inbound ruleset and the
SSH key is ed25519-only.

---

## 5. Proxmox VE install (Proxmox-on-Debian, no rescue mode)

The existing [docs/runbooks/install-proxmox.md](install-proxmox.md) already
targets Debian 13 + PVE 9.1 and is a verified working path (last observed
2026-03-21 producing PVE 9.1.0 on kernel 6.17.13-2-pve). Run it against the
new box's inventory entry.

Manual fallback (the exact commands the playbook runs; useful if you're
driving by SSH rather than Ansible):

```bash
ssh root@<IPv4> <<'PVE'
# 1. Hostname + /etc/hosts (PVE refuses to install without FQDN resolving)
hostnamectl set-hostname <fork-pve-hostname>
sed -i '/^127\.0\.1\.1/d' /etc/hosts
echo "<ipv4> <hostname>.<domain> <hostname>" >> /etc/hosts

# 2. PVE repo + GPG key (trixie repo shipped 2026-04-20)
wget -qO /etc/apt/trusted.gpg.d/proxmox-release-trixie.gpg \
  https://enterprise.proxmox.com/debian/proxmox-release-trixie.gpg
echo "deb http://download.proxmox.com/debian/pve trixie pve-no-subscription" \
  > /etc/apt/sources.list.d/pve-install-repo.list

# 3. Install PVE kernel
apt update
DEBIAN_FRONTEND=noninteractive apt install -y proxmox-default-kernel

# 4. Reboot into PVE kernel — RISK MOMENT
#    If the box doesn't come back, use Hetzner Robot KVM to select the
#    Debian kernel in grub (it's still installed as fallback).
reboot

# --- after reboot, re-SSH ---
# 5. Install proxmox-ve userland
DEBIAN_FRONTEND=noninteractive apt install -y proxmox-ve postfix open-iscsi chrony
apt remove -y linux-image-amd64 os-prober
pveversion
PVE
```

The `reboot` between steps 3 and 5 is the single riskiest moment of the
bootstrap. Before running it: verify `grep vmlinuz-.*-pve /boot/grub/grub.cfg`
shows the PVE kernel is present and listed first, and verify Hetzner Robot
access is working (you will need it if the reboot fails).

---

## 6. Identity overlay and first Ansible touch

On the workstation:

```bash
# 1. Create the overlay (do NOT commit)
cat > .local/identity.yml.<forkname> <<'YAML'
platform_domain: <fork-subdomain-or-apex>
platform_operator_email: operator@<fork-subdomain>
platform_operator_name: "<fork operator>"
hetzner_dns_zone_name: <actual-zone-at-hetzner>
management_ipv4: <new-ipv4>
management_gateway4: <new-ipv4-gateway>
management_ipv6: <new-ipv6>
management_interface: <iface-from-ip-brief-addr>
host_public_hostname: <new-hostname>
proxmox_node_name: <new-hostname>
YAML

# 2. Select it at runtime
export PLATFORM_IDENTITY_OVERLAY=.local/identity.yml.<forkname>

# 3. Smoke-test Ansible connectivity
ansible -i inventory/hosts.yml <new-hostname> -m ping
```

---

## 7. rDNS (manual — no API)

Hetzner's **legacy** Robot API does not expose PTR record management for
dedicated servers. This must be done via the Robot UI:

1. Log into the Hetzner Robot (robot.hetzner.com).
2. Navigate to the server, "IPs" tab.
3. Set reverse DNS on the main IPv4 to `mail.<platform_domain>`.
4. Do the same for the primary IPv6.

Without this, outbound mail from the clone's Stalwart instance will be
rejected by most major mail providers (especially Gmail and Outlook).

---

## 8. Gate before continuing

Before running **any** `make converge-*` against the new box, verify:

- [ ] Tailscale-assigned IP resolves for the new hostname
- [ ] `ansible -m ping` succeeds from the workstation
- [ ] `.local/identity.yml.<forkname>` exists and is selected via env var
- [ ] `.local/hetzner/dns.env` token verified working against target zone
- [ ] rDNS set (if mail will be deployed)
- [ ] RAID1 built (if stateful VMs will live on this host)
- [ ] Operator has confirmed: subdomain vs apex, hostname, RAID decision

Any missing gate → stop, escalate to operator, do **not** proceed with
converges. The pattern "I'll just try it and see what breaks" is how `.local/`
got clobbered in ADR 0376.

---

## 9. First converge order (after all gates pass)

1. `make converge-proxmox-host env=clone`  — base PVE config
2. `make converge-proxmox-guests env=clone`  — create the 8 collapsed-topology VMs
3. `make converge-runtime-control env=clone`  — Authentik, step-ca, OpenBao (identity anchor)
4. `make converge-postgres env=clone`  — shared DB
5. `make converge-mail-platform env=clone`  — Stalwart + Brevo bridge
6. `make converge-runtime-apps env=clone`  — application services
7. `make converge-monitoring env=clone`
8. `make converge-nginx-edge env=clone`  — last, once upstream services exist

Do **not** attempt step 9 (public DNS record publication) until nginx-edge
is healthy and presenting valid certs via step-ca.

---

## 10. Final validation before declaring the clone live

```bash
# Subdomain DNS resolves to the new server
dig +short A sso.<platform_domain>     # should be <new-ipv4>
dig +short AAAA sso.<platform_domain>  # should be <new-ipv6>

# Authentik readiness is reachable and signed by the shared edge certificate
curl -sS https://sso.<platform_domain>/realms/<realm>/.well-known/openid-configuration | jq .issuer

# Mail loop works: send a test message from the new operator address to a
# monitored external mailbox and verify SPF+DKIM+DMARC all pass in the headers.
```

If mail to external recipients lands in spam, check (in order):
1. rDNS set
2. SPF record includes Brevo's sending hosts
3. DKIM selector published on `clone.<domain>`
4. DMARC record present and aligned

These checks are implicit in the Stalwart role; the runbook lists them
here because every fork will get bit by at least one of them.

---

## 11. Live-apply notes from the example.org clone (2026-04-21)

The 0fork clone was bootstrapped without running the `env=clone` Ansible
targets (they don't exist yet in the Makefile/inventory). What *did* work,
captured here so the next fork can copy it verbatim:

### 11a. Internal-only bridge (zero-WAN-risk alternative to `vmbr0` swap)

Instead of converting `enp41s0` → `vmbr0` (the lockout-risk step), add a
private bridge + NAT masquerade as an **additive** change. WAN is untouched:

```bash
# /etc/network/interfaces.d/vmbr10.cfg
cat > /etc/network/interfaces.d/vmbr10.cfg <<'EOF'
auto vmbr10
iface vmbr10 inet static
    address 10.10.10.1/24
    bridge-ports none
    bridge-stp off
    bridge-fd 0
    post-up   sysctl -w net.ipv4.ip_forward=1
    post-up   iptables -t nat -C POSTROUTING -s 10.10.10.0/24 -o enp41s0 -j MASQUERADE 2>/dev/null \
              || iptables -t nat -A POSTROUTING -s 10.10.10.0/24 -o enp41s0 -j MASQUERADE
    post-down iptables -t nat -D POSTROUTING -s 10.10.10.0/24 -o enp41s0 -j MASQUERADE || true
EOF
# Persist ip_forward across reboots
printf 'net.ipv4.ip_forward = 1\nnet.ipv4.conf.all.forwarding = 1\n' > /etc/sysctl.d/99-proxmox-forward.conf
sysctl -p /etc/sysctl.d/99-proxmox-forward.conf

# Save NAT rule persistently (post-up re-adds on boot; this is belt-and-braces)
apt-get install -y iptables-persistent
# Bring ONLY vmbr10 up (does not touch enp41s0)
ifup vmbr10
netfilter-persistent save
```

Consequences: VMs get outbound internet via NAT. **Public inbound requires
explicit DNAT** (iptables) OR nginx-edge-on-host OR the full `vmbr0` swap.
For a fork that just needs internal services + operator-reachable SSH via
Headscale mesh, NAT-only is sufficient indefinitely.

### 11b. Cloud-init template (vmid 9000)

libguestfs-tools **cannot** be installed on a PVE host (it conflicts with
the `proxmox-ve` meta-package via the `pve-apt-hook`). Do not attempt
`virt-customize`. Inject everything via cloud-init user-data at first boot:

```bash
# Download upstream Debian 13 cloud image (no customization)
mkdir -p /var/lib/vz/template/qcow
curl -fsSL -o /var/lib/vz/template/qcow/debian-13-genericcloud-amd64.qcow2 \
  https://cloud.debian.org/images/cloud/trixie/latest/debian-13-genericcloud-amd64.qcow2

# Generate a fork-host bootstrap key (used for host→VM SSH)
ssh-keygen -t ed25519 -f /root/.ssh/id_ed25519 -N "" -C "debian-base-template-bootstrap"

# Write template user-data that installs qemu-guest-agent on first boot +
# pins the operator's external SSH pubkeys and the fork-host pubkey
cat > /var/lib/vz/snippets/template-user-data.yml <<EOF
#cloud-config
hostname: debian13-cloud-template
package_update: true
packages: [qemu-guest-agent, python3, sudo, curl, ca-certificates]
runcmd: [systemctl enable --now qemu-guest-agent]
users:
  - name: root
    ssh_authorized_keys:
      - <operator workstation pubkey>
      - <bootstrap pubkey>
      - $(cat /root/.ssh/id_ed25519.pub)
    lock_passwd: true
ssh_pwauth: false
EOF

# Build the template
qm create 9000 --name debian13-cloud-template \
  --memory 1024 --cores 1 --cpu host \
  --net0 virtio,bridge=vmbr10 --ostype l26 \
  --agent enabled=1,fstrim_cloned_disks=1 \
  --scsihw virtio-scsi-pci --serial0 socket --vga serial0
qm importdisk 9000 /var/lib/vz/template/qcow/debian-13-genericcloud-amd64.qcow2 local --format qcow2
qm set 9000 --scsi0 local:9000/vm-9000-disk-0.qcow2 --boot order=scsi0
qm set 9000 --ide2 local:cloudinit
qm set 9000 --cicustom "user=local:snippets/template-user-data.yml"
qm template 9000
```

### 11c. Clone-and-configure per-VM (inline loop, no Packer)

Collapsed topology provisioned via a simple shell loop that clones VMID
9000, resizes disk, sets cores/memory, attaches per-VM cloud-init snippet,
and starts the VM. See ADR 0424 for the 8-VM plan. Typical runtime: ~45
seconds total for all 8 VMs on the AX41-NVMe.

### 11d. What didn't work and remains pending operator

- **Direct SMTP to Gmail rejected (550-5.7.1 / 550-5.7.26)** — no PTR on
  either the IPv4 or IPv6 address, and no SPF/DKIM for `example.org`. Both
  IPv6 and IPv4 paths reject. Operator must set rDNS via Hetzner Robot UI,
  then publish SPF/DKIM records, then mail-platform converge becomes viable.
- **Hetzner DNS API brownout** — on 2026-04-21 the write API returned HTTP
  200 with empty record fields and an embedded `503 Temporary Shutdown`
  error. Read API worked fine. Scheduled full shutdown: 2026-05-20. Any
  fork between now and then needs a retry loop on writes and must verify
  the record exists after create.
- **WAN bridge (`vmbr0`) swap** — deferred. The internal-only bridge in
  §11a covers all bootstrap needs. The swap should happen during a window
  where the operator has Hetzner Robot KVM access to recover from a bad
  ifreload.

### 11e. Actual provisioning receipt (debian-base-template, 2026-04-21)

| vmid | name            | ipv4         | cores | mem_mb | disk_gb |
|------|-----------------|--------------|-------|--------|---------|
| 110  | nginx-edge      | 10.10.10.11  | 2     | 2048   | 10      |
| 122  | runtime-apps    | 10.10.10.12  | 6     | 12288  | 40      |
| 130  | docker-build    | 10.10.10.14  | 4     | 4096   | 40      |
| 140  | monitoring      | 10.10.10.15  | 2     | 4096   | 30      |
| 150  | postgres        | 10.10.10.13  | 4     | 8192   | 60      |
| 160  | backup          | 10.10.10.16  | 2     | 4096   | 40      |
| 181  | mail-platform   | 10.10.10.17  | 2     | 4096   | 20      |
| 192  | runtime-control | 10.10.10.10  | 6     | 16384  | 60      |
| 9000 | debian13-cloud-template | 10.10.10.254 | 1 | 1024 | 3 (qcow) |

Total allocation: 28 cores (on 12 threads = 2.33× oversub, matches ADR
0424 plan), 54 GiB RAM (+ ~8 GiB for host), 303 GiB disk.

All 8 service VMs are reachable from the fork host at `root@10.10.10.X`
using `/root/.ssh/id_ed25519`. Cloud-init completed cleanly on all of
them (qemu-guest-agent active, python3 present → Ansible-ready).
