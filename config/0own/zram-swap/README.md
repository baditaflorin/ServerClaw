# zram swap on the 0own hypervisor

`zram-swap.service`: 8 GiB zstd zram swap (priority 100), a memory safety net for the hypervisor, added 2026-10-19. The unit is kept here because its boot ordering has to be right and
a drop-in cannot fix it (an empty `After=` in a drop-in does not remove a line of the unit file, checked on systemd 257; hostconf manages drop-ins only).

## Why the ordering is what it is

`systemd-analyze verify default.target` on the host named two ordering cycles (the horizon check `boot_ordering_cycle` counted them on 2026-10-22):

1. default dependencies: sysinit.target -> swap.target -> zram-swap.service -> basic.target -> sockets.target -> iscsid.socket -> sysinit.target
2. `After=local-fs.target`: local-fs.target -> zram-swap.service -> swap.target -> tmp.mount -> local-fs.target (`tmp.mount` is After=swap.target and Before=local-fs.target)

At boot systemd breaks a cycle by deleting a start job (it said swap.target, then tmp.mount; it can pick any job of the loop). The unit therefore has `DefaultDependencies=no`, no `After=` of its own,
`Before=swap.target` and, because default dependencies are off, `Conflicts=shutdown.target` / `Before=shutdown.target` put back by hand. `tests/test_zram_swap_unit.py` models both loops and fails when
either edge comes back.

## Install / undo

```
tar -C config/0own/zram-swap -cf - . | ssh 0own_bastion 'd=$(mktemp -d) && tar -C $d -xf - && bash $d/install.sh; rm -rf $d'
```

`install.sh` verifies the unit, backs up what it replaces in `/root/zram-swap-backups`, installs it, removes the superseded hostconf drop-in, reloads systemd (no restart, the running swap
is not touched) and requires `systemd-analyze verify default.target` to print no ordering cycle afterwards; otherwise it puts everything back and exits 1. `bash install.sh --undo` restores the
newest backup. The unit takes effect for the ordering at the next boot; nothing changes for the running swap.
