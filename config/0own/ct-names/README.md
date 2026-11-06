# ct-names data disk on the 0own runtime VM (prepared, not applied)

`go-ct-names` (private Certificate Transparency name service, registry port 18336) runs on the 0own runtime VM 660 (ssh alias `0own_staging_runtime`,
the "0own" cluster of the fleet runner). Its data (sorted name sets, snapshots, run history; names only, never certificates) lives on its OWN
virtual disk, mounted at `/srv/ct-names`, with a hard IO cap at the Proxmox layer. Nothing here is applied by merging; a person runs the
scripts in this order (step 3 needs the OpenObserve ingest credential from the vault, piped, never typed). Every script is plan-only until `--apply`, and `tests/test_ct_names_0own_scripts.py` pins the guards.

| Step | Where | Script | Changes |
|---|---|---|---|
| 0 | hypervisor (`0own_bastion`) | `io-probe.sh --dir /var/lib/vz` | writes and deletes a 512 MB scratch file; aborts if io full avg10 > 10 % (it is usually higher: see the infra plan) |
| 1 | hypervisor | `attach-data-disk.sh` then `--apply` | a thin 1 TiB ZFS volume `rpool/data/vm-660-disk-N` (volblocksize 64k), attached as `scsi1` with `backup=0`, serial `CTNAMES0`, caps 15 MB/s write, 30 MB/s read, 100 write IOPS, 200 read IOPS; VM config saved to `/root/ct-names-backups/` |
| 2 | inside VM 660 | `prepare-data-disk.sh` then `--apply` | one ext4 (label `ctnames`, `-m 0`, no online discard) on the blank disk, an fstab line by UUID with `nofail`, `/srv/ct-names/data` owned by the container uid |
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

- `prepare-data-disk.sh` has no undo: stop the service, `umount /srv/ct-names`, remove the fstab line (the backup is in `/root/ct-names-backups/`).
- `attach-data-disk.sh --undo` detaches the disk (refuses any disk without our serial) and prints the `zfs destroy` command for the freed volume; it never runs it, because that deletes data.
