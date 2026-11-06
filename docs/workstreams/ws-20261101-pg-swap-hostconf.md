# WS-20261101: the Postgres VM's swap sysctl is a managed hostconf file

## Status

In review (branch `claude/hostconf-pg-swap`). Manifest, one file and documentation only. Nothing is applied: the live VM already has the file and the setting.

## Goal

On 2026-10-31 13:27Z the production DomainScope Postgres VM (VM701, `infer-pg-primary`) got a 16 GiB swapfile on its root disk and `/etc/sysctl.d/91-pg-swap.conf`
(`vm.swappiness = 10`), after the 01:25Z global OOM killed nine postgres processes. That sysctl file lived on the host only. hostconf exists so that host-local configuration is in
git, a rebuilt VM keeps it and a hand edit shows up as drift.

## Change

- `config/hostconf/files/sysctl-pg-swap.infer-pg-primary.conf`: `vm.swappiness = 10`, byte-identical to the live file (644 root:root, 19 bytes).
- `config/hostconf/hostconf.yaml`: entry `sysctl-pg-swap.infer-pg-primary` (destination `/etc/sysctl.d/91-pg-swap.conf`, expect `sysctl vm.swappiness = 10`) and the entry added to the
  host's file list. The purpose text records why, and the commands that rebuild the swapfile and its fstab line, which hostconf does not write (it manages drop-ins only).
- `config/hostconf/README.md`: 65 catalog files, and the swappiness line mentions this VM.

## Verified live (read-only)

2026-11-01 13:27Z, VM701: file content and mode as above, `free -m` Swap 16383 total / 147 used, fstab line `/swapfile none swap sw,pri=10 0 0`. After the entry was added,
`python3 scripts/hostconf.py drift --host infer-pg-primary` reports 10 of 10 items ok, including `/etc/sysctl.d/91-pg-swap.conf`.

## Not in this change

- The swapfile and the fstab line are not managed files. A rebuild follows the commands in the manifest entry.
- The hub alerts for this swap (PgPrimarySwapUsed, PgPrimarySwapIn, PgPrimarySwapAlmostFull) live in go-fleet-metrics-hub (0.1.17), not here.

## Verification

`python3 scripts/hostconf.py check` (42 hosts, 65 files), the three hostconf test files (201 passed), the live read-only drift check, then the repository pre-push gate on the build server.

## Rollback

Revert the commit. The live VM is unaffected either way.
