# ct-names data disk on the 0own runtime VM

`go-ct-names` (private Certificate Transparency name service, registry port 18336) runs on the 0own runtime VM 660 (ssh alias `0own_staging_runtime`,
the "0own" cluster of the fleet runner). Its data (sorted name sets, snapshots, run history; names only, never certificates) lives on its OWN
virtual disk, mounted at `/srv/ct-names`, with a hard IO cap at the Proxmox layer. Nothing here is applied by merging; a person runs the
scripts in this order (step 3 needs the OpenObserve ingest credential from the vault, piped, never typed). Every script is plan-only until `--apply`, and `tests/test_ct_names_0own_scripts.py` pins the guards.

| Step | Where | Script | Changes |
|---|---|---|---|
| 0 | hypervisor (`0own_bastion`) | `io-probe.sh --dir /var/lib/vz` | writes and deletes a 512 MB scratch file; aborts if io full avg10 > 10 % (it is usually higher: see the infra plan) |
| 1 | hypervisor | `attach-data-disk.sh` then `--apply` | a thin 1 TiB ZFS volume `rpool/data/vm-660-disk-N` (volblocksize 64k), attached as `scsi1` with `backup=0`, serial `CTNAMES0`, caps 15 MB/s write, 30 MB/s read, 100 write IOPS, 200 read IOPS; VM config saved to `/root/ct-names-backups/` |
| 2 | inside VM 660 | `prepare-data-disk.sh` then `--apply` | one ext4 (label `ctnames`, `-m 0`, no online discard) on the blank disk, an fstab line by UUID with `nofail`, `/srv/ct-names/data` owned by the container uid |
| 2a | inside VM 660 | `exclude-weekly-trim.py` then `--apply` | adds `X-fstrim.notrim` to the existing CT fstab entry only, after verifying the mounted label and UUID; saves a backup and does not remount or restart the service |
| 2b | inside VM 660 | `verify-data-dir.sh` (read-only) | checks, before the first deploy: `/srv/ct-names` is a mount point on its own device (not the root disk), `/srv/ct-names/data` is owned `10001:10001` mode 0750, uid 10001 can create a file there, at least 900 GiB free, the fstab line has `nofail`, and (once the compose directory exists) the deploy `.env` says `CT_DATA_HOST_DIR=/srv/ct-names/data`. Exit 1 on any failure |
| 3 | inside VM 660 | `install-log-shipper.sh --apply` (credentials as ONE JSON object on stdin) | the Vector log shipper, for the `go-ct-names` container only, to the OpenObserve stream `docker_logs` (fleet `0own`, host `0own-runtime`); config root-only 0600; validated first, rolled back if the agent does not start. VM 660 has no shipper today |

Run from the repo copy, for example
`tar -C config/0own/ct-names -cf - . | ssh 0own_bastion 'd=$(mktemp -d) && tar -C $d -xf - && bash $d/attach-data-disk.sh; rm -rf $d'`
(for step 2 use `0own_staging_runtime`).

## The data directory, end to end

- Host path `/srv/ct-names/data`, owned `10001:10001` (the container user, see the service's Dockerfile), mode 0750, on the dedicated ext4 disk. The deploy reads it from `CT_DATA_HOST_DIR`,
  which the service declares as `extra_env` in its `service.yaml` (the runner writes it into `/opt/services/<dir>/.env`; nobody edits that file by hand). The compose default is `./data`, i.e. the
  VM's root disk, so run `verify-data-dir.sh` before the first deploy and after any disk or fstab change.
- If the disk is ever missing at boot (`nofail`), docker creates `/srv/ct-names/data` as `root:root` on the root disk and the container cannot write: it fails loudly instead of filling the root disk. Do not chown it then; fix the mount.
- Expected size (measured, docs/SIZING.md of go-ct-names): 17.2 bytes per name merged, 18 per flushed name; 5.05 million ccTLD names after 33 minutes = 87 MB; about 1.8 GB merged and about 50 GB with 30 retained daily snapshots if CT shows 100 million names.
  The 1 TiB thin volume is a ceiling 20 times above that; the service pauses reading below `CT_MIN_FREE_GB` (10) / `CT_MIN_FREE_PCT` (5).
- IO caps (set by `attach-data-disk.sh` on the Proxmox disk, not in the guest): 15 MB/s write, 30 MB/s read, 100 write and 200 read IOPS. The service itself wrote about 1 MB/s while reading at 100 MB/s from the network.

## Trim and thin-pool capacity

The guest weekly fstrim must skip this disk: its 1 TiB of free extents passes through the 15 MB/s virtual-disk throttle and can keep the disk busy for many hours. On 2026-11-09 it held the reader's I/O-pressure guard. `X-fstrim.notrim` applies to `fstrim --listed-in /etc/fstab:/proc/self/mountinfo` and leaves the VM's other filesystems on the normal weekly timer. The option does not disable an explicit `fstrim /srv/ct-names`. A new filesystem gets this option from `prepare-data-disk.sh`; for an existing filesystem run `exclude-weekly-trim.py` plan and then `--apply`, and verify `fstrim -n -A -v` omits `/srv/ct-names`. Do not run a full explicit trim while the reader or shared storage is busy.

Exclusion means deleted guest blocks remain allocated in the thin ZFS volume until reclaimed. Guest `df` is not the pool usage. Check the actual zvol and pool on the hypervisor with `zfs list -o name,used,refer,volsize rpool/data/vm-660-disk-1` and `zpool list rpool`; investigate growth and capacity before the pool's free-space floor is threatened. On 2026-11-09 the zvol used about 408 GiB while the guest held about 8 GiB of files. Reclamation is performed by `reclaim/ct-names-reclaim.timer` one 128 MiB ext4 block group per tick, only when reader metrics are present, the reader is active and unpaused, and guest IO pressure is below 10%. The child retains the exclusive lock if it gets stuck in uninterruptible IO. The script stops attempting a group when pressure reaches 40% or after 15 seconds; kernel IO can outlive a kill, so the timer must never launch another worker while the inherited lock is held. A successful group is checkpointed atomically; a failed or interrupted group is retried without advancing. At one group per 45 seconds a full 1 TiB sweep takes at least 4.3 days. An ext4 free extent may extend beyond the requested length, so each call covers one complete verified block group, not an assumed tiny byte range.

`reclaim/install.sh guest --install` installs the worker and units without enabling them; `reclaim/install.sh hypervisor --install` installs a read-only zvol-allocation exporter on the hypervisor. Publish and test the central `ct-names-reclaim-alerts` rules, verify both hosts' textfile metrics are scraped and alert routing works, then enable the hypervisor timer and the guest timer with the same installer and `--enable`. On failure, stop the guest timer, wait for its service and fstrim process to exit, preserve `/var/lib/ct-names-reclaim/state.json`, and inspect the journal and metrics. Do not kill or bypass a stuck discard by starting a duplicate worker. A stale/missing exporter, repeated error, two hours without progress, or high zvol allocation alerts operators. `fstrim` reports discarded extents, not actual ZFS space recovered; verify the hypervisor's zvol allocation trend separately.

Live state on 2026-11-09: both timers were installed and enabled from merged commit `f2458c5`. Central Prometheus loaded the reclaim rules and scraped both hosts. The guest first deferred above the IO limit, then successfully advanced its durable cursor by one group while the reader kept running. An entire sweep and an actual reduction in ZFS allocation remain unverified.

## Why these numbers

- Thin volume, 1 TiB ceiling: nothing is reserved; the pool (`rpool`, 7.3 TB mirror of two spinning disks) only gives blocks that are written. The script refuses when
  the pool has less than 1.5 TiB free, because the PBS datastore (a 5 TiB volume holding 3.4 TiB) and the build worker can still grow into that space. Expected real use is
  far below the ceiling (see the infra plan for the estimate and its assumptions).
- IO caps are ceilings, not the plan. The expected sustained average is below 2 MB/s (append-only daily segments plus periodic merges); the pool today averages about 19 MB/s of writes
  and its two disks are busy 52 % of the time on average, so the writer must stay a small, polite share. The caps make a runaway merge slow itself down, not the builder or the keystore replica.
- `backup=0`: the first PBS backup of a new disk reads all of it, the data can be rebuilt from the public logs, and the store should back up its own immutable snapshots instead
  (open decision in the infra plan). `serial=CTNAMES0` lets the guest find the disk without guessing `/dev/sdX`.
- Separate filesystem: its own ext4 journal, so a long fsync on this disk does not stall the root filesystem the keystore replica and 50 pool workloads use (inside VM 610 one shared journal was the
  cause of the stalls described in the build-worker notes).

## Rollback

- To stop unattended reclaim, disable `ct-names-reclaim.timer` and wait for `ct-names-reclaim.service` and its child to exit; keep its checkpoint for resumption. Disable `ct-names-zvol-metrics.timer` only after retiring the corresponding alerts.
- To undo the weekly trim exclusion, restore the corresponding `/root/ct-names-backups/fstab.pre-trim-policy-*` backup after checking for intervening fstab changes, or remove only `X-fstrim.notrim` from the CT entry. This restores the original risk of long weekly trims.

- `prepare-data-disk.sh` has no undo: stop the service, `umount /srv/ct-names`, remove the fstab line (the backup is in `/root/ct-names-backups/`).
- `attach-data-disk.sh --undo` detaches the disk (refuses any disk without our serial) and prints the `zfs destroy` command for the freed volume; it never runs it, because that deletes data.
