# ADR 0490: Netplan MAC Mismatch — Root Cause and Self-Healing Recovery Model

**Status**: ACCEPTED
**Date**: 2026-05-20
**Decision**: When `provision-guests` regenerates cloud-init ISOs with corrected MACs, the running VMs need their `/etc/netplan/50-cloud-init.yaml` patched in-place via `qm guest exec` and `netplan apply`. The cloud-init ISO replacement alone is sufficient for reboot-persistence because the regenerated ISO produces a new instance-id, causing cloud-init to fully re-initialize on the next boot.

---

## Context

### What happened

After the initial bootstrap the `provision-guests` step was re-run (e.g. to regenerate snippets or resize VMs). Proxmox assigns a new `virtio` MAC to each NIC on re-creation, so the cloud-init ISOs were regenerated with the new (correct) MACs. The running VMs, however, still had the old `/etc/netplan/50-cloud-init.yaml` on disk — one written by cloud-init during the original first-boot with the original (stale) MACs.

Because netplan's `match.macaddress` no longer matched the actual NIC, the interface (`ens18` / renamed to `eth0`) would be left DOWN after any reboot or NIC reset, taking the VM off the internal network.

Affected VMs (2026-05-20 incident):

| VMID | Name | Stale MAC | Correct MAC |
|------|------|-----------|-------------|
| 110 | nginx-lv3 | `bc:24:11:91:9c:f4` | `bc:24:11:0d:03:bb` |
| 120 | docker-runtime-lv3 | `bc:24:11:14:f8:6c` | `bc:24:11:aa:99:7c` |
| 140 | monitoring-lv3 | `bc:24:11:4a:ba:fc` | `bc:24:11:b1:76:a0` |
| 150 | postgres-lv3 | `bc:24:11:ab:3d:6b` | `bc:24:11:2a:2e:ca` |

VM 192 (runtime-control-lv3, `bc:24:11:19:0a:92`) was fixed independently before this analysis.

### Why `provision-guests` regeneration alone is not enough

Proxmox's cloud-init ISO is regenerated when you run `qm set --ipconfig0 ...` or when `provision-guests` calls the equivalent API. The VM's OS only reads from this ISO during cloud-init's init phase. Because cloud-init had already completed on the running VM (status: `done`) and the instance-id in the new ISO differs from the cached one in `/var/lib/cloud/data/instance-id`, the new ISO config will be picked up — but only on the next reboot.

The running network stack is not affected by ISO regeneration. The VMs were already up (IPs manually restored via `qm guest exec ip link/addr` commands), but the stale `/etc/netplan/50-cloud-init.yaml` would have broken them again on the next reboot.

### Why the next reboot is now safe

After the fix:

1. `/etc/netplan/50-cloud-init.yaml` on each VM was overwritten with the correct MAC and `netplan apply` was run — the interface is UP and reachable.
2. The cloud-init ISO for each VM contains the correct MAC in `network-config`.
3. The ISO's `instance-id` differs from the cached value in `/var/lib/cloud/data/instance-id` on each VM. Cloud-init treats this as a new instance on next boot, discards cached state, and rewrites the netplan from the ISO — which now has the correct MAC.

There is no window where the VM can reboot into a broken state.

---

## Decision

### Recovery procedure

When VMs have lost network due to a stale netplan MAC (interface is DOWN after reboot), follow these steps from the Proxmox host:

```bash
SSH_KEY=".local/ssh/bootstrap.id_ed25519"
PROXMOX="root@65.108.75.123"

# Step 1 — verify the stale MAC in netplan
# (replace VMID and CORRECT_MAC with values from inventory/host_vars/proxmox-host.yml)
ssh -i $SSH_KEY $PROXMOX \
  "qm guest exec VMID -- /bin/bash -c 'cat /etc/netplan/50-cloud-init.yaml'"

# Step 2 — overwrite netplan with correct MAC
# CORRECT_MAC must be lowercase (bc:24:11:xx:xx:xx)
ssh -i $SSH_KEY $PROXMOX "qm guest exec VMID -- /bin/bash -c '
cat > /etc/netplan/50-cloud-init.yaml <<EOF
network:
  version: 2
  ethernets:
    eth0:
      match:
        macaddress: \"CORRECT_MAC\"
      addresses:
      - \"VM_IP/24\"
      nameservers:
        addresses:
        - 1.1.1.1
        search:
        - 0mpc.com
      set-name: \"eth0\"
      routes:
      - to: \"default\"
        via: \"10.10.10.1\"
EOF
netplan apply'"

# Step 3 — verify interface came up
ssh -i $SSH_KEY $PROXMOX \
  "qm guest exec VMID -- /bin/bash -c 'ip addr show eth0; ip route'"

# Step 4 — confirm the cloud-init ISO also has the correct MAC
# (it should if provision-guests was re-run; if not, run: make provision-guests)
TMPDIR=$(mktemp -d)
ssh -i $SSH_KEY $PROXMOX "
  qemu-nbd -c /dev/nbd1 /var/lib/vz/images/VMID/vm-VMID-cloudinit.qcow2
  sleep 1
  mount /dev/nbd1 $TMPDIR
  grep mac_address $TMPDIR/network-config
  umount $TMPDIR
  qemu-nbd -d /dev/nbd1
"
```

If the ISO still has the wrong MAC, re-run `make provision-guests` before rebooting any VM.

### Invariant going forward

- `inventory/host_vars/proxmox-host.yml` is the single source of truth for `macaddr` values.
- A re-run of `provision-guests` regenerates the cloud-init ISO with whatever MAC is in inventory. If the MAC in inventory is wrong, the ISO will be wrong.
- The MAC in inventory must match the MAC actually assigned by Proxmox (`qm config VMID | grep net0`).
- After any `provision-guests` re-run, verify with: `qm config VMID | grep net0` vs `grep macaddr inventory/host_vars/proxmox-host.yml`.

### Diagnostic quick-reference

```bash
# Check current netplan MAC on a running VM
qm guest exec VMID -- /bin/bash -c 'grep macaddress /etc/netplan/50-cloud-init.yaml'

# Check actual NIC MAC assigned by Proxmox
qm config VMID | grep net0

# Check MAC in cloud-init ISO (requires nbd module)
TMPDIR=$(mktemp -d)
qemu-nbd -c /dev/nbd1 /var/lib/vz/images/VMID/vm-VMID-cloudinit.qcow2
sleep 1; mount /dev/nbd1 $TMPDIR
grep mac_address $TMPDIR/network-config
umount $TMPDIR; qemu-nbd -d /dev/nbd1; rm -rf $TMPDIR

# Check cloud-init instance-id mismatch (triggers full re-init on next boot)
# In ISO:
grep instance-id $TMPDIR/meta-data
# On VM:
qm guest exec VMID -- /bin/bash -c 'cat /var/lib/cloud/data/instance-id'
```

---

## Consequences

- VMs survive reboot without manual intervention after `provision-guests` regenerates their ISOs.
- There is a brief window between a `provision-guests` re-run and the next VM reboot where the running netplan is stale. Apply the in-place fix (Step 2 above) to close this window immediately.
- The `qm guest exec` channel does not depend on the VM's network being up, making it reliable for recovery even when SSH is unreachable.
- The Proxmox firewall drops ICMP from the host to VMs by default; use `nc -w2 IP 22` or `qm guest exec` rather than ping to test reachability.
