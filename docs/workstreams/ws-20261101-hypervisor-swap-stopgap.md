# WS-20261101: the 0mcp hypervisor's stopgap swapfile is in git

## Status

In review (branch `claude/hypervisor-swap-stopgap`). Documentation, one script, a snapshot of the live state and tests. **This change installs and changes nothing on any host**; the swapfile is
live already (added by hand, 2026-11-01 22:03Z) and is not persisted. The installer's read-only `check` verb was run once against the live hypervisor (22:27Z, exit 2, output in the capture) to test it.

## Goal

On 2026-11-01 the 0mcp hypervisor (`pve-0mcp`) had 8 GiB of 125 GiB available, swap full and VMs configured for 139 GiB. The owner approved a stopgap, and a 32 GiB swapfile
`/swapfile-0mcp-stopgap` was added live. It lived on the host only; `AGENTS.md` rule 5 says a manual server change is documented in the same turn. This puts it in git: why, how to read it,
how to undo it, when to remove it, and an installer that repeats it.

## Change

- `config/0mcp/hypervisor-swap/README.md`: the facts, the reason, the numbers, the undo, the removal criteria, the alerts, the difference from the swap file the memory-budget proposal (PR 653) describes.
- `config/0mcp/hypervisor-swap/install-host.sh`: `check` (read-only, the default), `--apply`, `--persist`, `--remove`. Idempotent; it recognises the live file (path, size, mode, label) and adds only what is missing.
- `config/0mcp/hypervisor-swap/live-state-20261101.txt`: the read-only capture the README quotes.
- `tests/test_hypervisor_swap.py`: the script against a fake host, the README against the script, and a mutation sweep that proves each guard is tested.

## Why no hostconf entry and no ADR

hostconf manages sysctl files, systemd drop-ins and Postgres `conf.d` files; it has no swap or fstab kind (the 16 GiB swapfile of VM701 is in the same position). The install-script pattern of
`config/0mcp` and `config/0infer` is the platform's existing answer for a single host-local change that is not one of those kinds. No ADR: this is a stopgap, not a decision; the lasting
fix is the owner's and belongs to the capacity plan and the memory-budget proposal (PR 653).

## Not in this change

- Persisting the swapfile (`install-host.sh --persist`): a change on a production hypervisor, needs the owner's yes.
- The lasting fix: VM memory sizes that fit the host, or less overcommit (owner decision; docker-prod capacity plan).
- Any alert rule change.

## Verification

`tests/test_hypervisor_swap.py` (script against a fake host, README against script, mutation sweep), then the repository pre-push gate on the build server and Woodpecker.

## Rollback

Revert the commit. The live host is unaffected either way. To remove the swapfile itself: `install-host.sh --remove` (README).
