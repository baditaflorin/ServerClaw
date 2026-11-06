# WS-20261101: standby-ctl keeps the guest's own account when a step times out

## Status

In review (branch `claude/standby-guest-diag`, ADR 0188 for the daily failover rehearsal). Code, tests and README only. Nothing is installed on the hypervisor: `host/install-host.sh` after the merge is a separate step that needs the owner's yes.

## Goal

The daily DomainScope standby rehearsal (VM 8101 on 0infer) failed on 2026-10-31 with `silent: guest exit 124` and `teardown: guest exit 124`. The record said only "guest command did not finish in time". The cause (found by reading the hypervisor journal, the host and guest metrics and the stopped guest's disk read-only) was a hang in the guest's boot: docker never finished starting. The guest's own journal of that boot was gone by the next day, so the evidence for what docker or containerd waited on does not exist. The next occurrence should not need a forensic read of a disk.

## Change

- `config/0infer/tier0-runner/host/standby_ctl.py`: `Ctl.g()` calls `capture_guest_diag()` on the first guest exit 124 of a run. It runs `GUEST_DIAG` in the guest (25 s limit, `timeouts.diag_s`): uptime, queued systemd jobs, unit states of containerd, docker.socket, docker, cloud-final and multi-user.target, the containerd and docker journal of this boot, kernel warnings, processes in D state, memory, disk. Every command is bounded with `timeout` and none calls docker (the hang it exists for is the one where docker answers nothing). The text is scrubbed, capped at 3,500 characters and lands in the record as `guest_diag` (rehearse and activate) and is logged. When the agent is wedged too, the field says `unavailable: guest exit ...` and the run goes on; the diagnostic can never replace the failure or skip the teardown, link down or power off.
- `config/0infer/tier0-runner/README.md`: documents the field and why the guest's own journal cannot be relied on (journald `SystemKeepFree=5G` with about 5 GB free on the guest disk).
- `tests/test_standby_ctl_guest_diag.py`: seven tests (silent timeout leaves the diagnostic before the teardown; one per run when teardown hangs too; wedged agent; the script never calls docker and bounds every command; nothing secret survives; no diagnostic on a healthy run or an ordinary exit code; activation keeps it too). Mutation-checked: without the call on 124, six fail; without the once-per-run guard, one fails.

## Not in this change (proposed to the owner)

- A recovery in the silent step (restart containerd and docker once when `docker ps` does not answer in ~30 s, record the run as `degraded`). It would change the failover path and its effect is unproven without the evidence this change collects.
- Guest journal retention and the guest disk (5.6 GB free of 50 GB, 89 %): a change to the DR VM image.

## Verification

`uv run --no-project --with pytest --with pyyaml --with jsonschema python -m pytest tests/test_standby_ctl_guest_diag.py tests/test_standby_ctl.py` (122 passed; the fake speaks the real `qm` command line and syntax-checks every guest script with `bash -n`), then the repository pre-push gate. No host is contacted.

## Rollback

Revert the commit; the installed controller on the hypervisor is unchanged until `install-host.sh` is run.
