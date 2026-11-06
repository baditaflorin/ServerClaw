# pve-0mcp: the stopgap swapfile `/swapfile-0mcp-stopgap` (32 GiB)

2026-11-01. The 0mcp hypervisor (`pve-0mcp`, hostname `debian-base-template`, ssh alias `operator-bastion`) was out of memory headroom with its swap nearly full. The owner approved a stopgap ("Yes, add swapfile") and a 32 GiB swapfile was added by hand at 22:03Z, in
no repository. This directory records it. `install-host.sh` repeats it idempotently, checks it read-only and
removes it; `live-state-20261101.txt` is the read-only capture the numbers below come from. **It is a stopgap, not the fix**: the lasting fix (VM memory sizes that fit the host, or less
overcommit) is the owner's decision and belongs to the docker-prod capacity plan and the memory-budget proposal (PR 653), not here.

## What is live (read-only capture, 2026-11-01 22:08Z to 22:11Z)

| | |
|---|---|
| File | `/swapfile-0mcp-stopgap`, 34,359,738,368 bytes (32 GiB), mode 600 `root:root`, made with `fallocate -l 32G` (329 extents, no holes) |
| Where | `/` = `/dev/md2`, ext4, 1.88 TB, 624 GB free; RAID1 with one member (`nvme1n1p3`), the same NVMe that holds `/boot` and the 4 GiB swap (and, per the memory-budget proposal, the disks of 16 of the 19 VMs) |
| Swap signature | `mkswap -L stopgap`, UUID `c6e053ea-ed3a-4826-b2b7-b8f262f791a1` (the swap area is one page smaller than the file: 34,359,734,272 bytes) |
| Active | `swapon /swapfile-0mcp-stopgap`, no priority given, so priority -1: the same as `/dev/md0` (the 4 GiB partition), and the kernel uses areas of equal priority in turn |
| In `/etc/fstab` | **No.** The only swap line is the `/dev/md0` UUID line. A reboot drops the swapfile (the file stays on disk, it is just not swap any more) |
| Total swap | 37,743,608 kB = 36.0 GiB (4 GiB + 32 GiB); `vm.swappiness` 60, unchanged |
| Undo, by hand | `swapoff /swapfile-0mcp-stopgap && rm /swapfile-0mcp-stopgap` (and the fstab line, if it was persisted) |

## Why

Figures of the 2026-11-01 evening analysis (read-only, by the coordinating session; this change did not measure them again, except the two marked *now*):

| Measured | Value |
|---|---|
| MemAvailable | 8 GiB of 125 GiB, 15.4 GiB twelve hours earlier: about 0.6 GiB lost an hour. *Now (22:10Z): 7,992,408 kB = 7.6 GiB, 6.1 %* |
| Swap before | the 4 GiB `md0` partition, 3.8 GiB used. *Now: 3.7 GiB of it* |
| VM memory | the running VMs are configured for 139 GiB against 125 GiB |
| Ballooning does not hand host memory back | qemu backs guest RAM with transparent huge pages (`AnonHugePages` 82 GiB); held above the balloon size on the morning of 11-01: vm130 9.2, vm122 4.7, vm192 4.1, vm171 2.7, vm170 1.9 GiB |
| Who the kernel would kill first | `oom_score` of the biggest qemu processes: vm120 752, vm191 747, vm150 (`postgres-lv3`) 704, vm192 702 |

The swapfile is insurance so that the kernel can push cold guest pages out instead of OOM-killing a production VM's qemu process. It is **not capacity** and it **gives no memory back**: pages swapped
out of a guest come back slowly (NVMe latency) when that guest touches them, and `MemAvailable` does not count swap. The disk is the one the memory-budget proposal would have avoided (it puts a
12 GiB file on the quiet `nvme0n1`, `/var/lib/vz-nvme1/swap/swapfile`, priority -2; its seven-day numbers: `nvme1n1` busy 26 % at the median, swap I/O at most 2.7 MiB/s out); the stopgap went
on `/` (md2: 624 GB free, no new partition or mount needed). If that proposal's swap step is applied as written the host would have a third swap area (48 GiB):
decide between the two, then `--remove` the one that is not wanted.

## Alerts that motivated it, and what it changes about them

| Alert | Where | Fires when |
|---|---|---|
| `FleetHypervisorMemAvailableLow` | `config/prometheus/rules/fleet-hypervisor-memory.yml` | warning, MemAvailable under 5 % for 10 minutes |
| `FleetHypervisorMemAvailableCritical` | same file | critical, under 3 % for 5 minutes |
| `FleetHypervisorSwapExhausted` | same file | warning, under 10 % of swap free for 15 minutes |
| `ProxmoxHostMemoryExhausted` | go-fleet-metrics-hub, `prometheus/rules/proxmox-capacity-alerts.yml` | critical, under 5 % available for 5 minutes |
| `ProxmoxHostMemoryHeadroomLow` | same file | warning, under 15 % available for 10 minutes |

The memory alerts read `MemAvailable`, which does not include swap, so none of them goes quiet because of the swapfile: they still say when the host is short. `FleetHypervisorSwapExhausted` is the
exception: its denominator grew from 4 to 36 GiB, so it now needs 32.4 GiB swapped out, and the `md0` partition filling (the 2026-11-01 symptom) no longer fires it. That is a side effect of
this change, recorded here; whether it needs a replacement is the owner's decision (no alert rule is changed by this PR).

## Install, check, undo

`install-host.sh` runs as root on the hypervisor and is streamed through ssh, so nothing is written there to run it. **This change made no change on the host.** The capture was plain reads, and
the one verb of the installer that was run there is the read-only `check` (once, 2026-11-01 22:27Z, to test the script against the real tools; its output is the last block of `live-state-20261101.txt`).

```sh
ssh operator-bastion 'bash -s -- check'     < config/0mcp/hypervisor-swap/install-host.sh   # read-only, the default
ssh operator-bastion 'bash -s -- --apply'   < config/0mcp/hypervisor-swap/install-host.sh   # the file and swapon: what was done by hand; a reboot drops it
ssh operator-bastion 'bash -s -- --persist' < config/0mcp/hypervisor-swap/install-host.sh   # --apply, plus the fstab line; needs the owner's yes
ssh operator-bastion 'bash -s -- --remove'  < config/0mcp/hypervisor-swap/install-host.sh   # swapoff, the fstab line and the file go
```

| Exit | Meaning |
|---|---|
| 0 | `check`: file, swap area and fstab line are all as wanted. The other verbs: done (or nothing to do) |
| 1 | refused or invalid (not this host, not root, a guard below, wrong arguments) |
| 2 | `check`: usable now, **not persisted** (no fstab line). This is the state on the live host today |
| 3 | `check`: not as wanted (file missing or wrong, not swap) |

What it does, and what it refuses:

1. **Recognises the live file** (path, size 34,359,738,368 bytes, mode 600, `root:root`, swap signature with the label `stopgap`) and adds only what is missing: nothing to create, `swapon` only if the
   area is not active (after a reboot: `--apply`), the fstab line only with `--persist`. A run with nothing to do changes nothing and makes no backup.
2. **Creates the file only when it is missing**, on ext4 only (a swapfile with holes or copy-on-write is unsafe elsewhere) and only when `/` keeps **at least 200 GB free after the 32 GiB file**
   (it needs 234 GB free before). The file is made under a temporary name with `umask 077`, `chmod 600` and `mkswap -L stopgap`, then renamed into place.
3. **Never touches a file that is not ours**: another size, another signature or label, a symlink, not a regular file are refused (a file of the right size with no signature, left by a run that
   was cut off, is completed). The one other safe completion is the mode: a swap file with the right label and size at another mode is set to 600.
4. **`--persist`** adds `/swapfile-0mcp-stopgap none swap sw,nofail 0 0` (`nofail`: a missing file does not make the swap unit a hard dependency of the boot; no priority, as live). `/etc/fstab` is rewritten only after the
   candidate was read back with `findmnt --tab-file`; the old file is kept as `/etc/fstab.bak-swap-<UTC time>`; `systemctl daemon-reload` runs after the change (it reloads unit files, the swap
   area stays as it is: systemd already has a `swapfile\x2d0mcp\x2dstopgap.swap` unit for it); `findmnt --fstab` reads the result back and the backup is put back if it does not match.
5. **`--remove`** does `swapoff` of this one file (never `swapoff -a`, never `/dev/md0`), drops its fstab line, deletes the file. It refuses while more is swapped out than **half of MemAvailable**
   (`swapoff` has to move every page back into RAM first; with 7.6 GiB available that is 3.8 GiB, so check `swapon --show` and wait or free memory). Nothing is changed when it refuses.
6. **Refuses any other machine**: root, hostname `debian-base-template` and `/etc/pve/nodes/<hostname>`.

On the live host `check` printed `file ok`, `active ok` (0 MiB used) and `fstab absent`, and exited 2. `--persist` would then change only `/etc/fstab` (a line, a backup) and reload the units, and `check` would exit 0.

## When to remove it (proposed; the owner decides)

- **It is replaced.** The swap step of the memory-budget proposal (a file on `nvme0n1`) is applied: install the replacement first, then `--remove` this one.
- **The lasting fix has landed** (guaranteed VM memory within the budget the owner sets) and for 30 days `ProxmoxHostMemoryHeadroomLow` has not fired: `--remove` (it refuses by itself while too
  much is swapped out; `used` in `check` is the number to watch).
- **The root filesystem is short of space**: under 200 GB free on `/` (the creation guard's figure). Remove or shrink it before the disk fills; the 32 GiB are already allocated, so it does not grow.

## Why not hostconf

`config/hostconf` writes sysctl files, systemd drop-ins and Postgres `conf.d` files only (`KIND_PATTERNS` in `scripts/hostconf.py`); it has no swap or `/etc/fstab` kind, and the 16 GiB swapfile of
VM701 is in the same position. The install-script pattern of `config/0mcp` and `config/0infer` (README, idempotent installer, capture, test) is the platform's existing answer for a
single host-local change of another kind. `tests/test_hypervisor_swap.py` fails if hostconf ever gets such a kind, as a reminder to move this there.

## Not here, on purpose

- Persisting the swapfile on the host: `install-host.sh --persist` needs the owner's yes.
- The lasting fix, a change of `vm.swappiness` (60 stays), zram or zswap (they spend RAM the host does not have), KSM, and any alert rule.

The test is `tests/test_hypervisor_swap.py`: the installer against a fake host (every verb, every guard), the README and the installer agree, and a mutation sweep that breaks each guard to prove it is tested.
