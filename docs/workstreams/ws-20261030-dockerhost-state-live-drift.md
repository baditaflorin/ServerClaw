# WS-20261030: The VM 100 state backup in git matches what runs on the host

## Status

In review (branch `claude/dockerhost-state-live-drift`). Nothing is installed or changed on VM 100 or own-pbs; the user decides the merge, and installing from git is a separate step.

## Goal

On 2026-10-29 someone extended `dockerhost-state-backup` on VM 100 by hand: 12 inventory entries in the installed script (20:48Z) and 6 archives in the installed config (21:01Z, plus the `usr_local` exclude list). Neither change was in a pull request.
The merged staging change (#617) was installed on 2026-10-30 07:05Z as the merged script with those 12 entries carried over, and the config was left alone. Installing either file from git would therefore have dropped the extra coverage
(the six directories and the rebuild inventory) from the next backup without a word. This change puts them into git, as they run.

## Change

- `dockerhost_state_backup.py`: the 13 added lines (one comment, 12 inventory entries) in `INVENTORY`, exactly as on the host. The file is byte-identical to the live `/usr/local/sbin/dockerhost-state-backup` (sha256 `7d193fa14e815a12a22a2de17dff82fed9c90004d35296bfc782118df3d5dd52`, 1,104 lines, read 2026-10-30 15:05Z).
- `config.json`: the archives `usr_local`, `tailscale`, `dockernet`, `systemd_state`, `url_categorizer_state`, `fleet_container_audit` after `volumes`, in the live order, and `exclude.usr_local = ["/bin/cosign"]`. Equal to the live config apart from whitespace and from four keys the host's copy does not have (`limits.compress_min_bytes`,
  `compress_timeout_s`, `trim_wait_s`, `trim_staging`: the staging change put them in git; their values are the script's defaults, so the host behaves the same).
- `README.md`: a section "Added on VM 100 on 2026-10-29" (what each entry and archive is, sizes, what lands in clear text, the known issue below, live versus git and how to compare), who can read the snapshot, the restore notes.
- `tests/test_dockerhost_state_backup_staging.py`: nine tests pin the archives (names, paths, order, exclude), the client call, the 23 inventory entries as they run, that every command only reads, the failure behaviour of `stage_inventory`, a run with the twelve archives, the known issue and the README sections.
  `tests/test_dockerhost_state_backup.py` is untouched and passes unchanged (it needed no count fixed); it is not formatted for ruff on main and the pre-commit `ruff-format --check` would need a 250-line reformat of it.

## Found while porting (not changed here)

- `docker-noncompose-containers.json` is always empty: docker prints `<no value>` for a missing label, so the `awk 'NF==1'` filter drops the five containers that have no compose label. A working filter would put the full `docker inspect` (with `Config.Env`) of those containers into the snapshot,
  which the script and README rule out. Fix the filter and the environment together (names only, or encrypt the snapshot).
- `systemd_state` carries `credential.secret` and `random-seed`, `tailscale` carries the node key: all in clear in a snapshot that is not client-side encrypted, on a datastore that is not encrypted at rest either (own-pbs `acl.cfg` and zvol read 2026-10-30 15:45Z). The snapshot `2026-10-29T21:13:46Z` already holds them. See the README and the pull request.

## Verification

- The script is byte-identical to the live one (`cmp`, sha256 above). The config differs from the live one only by the four keys named above (canonical diff in the pull request).
- All 79 existing tests pass unchanged; the 9 new tests pass; 12 of 12 hand-made mutations (dropped or reordered archive, changed or reordered inventory entry, a writing command, the awk filter "fixed", README sections removed) are each caught by a new test.

## Rollback

Revert the commit. Nothing on VM 100 changes with the merge.

## Not in this change

The timer slot (VM 100 runs 19:30Z through a drop-in, this directory still says 17:30Z), a fix for the empty non-compose entry, redacting or narrowing any entry or archive, client-side encryption, and installing anything on VM 100 are separate decisions.
