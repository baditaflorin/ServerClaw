# WS-20261029: Lower the peak staging size of the VM 100 state backup

## Status

In review (branch `claude/dockerhost-state-staging-peak`). Nothing is applied to VM 100 or own-pbs; the user decides the merge and the install.

## Goal

`dockerhost-state-backup` on VM 100 staged about 18 GiB on the guest's root disk (three SQLite online copies: chaos.db 8.47 GiB, graph.db 6.67 GiB, kuma.db 2.37 GiB) before one `proxmox-backup-client` call, and deleted it afterwards. The guest disk is a qcow2 on the hypervisor's only filesystem (`/dev/md3`), so every day the hypervisor's free space fell by about four points for twenty minutes. On 2026-10-28 it reached 13.72 % free at 17:55Z and was under the 14 % CI admission hold from 17:47 to 17:56Z (`PveHostFilesystemAdmissionHold` 17:49 to 17:55Z), the first time since 2026-10-22. The goal is a lower peak without changing what is backed up.

## Change

- The SQLite copies are made one at a time, largest first. A copy of 64 MiB or more is compressed with `zstd -1`, read back and compared by sha256, and only then is the raw copy deleted. The staging directory holds one raw copy plus the compressed files so far.
- The blocks of every deleted raw copy, and of what is left of the staging after the run, are given back to the disk right away (FITRIM of exactly the extents they held, after an fsync of the directory: ext4 offers a freed block to FITRIM only after the delete has committed). Without the trim the same change put 21.9 GiB on the disk file against 18.2 GiB for the old script, because ext4 does not reuse the blocks of a file it has just freed.
- A self-test before the first copy checks that trimming works here; if not, the run stages as before and ends failed with a warning. Any failure to compress (zstd missing, a timeout, a mismatch) keeps the raw copy: the backup is complete either way.
- `MANIFEST.json` records per copy what was staged (`staged`, `codec`, `copy_bytes`, `staged_bytes`, `sha256` of the raw copy) and the run's `staging_peak_bytes`; a new metric `dockerhost_state_backup_staging_peak_bytes` is exported.
- README: restore recipe for a `.zst` copy, the Staging peak section with the numbers, switches and rollback. Tests: `tests/test_dockerhost_state_backup_staging.py` (the existing test file is untouched).

## Verification

- Bench on `0mcp_artifact_cache` (full-size synthetic databases at the compression ratios measured on the real files, guest disk modelled as a sparse file): peak staged 18.18 to 10.05 GiB, peak on the disk file 18.18 to 10.05 GiB, 4.07 GiB staged when the client starts. Details and the codec speeds are in the README.
- Restore drill of one compressed copy (chaos.db, 8.5 GiB) through a scratch Proxmox Backup Server with the real client 3.4.9: see the README.
- 79 tests (46 existing and 33 new) pass on Python 3.9 and 3.12; 12 hand-made mutations of the script are each caught by a test.

## Rollback

Set `limits.compress_min_bytes` to 0 in the installed `config.json` (the run then stages as it did before, all at once), or reinstall the previous `dockerhost_state_backup.py`. Nothing in PBS needs to change: the group, the snapshot layout and the archives are the same.

## Not in this change

Moving the timer to a quieter hour (a drop-in on VM 100 moved it to 19:30Z on 2026-10-29; the timer in this directory still says 17:30Z), the NVMe replacement and CT108's own disk growth are separate decisions. Whether `chaos.db` (a mirror of ProjectDiscovery's public Chaos corpus) can be left out because it can be rebuilt is the owner's decision; this change does not exclude it. graph.db is 86.5 % free pages: a VACUUM by its owner would take about 5.8 GiB off the disk and the nightly copy.
