# fleet_hypervisor_memory_reclaim

Releases memory that a ballooning Proxmox hypervisor holds in deferred-split transparent huge pages. One systemd timer checks
`MemAvailable` every 5 minutes and, only while it is under `fleet_hypervisor_memory_reclaim_threshold_percent` (default 10%),
runs `echo 2 > /proc/sys/vm/drop_caches`, which runs every kernel shrinker once.

Why it exists (found 2026-10-13 on pve-0mcp): the host read 3% MemAvailable and 99.5% swap used, with ~141 GB of guest RAM
configured on 128 GB. pvestatd had already ballooned every guest to its floor, but QEMU backs guest RAM with transparent huge
pages: when the balloon driver returns scattered 4 KiB pages the host splits the huge page lazily, so the freed part stays
allocated (queued for a deferred split) and is counted neither as free nor as available until memory pressure runs the
shrinkers. One `drop_caches=2` moved MemFree from 2.2 GB to 15.3 GB and AnonPages down by 8.6 GB with no swap activity and no
guest impact. Without the timer the memory is stranded again after the next balloon change.

It touches no guest, no file data (`drop_caches=2` only drops reclaimable slab) and writes one textfile metric set
(`fleet_hypervisor_memory_reclaim_*`) when `fleet_hypervisor_memory_reclaim_textfile_dir` is set. The alerts that watch the result
are in `config/prometheus/rules/fleet-hypervisor-memory.yml`.

Run it like the other fleet roles: `playbooks/fleet-observability.yml --limit <one host> --tags memory-reclaim --check --diff` first.
Rollback: `systemctl disable --now fleet-hypervisor-memory-reclaim.timer`, remove the two unit files and
`/usr/local/sbin/fleet-hypervisor-memory-reclaim`, `systemctl daemon-reload`.
