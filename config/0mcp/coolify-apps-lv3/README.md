# coolify-apps-lv3 (VM 171 on the 0mcp hypervisor): memory

`coolify-apps-lv3` (8 GiB maximum, 4 vCPU) has a **3 GiB balloon floor since 2026-10-30** (`qm set 171 --balloon 3072`, live; it
was 7168). Same method and caveats as `config/0mcp/docker-build-lv3/README.md`.

* **Why.** Over 7 days the guest used a median of 1.2 GiB and never more than about 1.3 GiB (minimum `MemAvailable` 5.6 GiB of
  6.9 GiB visible, average 84 % available), while `pve-0mcp` runs at 8 % available memory. A floor of 3 GiB leaves more than twice the
  observed peak.
* **Effect.** The device was present (`ballooninfo`), so no restart was needed. pvestatd lowered the running target from 7.2 GB
  to 4.8 GB within 6 minutes, and `pve-0mcp` `MemAvailable` was about 12 GiB afterwards. As with VM 130, count on about half of
  what the guest gives back showing up as host `MemAvailable`.
* **Watch.** If Coolify deploys several apps at once, check `free -m` in the guest; the balloon grows back only when the guest
  asks and the host has memory. Roll back with `qm set 171 --balloon 7168` (a config backup is
  `/root/171.conf.pre-balloon-20261029T233717Z` on the hypervisor).
* **Trap.** `make provision-guests` (role `proxmox_guests`) runs `qm set --balloon 0` on every declared guest, which would
  remove this floor (and every other balloon) until the next restart. Do not run it for the whole set; the Makefile already warns
  for VM 155. A per-guest `balloon_mb` in `inventory/group_vars/platform.yml` would fix that and is not done yet.
