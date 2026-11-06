# pve-0mcp memory budget (proposal; stage 1 partly applied on 2026-11-02, see section 11)

Status: **proposal for review**, written 2026-11-01 (workstream `ws-20261101-pve-0mcp-memory-budget`, ADR 0494 for the placement rule). Every command run against a host for this document was read-only: no `qm set`, no restart, no swap, KSM or sysfs change, no package. Applying any step below needs the owner's yes.

**Update 2026-11-03:** after review, stage 1 was taken in part, and three more VMs were given fixed sizes when the host fell under 5 percent available again. Sections 1 to 10 keep the measurements of 2026-11-01 as they were; **section 11 says what was applied and what the numbers are now.**

`pve-0mcp` (ssh alias `operator-bastion`) runs the fleet's 0mcp services as 19 VMs. On 2026-11-01 it fell to 3.9 percent available memory with its 4 GiB of swap full; restarting VM 130 at a fixed 14,336 MiB ended it (08:48 to 08:49Z). This page says what the host promises its guests, what they really use, what can move, and in which order.

## 1. Summary

1. **The floors are the real sizes.** The 19 running VMs have maximums of 142,336 MiB (139.0 GiB, 110.6 percent of the host's 128,716 MiB) but are *guaranteed* 103,168 MiB (100.75 GiB, **80.15 percent**): the balloon floors of 16 VMs plus the whole memory of the 3 VMs with `balloon: 0`. `pvestatd` shrinks ballooned guests while the host is above its ballooning target (**85 percent used on this node**; the node config was last changed on 2026-09-29; not in git; the default is 80), and the host is at 89.3 percent. All 16 ballooned guests sit exactly at their floors (section 3).
2. **The seven-day numbers do not support lowering the floors of VM 191 or VM 120.** VM 191 used 12.4 GiB at the 95th percentile and 13.4 GiB at its one-minute maximum (floor 16.0 GiB). VM 120 used 15.6 GiB at its maximum against 15.9 GiB visible at its floor, had 23 guest OOM kills on 10-25 to 10-28 while pinned there with its swap full, and needs *more*. Proposal: VM 191 unchanged, **VM 120 floor 16,384 to 18,432** (section 6).
3. **Most of the host's pressure is memory the guests do not own.** The VMs hold 8.5 GiB (6.7 percent of RAM) more than their guaranteed sizes, 10.3 GiB gross in four VMs (122, 171, 155, 192), 70 percent of the host's anonymous memory is in huge pages, and at the 11-01 peak the host held 21 to 23 GiB more than the guests could see. Lowering floors does not touch that. A cause is not proven (section 4).
4. **Host swap: add a 12 GiB swap file on the quiet NVMe (16 GiB in all), as insurance, not capacity.** **KSM: not now.** Fixed VMs: **VM 130 and VM 180 stay fixed; VM 200 (staging) gets a floor of 2,560 at its next restart.**
5. **Budget rule:** floors plus fixed VMs at most **75 percent** of RAM by design, an alarm above **80**, no net increase without an offsetting cut. It was 80.15 on 2026-11-01 (82.14 after the changes of section 11). The alert `ProxmoxHostGuaranteedMemoryOverBudget` (same PR, not shipped) fires on it.
6. **One decision for the owner:** approve stage 1 of the apply plan (section 7): the swap file, VM 120 up by 2,048 MiB, VM 154 down by 2,048 MiB (a trial). The budget stays 80.15 percent; the host gets a 12 GiB safety valve and the one guest with a measured OOM history gets its memory.

## 2. Where memory is defined and how a change reaches the host

| What | Where it is defined | How a change reaches the host | In git? |
|---|---|---|---|
| Maximum memory (`memory`), cores, disk of a declared guest | `inventory/host_vars/proxmox-host.yml`, `proxmox_guests[].memory_mb` | role `proxmox_guests` (`make provision-guests`) runs `qm set <id> --cores --memory --balloon 0` on **every** declared guest | yes, but it disagrees with the live VMs for six guests (below) |
| Balloon floor (`balloon`) | nowhere in the inventory; the role forces `--balloon 0` | by hand: `qm set <id> --balloon <MiB>` (live when the VM already has a balloon device); recorded in `config/0mcp/<vm>/README.md` (VM 171 floor 3,072, VM 130 history) and `playbooks/agent-history-vm.yml` (VM 155 floor 6,144) | **no** |
| Live balloon target | `pvestatd` (`/usr/share/perl5/PVE/Service/pvestatd.pm`, `PVE/AutoBalloon.pm` on pve-manager 9.2.21), every 10 s | host used = MemTotal minus MemAvailable; goal = `ballooning-target` percent of MemTotal minus used; goal above +10 MiB grows guests (those short of free memory first), below -10 MiB shrinks them (those with free memory first), never under a VM's `balloon`, at most 100 MiB per VM per cycle; VMs with `balloon: 0` or `shares: 0` are skipped | n/a |
| `ballooning-target` | `/etc/pve/nodes/<node>/config`, value 85 (file last changed 2026-09-29) | `pvesh set /nodes/<node>/config --ballooning-target N` | **no** |
| Host swap | `/etc/fstab`: one 4 GiB partition (`/dev/md0`) | by hand | no (`hostconf` manages sysctl files and systemd drop-ins, not swap) |
| KSM, THP | `/sys/kernel/mm/ksm/run`, `/sys/kernel/mm/transparent_hugepage/*` (KSM off, no `ksmtuned` package; THP `madvise`, `khugepaged` `max_ptes_none` 511) | by hand | no |
| Reclaim of deferred-split huge pages | role `fleet_hypervisor_memory_reclaim` (timer on `operator-bastion`, acts below 10 percent available) | Ansible, installed | yes |
| Alerts | `config/prometheus/rules/fleet-hypervisor-memory.yml` (below 5 and 3 percent available, swap over 90 percent), the hub's `ProxmoxHostMemoryHeadroomLow` (below 15 percent) and `ProxmoxVMBallooningUnavailable`, and, in this PR, `proxmox-host-memory-budget.yml` | monitoring role copy plus a Prometheus reload (a separate approved step) | yes |
| Capacity model | `config/capacity-model.json`: `host.target_utilisation.ram_percent` 80, `reserved_for_platform.ram_gb` 8, `runtime_pool_memory.host_free_memory_floor_gb` 20; read by `scripts/capacity_report.py` | git only | yes, **stale** (no VM 100 or 200, VMs 151/152/154/155 still `planned`, VMs 121, 140, 151, 152, 190, 191 with other sizes) |

**Traps.**

- *Git says 166 GiB, the host runs 139.* The inventory declares 169,984 MiB for 18 guests. It disagrees with `qm config` for VM 121 (git 8,192, live 4,096), VM 140 (8,192, 4,096), VM 151 and VM 152 (8,192, 2,048), VM 190 (16,384, 3,072) and VM 191 (12,288, 16,384); VM 160 (`backup`, 8,192) is declared and does not run; VM 100 and VM 200 are not declared. An unscoped `make provision-guests` would resize those VMs, clone VM 160, and remove every balloon floor (`--balloon 0` on all). Never run it for the whole set (the Makefile warns for VM 155 only). VM 130 was corrected by PR 651.
- *Raising a floor does not give the guest the memory at once.* `pvestatd` grows guests only while the host is below its target. A raise on a running VM needs the QMP command as well: `echo "balloon <MiB>" | qm monitor <id>` (the VM 130 README uses it).
- *The role forces `balloon 0`,* which is why floors live only on the host and in READMEs. A per-guest `balloon_mb` in the inventory and role would put them in git (follow-up, not here).

## 3. What was measured (2026-11-01, read-only)

Host `pve-0mcp` at 13:30Z: Debian trixie, PVE 9.2.21, kernel 7.0.2-4-pve, AMD Ryzen 9 3900 (24 threads, one NUMA node), up 166 days.

| | Value |
|---|---|
| RAM | 128,716 MiB (125.7 GiB) |
| Available / used | 13,793 MiB (10.7 percent) / 114,923 MiB (89.3 percent) |
| Swap | 4,090 MiB, 3,864 MiB used (94.5 percent); `vm.swappiness` 60 |
| Anonymous memory | 109.2 GiB, of which 76.3 GiB (69.9 percent) in huge pages; page cache 3 GiB |
| Deferred-split gap (the part the reclaim timer handles) | 215 MiB, so it is not what holds the memory |
| Memory pressure (PSI) | 0.00 some and full at 10 s, 60 s and 300 s; 9 kernel OOM kills since boot (the kernel journal shows none) |
| Committed address space | 161 GiB (`Committed_AS`) |

Seven days of the host (hourly samples): available memory was **below 15 percent in 145 of 169 hours**, below 10 percent in 44, below 5 percent in 2 (minimum 4.0 percent at 11-01 08:00Z). Swap used peaked at 3.99 GiB. Swap traffic was small: swap-out 95th percentile 3 pages/s (maximum 699, 2.7 MiB/s), swap-in 9 (maximum 91). The guaranteed footprint, computed from the `fleet_proxmox_guest_*` series, moved between 73.8 and 83.3 percent and is 80.15 now.

### The budget table (MiB)

`In git` is `memory_mb` in the inventory. `Floor` is the balloon floor, `Fixed` the whole memory of a VM with `balloon: 0`, `Guaranteed` is whichever of the two applies. `Host RSS now` is `VmRSS` of the VM's QEMU process at 13:31Z.

| VM | Name | In git | Maximum | Floor | Fixed | Guaranteed | Host RSS now |
|---|---|---|---|---|---|---|---|
| 100 | hermes-agent | - | 6,144 | 4,096 | - | 4,096 | 4,073 |
| 110 | nginx-lv3 | 4,096 | 4,096 | 2,048 | - | 2,048 | 1,959 |
| 120 | docker-runtime-lv3 | 18,432 | 18,432 | 16,384 | - | 16,384 | 16,375 |
| 121 | runtime-comms-lv3 | 8,192 | 4,096 | 2,048 | - | 2,048 | 1,941 |
| 122 | runtime-apps-lv3 | 8,192 | 8,192 | 1,536 | - | 1,536 | 6,308 |
| 130 | docker-build-lv3 | 14,336 | 14,336 | - | 14,336 | 14,336 | 14,379 |
| 140 | monitoring-lv3 | 8,192 | 4,096 | 3,072 | - | 3,072 | 3,056 |
| 150 | postgres-lv3 | 8,192 | 8,192 | 6,144 | - | 6,144 | 5,992 |
| 151 | postgres-replica-lv3 | 8,192 | 2,048 | 1,024 | - | 1,024 | 969 |
| 152 | postgres-apps-lv3 | 8,192 | 2,048 | 1,024 | - | 1,024 | 1,012 |
| 154 | postgres-data-lv3 | 8,192 | 8,192 | 6,144 | - | 6,144 | 6,031 |
| 155 | agent-history | 8,192 | 8,192 | 6,144 | - | 6,144 | 8,144 |
| 170 | coolify-lv3 | 6,144 | 6,144 | 4,096 | - | 4,096 | 4,039 |
| 171 | coolify-apps-lv3 | 8,192 | 8,192 | 3,072 | - | 3,072 | 5,609 |
| 180 | artifact-cache-lv3 | 4,096 | 4,096 | - | 4,096 | 4,096 | 3,585 |
| 190 | runtime-ai-lv3 | 16,384 | 3,072 | 1,280 | - | 1,280 | 1,266 |
| 191 | runtime-general-lv3 | 12,288 | 16,384 | 16,384 | - | 16,384 | 15,627 |
| 192 | runtime-control-lv3 | 12,288 | 12,288 | 6,144 | - | 6,144 | 7,425 |
| 200 | 0mcp-staging-runtime | - | 4,096 | - | 4,096 | 4,096 | 4,051 |

Totals: maximum **142,336** (110.6 percent of RAM); floors 80,640 (16 VMs); fixed 22,528 (VMs 130, 180, 200); guaranteed **103,168 (80.15 percent)**; host RSS 111,841 (86.9 percent). The template VM 9000 is stopped and not counted.

Reading it:

- Every ballooned VM's current balloon equals its floor (`qm status <id> --verbose`, `ballooninfo.actual`), 16 of 16.
- Used (89.3 percent) = guaranteed 80.15 + the VMs' RSS above their guarantee 6.7 (8,673 MiB net; 10,633 MiB gross: VM 122 +4,772, VM 171 +2,537, VM 155 +2,000, VM 192 +1,281, VM 130 +43) + the host itself 2.4 (3,082 MiB: kernel, slab 1.1 GiB, page tables 0.3 GiB, daemons).
- The 85 percent target leaves 85 - 80.15 - 2.4 = 2.5 percent (3.1 GiB) for anything the guests hold above their floors; they hold 8.5 GiB, so `pvestatd` has been asking for a shrink of about 5.4 GiB all the time and has nothing left to shrink.

### Seven days of each guest's own used memory (MiB)

Source: the guests' node exporters on the 0mcp Prometheus, `node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes`, `fleet-prom range ... --since 7d --step 1h --instance 0mcp --json` (169 hourly samples; VM 155 has 74, it is three days old). `1-min max` is the same expression with `max_over_time(...[1h:1m])`, which catches a spike inside an hour. `Peak share` is the 1-minute maximum over the guest's visible memory (`MemTotal`) now.

| VM | Name | p50 | p95 (hourly) | Max (hourly) | 1-min max | MemTotal now | Peak share | Guest OOM kills (7 d) | Swap-out, p95 of hourly peaks (MiB/s) | Guest swap max |
|---|---|---|---|---|---|---|---|---|---|---|
| 100 | hermes-agent | 1,210 | 3,479 | 3,888 | 4,315 | 3,974 | 109% | 0 | 18.4 | 1,382 |
| 110 | nginx-lv3 | 822 | 846 | 864 | 991 | 1,927 | 51% | 0 | 0.0 | 155 |
| 120 | docker-runtime-lv3 | 13,446 | 14,136 | 15,336 | 15,997 | 16,261 | 98% | 23 | 0.6 | 8,192 |
| 121 | runtime-comms-lv3 | 1,105 | 1,126 | 1,136 | 1,162 | 1,925 | 60% | 0 | 0.0 | 0 |
| 122 | runtime-apps-lv3 | 709 | 730 | 785 | 901 | 1,413 | 64% | 0 | 0.0 | 149 |
| 130 | docker-build-lv3 | 3,734 | 6,669 | 9,966 | 11,343 | 14,209 | 80% | 164 | 8.3 | 4,096 |
| 140 | monitoring-lv3 | 2,216 | 2,419 | 2,535 | 2,651 | 2,950 | 90% | 0 | 0.2 | 574 |
| 150 | postgres-lv3 | 1,496 | 1,616 | 1,661 | 1,731 | 6,022 | 29% | 0 | 0.0 | 0 |
| 151 | postgres-replica-lv3 | 641 | 658 | 665 | 691 | 902 | 77% | 0 | 0.0 | 0 |
| 152 | postgres-apps-lv3 | 646 | 659 | 668 | 701 | 902 | 78% | 0 | 0.0 | 0 |
| 154 | postgres-data-lv3 | 1,011 | 1,029 | 1,040 | 1,093 | 6,022 | 18% | 0 | 0.0 | 0 |
| 155 | agent-history | 3,067 | 3,099 | 3,154 | 3,239 | 6,022 | 54% | 0 | 0.0 | 0 |
| 170 | coolify-lv3 | 1,494 | 1,630 | 1,813 | 2,762 | 3,974 | 70% | 0 | 0.0 | 780 |
| 171 | coolify-apps-lv3 | 1,265 | 1,291 | 1,301 | 1,321 | 2,950 | 45% | 0 | 0.0 | 122 |
| 180 | artifact-cache-lv3 | 837 | 1,071 | 1,334 | 1,589 | 3,974 | 40% | 1 | 0.0 | 174 |
| 190 | runtime-ai-lv3 | 767 | 783 | 787 | 826 | 1,158 | 71% | 0 | 0.0 | 0 |
| 191 | runtime-general-lv3 | 11,682 | 12,721 | 13,332 | 13,670 | 16,260 | 84% | 1 | 2.6 | 1,708 |
| 192 | runtime-control-lv3 | 3,824 | 3,991 | 4,038 | 4,464 | 6,022 | 74% | 0 | 0.0 | 644 |
| 200 | 0mcp-staging-runtime | no node exporter; one reading 13:5xZ: 1,498 used of 3,974, load 0.09 | | | | | | | | |

Caveats: `used` excludes reclaimable page cache, so a database VM's cache is not in it; the OOM counter is `node_vmstat_oom_kill` and cannot tell a guest-wide OOM from a container hitting its own limit; VM 200 has one reading, taken inside the guest through the guest agent with `cat /proc/meminfo`; a monthly job would not show in seven days.

## 4. What the numbers say

1. **A floor below the measured need starves the guest, and exactly two guests are below it.** Take a floor of at least 1.15 times the one-minute maximum of used memory. Only VM 100 (4,315 x 1.15 = 4,962 against 4,096) and VM 120 (15,997 x 1.15 = 18,397 against 16,384) fail it, and they are the two with symptoms. VM 100 reaches 18.4 MiB/s of swap-out in its hourly peaks at the 95th percentile, and its peak (4,315 MiB) is above the 3,974 MiB it can see now. VM 120 had 23 OOM kills (10-25 21:00Z, 10-26 22:00Z, 10-28 00:00Z to 09:00Z): in the four of those six hours that have samples its `MemTotal` was 16,261 (the floor) and its 8 GiB of guest swap was full. It has had none in the 3.2 days since, and it is pinned at the floor again now with 4.2 GiB of swap used. Every other VM passes (VM 140 only just: 3,049 against 3,072).
2. **VM 130's trouble was a floor too low.** 164 guest OOM kills between 10-27 23:00Z and 10-31 03:00Z, with `MemTotal` between 8,065 and 13,882 MiB (once 20,353) and guest swap up to 4 GiB; its peak used memory was 11.1 GiB. None in the five hours since the restart at 14.2 GiB, which is too short to prove anything.
3. **Memory the host holds beyond the guests' sizes is the larger problem.** VM 122 has 1.4 GiB visible and its QEMU process holds 6.2 GiB (96.6 percent of it in huge pages); VM 171 holds 2.5 GiB more than its floor (80 percent huge pages), VM 155 2.0 GiB (96 percent), VM 192 1.3 GiB (75 percent). The ballooned VMs that sit at their floor (RSS within 3 percent of it) have 25 to 52 percent in huge pages; the VMs that never balloon (the fixed VMs 130, 180 and 200, and VM 191 whose floor is its maximum) have 96 to 100 percent, and the four above their floor look like those. At the 11-01 peak the host's anonymous memory was 117.9 GiB against 94.6 GiB the guests could see (90.6 GiB of the monitored guests plus VM 200's 4), a gap of 21 to 23 GiB by two ways of computing it; VM 130 alone was 9.7 GiB of it (RSS 19.6 against 9.9 GiB visible, read by the session that restarted it).
4. **Unproven mechanism.** The balloon discards 4 KiB pages inside 2 MiB huge pages; `khugepaged` (`max_ptes_none` 511, 861,782 collapses since boot, about 10 GiB a day) may collapse such ranges again and fill the holes. Nothing here measures that. See section 6, "A test, not a proposal".
5. **The host is quiet while it is full.** No memory stalls, little swap I/O, no OOM kill. The danger is a burst with swap full and little cache left (0.6 GiB at the peak, 2.9 GiB now): the next allocation is an OOM kill of a QEMU process (their `oom_score` is 670 to 750; VM 120, VM 191 and VM 130 are the largest).

## 5. The budget

**Rule.**

1. The *guaranteed footprint* (balloon floors of running VMs that have a balloon, plus the whole memory of running VMs with `balloon: 0`) is at most **75 percent of host RAM** (96,537 MiB on `pve-0mcp`) by design, and an **alarm above 80 percent** (102,973 MiB). The capacity model already has 80 percent as its target; 75 is what the measured overheads leave under an 85 percent ballooning target while keeping the owner's 15 percent available (ADR 0494 placement guard): 100 - 15 (available) - 6.7 (held above floors) - 2.4 (host) = 75.9.
2. Memory held above the floors (6.7 percent today, 8.3 percent gross, 17 to 19 percent at the peak) and the host's own 2.4 percent are not budgeted; the swap file is what absorbs them. Swap is not capacity and is not counted.
3. Every raise of a floor, a fixed size or a new guest is paid for by an equal cut elsewhere, or carries an owner-recorded exception (as the VM 155 activation does).
4. A floor is at least 1.15 times the guest's one-minute maximum used memory over seven days, and never below what the guest showed it needs when squeezed (OOM or swap history). A database guest also keeps a page cache (guideline: at least 2.3 times its maximum used), which is performance, not stability.
5. A VM gets `balloon: 0` only if it cannot take squeezing (the CI builder) and then is sized to its peak plus 25 percent.
6. Measure first: the seven-day table above, re-run with the commands in section 9, before any change.

**Expected available memory** is about 100 - guaranteed - 6.7 - 2.4 percent:

| State | Guaranteed (MiB) | Percent of RAM | Expected available |
|---|---|---|---|
| Now | 103,168 | 80.15 | 10.7 (measured) |
| After stage 1 (VM 120 +2,048, VM 154 -2,048) | 103,168 | 80.15 | 10.7 |
| After stage 2 (VM 200 floor 2,560) | 101,632 | 78.96 | 11.9 |
| Also the optional VM 100 +1,024 | 102,656 | 79.75 | 11.1 |
| Also every candidate cut of section 6 | 95,232 | 73.99 | 16.9 |
| CI builder moved off the host (VM 130 retired, owner's plan of 2026-10-29) | 88,832 | 69.01 | 21.9 |

Moving the CI builder is the one change that gets under 75 percent without touching a database's cache.

## 6. Proposals

### Floors

P1, P2 and P4 are live changes with no restart (those VMs already have a balloon device); P3 needs a restart, because a VM with `balloon: 0` has no balloon device.

| Step | VM | Name | Now | Proposed | Change | Restart | Basis |
|---|---|---|---|---|---|---|---|
| P1 | 120 | docker-runtime-lv3 | 16,384 | 18,432 | +2,048 | no | 1-minute max 15,997 of 16,261 visible; 23 OOM kills at the floor; 18,432 is its maximum, so it becomes fixed in effect |
| P2 | 154 | postgres-data-lv3 | 6,144 | 4,096 | -2,048 | no | max used 1,093; floor 3.7 times that; no swap, no OOM; **a trial**: it takes about 2 GiB of page cache from a database |
| P3 | 200 | 0mcp-staging-runtime | 4,096 fixed | 2,560 | -1,536 | **yes** | one reading of 1,498 used; staging; take two more readings during a staging deploy first |
| P4 (optional) | 100 | hermes-agent | 4,096 | 5,120 | +1,024 | no | 1-minute max 4,315; swaps 18.4 MiB/s at the floor; its owner decides if it matters |
| - | 191 | runtime-general-lv3 | 16,384 (= max) | 16,384 | 0 | no | see below |
| - | 130 | docker-build-lv3 | 14,336 fixed | 14,336 | 0 | no | see below |
| - | 180 | artifact-cache-lv3 | 4,096 fixed | 4,096 | 0 | no | see below |

**VM 191 (floor = maximum = 16,384).** Do not lower it. Its used memory is 11,682 at the median, 12,721 at the 95th percentile (above a 12,288 floor) and 13,670 at the one-minute maximum; 1.15 times that is 15,720. A floor of 15,360 would leave 11 percent over the maximum for a gain of at most 1 GiB of host memory, and 12,288 would put the guest below its own 95th percentile.

**VM 120 (floor 16,384, maximum 18,432).** Do not lower it; raise it (P1). The floor already sits 2 percent over the one-minute maximum. It costs 2 GiB of guaranteed memory, which is why P2 pays for it and the swap file comes first.

**VM 154 (floor 6,144, the trial).** Of the database VMs it has the lowest share of its visible memory at the peak (18 percent; VM 150 29, VM 151 77, VM 152 78) and no swap. VM 150 is the HA primary and is left for after the trial.

**VM 130 (fixed 14,336).** No floor. A floor would be pinned by `pvestatd` for most of the week, so it must be at least 1.15 times the 11,343 MiB peak, about 13,000 MiB, which saves at most 1.3 GiB for a second restart of the CI builder; the week before the restart shows what a lower floor costs. The real relief is moving CI off this host.

**VM 180 (fixed 4,096) and VM 200 (fixed 4,096).** VM 180 peaked at 1,589 and 608 MiB of it is already in host swap, but it is the CI artifact cache and a floor needs a restart: leave it (candidate 2,560 at a CI-quiet restart, -1,536). VM 200 is staging: P3.

**Not proposed:** raising `ballooning-target` (it changes when guests are squeezed, not how much memory exists) and changing `shares`.

**Candidates not proposed here (each needs its own page-cache check; none was measured):** VM 150 6,144 to 4,096 (-2,048; max used 1,731; the HA primary), VM 155 6,144 to 4,608 (-1,536; max used 3,239; three days old), VM 192 6,144 to 5,376 (-768; max used 4,464), VM 170 4,096 to 3,584 (-512; its one-minute maximum of 2,762 is a spike far above its hourly 95th percentile of 1,630), VM 180 4,096 fixed to 2,560 (-1,536, restart).

### A test, not a proposal: the huge-page mechanism

If the held-above-floor memory is `khugepaged` refilling what the balloon discarded, then `echo 0 > /sys/kernel/mm/transparent_hugepage/khugepaged/max_ptes_none` (collapse only fully populated ranges; undo by writing 511) stops it from growing, and a balloon cycle of VMs 122, 171, 155 and 192 would then give 8 to 10 GiB back without changing any guest's size. The evidence for the mechanism is correlation only (huge-page share 75 to 97 percent in the four VMs above their floor and 96 to 100 percent in the VMs that never balloon, 25 to 52 percent in the ballooned VMs at their floor; 70 percent host-wide; the huge-page share of anonymous memory rose from about 45 to 73 percent together with the held-above-floor amount on 10-29 to 10-30). The way to find out is a one-day trial on the live host with the metrics of this page as the judge. It is a sysfs write, not part of this PR, and is listed in the apply plan as optional step T1.

### Host swap: add 12 GiB on the quiet NVMe

- *Layout (read-only).* Two SAMSUNG MZQL21T9HCJR NVMe (1.7 TB each, wear 6 percent, 30,647 power-on hours, SMART passed). `nvme1n1` carries `/` (md2, 66 percent used, 614 GB free), `/boot` and the 4 GiB swap `md0`, and holds 16 of the 19 VM disks (`local`); its md arrays have one member each. `nvme0n1` is `/var/lib/vz-nvme1` (ext4, 29 percent used, 1.3 TB free) with the disks of VM 130, 171 and 200 (`local-nvme`).
- *Load over seven days.* `nvme1n1`: busy 26 percent at the median, 35 at the 95th percentile, 575 GB written a day. `nvme0n1`: busy 5 and 19 percent, 1,814 GB a day (CI builds). Swap I/O was at most 2.7 MiB/s out and 0.4 MiB/s in.
- *Size.* 16 GiB in all (12.4 percent of RAM): keep `md0` (4 GiB) and add **12 GiB**. The held-above-floor memory is 10.6 GiB gross today, and 11 to 14 GiB at the 11-01 peak once VM 130's 9.7 GiB is taken out; 12 + 4 covers both with margin. The 4 GiB that exists was 95 to 100 percent used at the 10-30 and 11-01 peaks.
- *Place.* A file at `/var/lib/vz-nvme1/swap/swapfile` (outside every storage content directory, so PVE does not list it), priority -2 so `md0` is used first. It keeps the root filesystem and the 16-VM disk off the swap path and does not need a partition change. Not zram or zswap: both spend RAM on a host that has none to spare.
- *Cost.* Guest pages swapped on the host slow that guest on its next touch; NVMe latency makes this tolerable. Writes on a 6-percent-worn drive are negligible at the observed rates. `vm.swappiness` 60 stays: with 0.6 GiB of page cache left at the peak it has little to choose from.
- *Undo.* `swapoff` pulls the file's pages back into RAM, so it is safe only while the file's used amount is well below MemAvailable (check `swapon --show` first).

### KSM: not now

- *Can the similarity be measured read-only on `pve-0mcp`?* No. KSM is off there (`pages_sharing` 0) and `ksmtuned` is not installed; measuring would mean hashing every guest's memory through `/proc/<pid>/mem`, which reads production guests' secrets and loads a host that had 0.6 GiB of cache at its peak. I did not.
- *Measured on a comparable host.* `pve-0own` (PVE 9.2.21, 64 GB of RAM, 7 guests) runs `ksmtuned` (scan 1,250 pages every 25 ms): `pages_sharing` 1,070,022 (4.08 GiB saved, 8.8 percent of its 46.4 GiB of anonymous memory), `general_profit` 3.33 GiB, `ksmd` CPU 43.5 hours in 29.5 days, **6.1 percent of one core** on average. `pve-0docker`, `pve-0pipe` and `pve-0infer` have KSM off.
- *Why not copy it.* KSM merges 4 KiB pages and splits a huge page before it merges inside it. `pve-0own` has 11 percent of its anonymous memory in huge pages, `pve-0mcp` 70, so the saving would cost the huge pages first and I have no number for that cost (TLB misses, page-table memory, `khugepaged` fighting it). Saving 5 to 9 GiB is plausible and unproven.
- *Trade-offs.* Cross-VM deduplication leaks timing, and this host runs a CI builder and an agent VM next to databases; the fleet has one owner, which lowers the risk and does not remove it. The package (`ksm-control-daemon`) must be installed. **Undo is `echo 0 > /sys/kernel/mm/ksm/run`, never `echo 2`** (unmerging allocates the memory back and could exceed what is free).
- *Verdict.* A time-boxed trial after stage 1, only if the owner accepts the side channel, with `pages_sharing`, `ksmd` CPU, and `RSS - guaranteed` as the judges.

## 7. Apply plan (each step needs the owner's yes; what was taken is in section 11)

Before any step: `ssh operator-bastion`; MemAvailable at least 10 percent; no `vzdump` running (`pgrep -a vzdump`); no CI burst on VM 130; back up the VM config (`cp -p /etc/pve/qemu-server/<id>.conf /root/<id>.conf.pre-balloon-$(date -u +%Y%m%dT%H%M%SZ)`).

| Order | Step | Commands | Restart | Check afterwards | Undo |
|---|---|---|---|---|---|
| A1 | Host swap file, 12 GiB | `mkdir -p /var/lib/vz-nvme1/swap`; `fallocate -l 12G /var/lib/vz-nvme1/swap/swapfile`; `chmod 600` it; `mkswap` it; `swapon --priority -2` it; back up `/etc/fstab`; append `/var/lib/vz-nvme1/swap/swapfile none swap sw,pri=-2,nofail 0 0` | no | `swapon --show` lists 16 GiB; `FleetHypervisorSwapExhausted` clears | `swapoff` the file (only if its used amount is small), `rm` it, restore fstab |
| A2 | VM 154 floor to 4,096 (trial) | `qm set 154 --balloon 4096` | no | in 5 minutes the balloon is at 4,096 and host available is about 2 GiB higher; for 48 h watch the guest's `node_vmstat_pgmajfault` rate, disk read rate and swap | `qm set 154 --balloon 6144` and `echo "balloon 6144" \| qm monitor 154` |
| A3 | VM 120 floor to 18,432 | `qm set 120 --balloon 18432`; `echo "balloon 18432" \| qm monitor 120` | no | `qm status 120 --verbose`: `ballooninfo.actual` 18,432; guest OOM counter flat; host available falls by at most 2 GiB | `qm set 120 --balloon 16384` (`pvestatd` shrinks it back 100 MiB per 10 s) |
| A4 | VM 200 floor 2,560 | `qm set 200 --balloon 2560`; `qm shutdown 200`; `qm start 200` | **yes, staging** | `qm config 200` shows `balloon: 2560`; staging answers | `qm set 200 --balloon 4096` (live, floor = maximum) or `--balloon 0` and a restart |
| A5 (optional) | VM 100 floor to 5,120 | `qm set 100 --balloon 5120`; `echo "balloon 5120" \| qm monitor 100` | no | `ballooninfo.actual` 5,120; the guest's swap-out rate falls | `qm set 100 --balloon 4096` |
| T1 (optional) | `khugepaged max_ptes_none` trial | `echo 0 > /sys/kernel/mm/transparent_hugepage/khugepaged/max_ptes_none` | no | one day: does `RSS - guaranteed` stop growing; `thp_collapse_alloc` flat | `echo 511 > ...` |
| K1 (optional) | KSM trial | install `ksm-control-daemon`, or `echo 1 > /sys/kernel/mm/ksm/run` | no | `pages_sharing`, `ksmd` CPU | `echo 0 > /sys/kernel/mm/ksm/run` |
| C1 | After CI leaves the host | retire VM 130 | n/a | re-run section 9; re-derive the table | n/a |

**Stage 1 is A1, then A2 and A3 the same day.** The order matters: the swap file first (it is the only step that adds safety), A3 spends about 2 GiB and A2 gives back about 2 GiB. Stage 2 is A4 (and A5 if wanted) after 48 h of A2 without regression. Shipping `proxmox-host-memory-budget.yml` to the monitoring VM is separate (role copy plus Prometheus reload, as for the earlier rule files); the alert fires from its first evaluation while the sum is above 80 percent (78.56 between A2 and A3, 80.15 after stage 1, 78.96 after A4), which is the point of it.

## 8. Risks

- **A floor cut starves a guest** (page cache first, then swap, then an OOM kill). P2 is the only cut proposed for stage 1 and it is a trial with a 48-hour gate; its undo is two commands (the floor and the QMP step: a raise reaches the guest only through it).
- **A floor raise takes headroom.** P1 can pull the host from 10.7 to about 9.1 percent available; that is why the swap file comes first.
- **The seven-day window is short** and `used` excludes cache. VM 200 has one reading. The database page-cache cost of P2 was not measured (no Postgres exporter series exist on the 0mcp Prometheus).
- **The huge-page mechanism is a hypothesis.** Do not size anything on it.
- **Swap** slows guests whose pages land in it; `swapoff` needs free RAM.
- **KSM** is a side channel and a CPU cost; undo with `run=0`.
- **`make provision-guests`** (unscoped) undoes every floor and resizes six VMs: see section 2.
- **The alert fires on its first evaluation** (80.15 percent against 80) and stays above the line after stage 1 (80.15) until A4 brings it to 78.96. It is a warning, routed to the warning topic.
- **Parallel state:** the guests, the host and the Prometheus are shared with other sessions; this page changes none of them.

## 9. Evidence and how to repeat it

Raw outputs of the probes (kept outside the repo, in the session notes folder) and these commands:

```bash
# guests, seven days (0mcp Prometheus)
fleet-prom range 'node_memory_MemTotal_bytes{fleet="0mcp",role!="hypervisor"} - node_memory_MemAvailable_bytes{fleet="0mcp",role!="hypervisor"}' --since 7d --step 1h --instance 0mcp --json
fleet-prom range 'max_over_time((node_memory_MemTotal_bytes{fleet="0mcp",role!="hypervisor"} - node_memory_MemAvailable_bytes{fleet="0mcp",role!="hypervisor"})[1h:1m])' --since 7d --step 1h --instance 0mcp --json
# guaranteed footprint: the expression of ProxmoxHostGuaranteedMemoryOverBudget without "> 0.80"
fleet-prom query "$(sed -n '/expr: >-/,/for: 1h/p' config/prometheus/rules/proxmox-host-memory-budget.yml | sed '1d;$d' | tr '\n' ' ' | sed 's/ > 0.80 *$//')" --instance 0mcp
# host (read-only)
ssh operator-bastion 'qm list; qm config <id>; pvesh get /nodes/$(hostname)/qemu/<id>/status/current --output-format json; grep -E "VmRSS|VmSwap" /proc/$(cat /var/run/qemu-server/<id>.pid)/status; grep -E "^(MemTotal|MemAvailable|AnonPages|AnonHugePages|Swap)" /proc/meminfo; cat /sys/kernel/mm/ksm/run /etc/pve/nodes/*/config; lsblk; cat /proc/mdstat; pvesm status'
# other hypervisors' KSM (read-only)
ssh 0own_bastion 'grep . /sys/kernel/mm/ksm/pages_sharing /sys/kernel/mm/ksm/general_profit; ps -o etime,cputime -C ksmd'
```

Numbers that came from outside the 0mcp Prometheus: VM 200's reading (guest agent), the KSM figures (read from `pve-0own`), the host's `/proc` and `/sys` values (13:30Z), and `ballooning-target` and its date (`/etc/pve/nodes/*/config`).

## 10. Follow-ups (not in this change)

- Reconcile `inventory/host_vars/proxmox-host.yml` with the live VMs (six disagreements, VM 160, VMs 100 and 200) and add a per-guest `balloon_mb` the role applies instead of `--balloon 0`, so git can hold floors.
- Put `ballooning-target`, the swap file and any KSM or THP setting under version control (`hostconf` does sysctl and drop-ins only).
- Refresh `config/capacity-model.json` to the live guests.
- Export each VM's host RSS (`memhost`) to Prometheus, so the held-above-floor memory is a metric instead of a probe, and an alert can name the VM.
- Measure the Postgres page-cache need (hit ratio) before any database floor beyond P2.

## 11. Status after stage 1 (2026-11-02 and 2026-11-03)

Written 2026-11-03 from read-only measurements and the commands listed here, each with its undo. The tables above are the 2026-11-01 snapshot and are not rewritten; this section is what changed since.

### What was taken

| Step | Status | Detail |
|---|---|---|
| A1 host swap file, 12 GiB on the quiet NVMe | **not applied; a stopgap exists, the choice is open** | `/swapfile-0mcp-stopgap` (32 GiB) was added by hand on 2026-11-01 at 22:03Z on `/` (`md2`, which is `nvme1n1p3`, the busy NVMe that holds 16 of the 19 VM disks), priority -1, **not in fstab**; see `config/0mcp/hypervisor-swap/README.md`. Swap is 4 + 32 GiB, not the 4 GiB this page assumed. Decide: keep the stopgap and make it persistent, or place the swap on `nvme0n1` as in section 6 and remove the stopgap. Not both: a third area would make 48 GiB. |
| A2 VM 154 floor to 4,096 (trial) | not done, not approved | unchanged |
| A3 VM 120 floor to 18,432 | **applied 2026-11-02 10:43Z** | floor now equal to its maximum; guest memory 15.9 to 17.9 GiB; no guest OOM kill in the 30 minutes after (17 in the 7 days before). Undo: `qm set 120 --balloon 16384`. |
| not in the plan: VM 171 fixed at 3,072 | **applied 2026-11-02 10:41Z** | restart at `memory: 3072`, `balloon: 0` (was maximum 8,192, floor 3,072); its working set peaked at 1.3 GiB in 7 days. Undo: `qm set 171 --memory 8192 --balloon 3072`, restart. |
| not in the plan: VM 122 fixed at 2,048 | **applied 2026-11-02 23:09Z** | restart (was maximum 8,192, floor 1,536); working set peak 0.73 GiB. Undo: `qm set 122 --memory 8192 --balloon 1536`, restart. |
| not in the plan: VM 192 fixed at 6,144 | **applied 2026-11-02 23:11Z** | restart (was maximum 12,288, floor 6,144); working set peak 3.95 GiB; its OpenBao unsealed by itself and all 30 containers were healthy within about 3 minutes. Undo: `qm set 192 --memory 12288 --balloon 6144`, restart. |
| the alert `ProxmoxHostGuaranteedMemoryOverBudget` | **shipped 2026-11-03 17:42Z** | receipt `2026-11-03-pve-0mcp-memory-budget-alert-monitoring-live-apply`; it computes 82.14 percent, so it is pending and fires as a warning after its hour. |

### The numbers now

| VM | Name | Maximum before | Maximum now | Guaranteed before | Guaranteed now |
|---|---|---|---|---|---|
| 120 | docker-runtime-lv3 | 18,432 | 18,432 | 16,384 | 18,432 |
| 122 | runtime-apps-lv3 | 8,192 | 2,048 | 1,536 | 2,048 |
| 171 | coolify-apps-lv3 | 8,192 | 3,072 | 3,072 | 3,072 |
| 192 | runtime-control-lv3 | 12,288 | 6,144 | 6,144 | 6,144 |

- Guaranteed footprint (balloon floors plus the whole memory of VMs with balloon 0): 103,168 to **105,728 MiB**, which is **82.14 percent** of RAM (was 80.15 percent): VM 120 adds 2,048 and VM 122 adds 512; VMs 171 and 192 equal their old floors.
- Sum of the maximums: 142,336 to **124,928 MiB**, which is **97.1 percent** of RAM (was 110.6 percent): the maximums no longer exceed the host.
- The alarm is 80 percent, 102,973 MiB. The footprint is **2,755 MiB** above it. A2 alone gives back 2,048 and leaves 103,680 MiB, 80.55 percent, still above; the candidates of section 6 remain, and nothing here chooses among them.

### What happened to the host, and what it adds to section 4

- Available memory was 6.7 GiB (5.3 percent) at 2026-11-02 10:40Z, 10.7 GiB after VM 171 and A3, and 5.9 GiB (4.7 percent, critical) again at 23:07Z. Between 10:45Z and 23:07Z VM 122 went from 2.5 to 5.5 GiB of host RSS, VM 192 from 7.0 to 9.0 and VM 170 from 4.0 to 5.2, while VM 171, already at a fixed size, did not move. After VM 122 and VM 192 were restarted at fixed sizes the host read 13.3 GiB (10.6 percent) at 23:15Z.
- So a guest with a floor below its maximum ratchets its host RSS back up after a restart, and a fixed size stops it. Whether T1 (`khugepaged`) changes this is not measured.
- Still open: VM 170 (floor 4,096, working set peak 1.87 GiB, host RSS 5.1 GiB), and the two Postgres VMs 150 and 154, which hold about 1.8 GiB each above their floors.
