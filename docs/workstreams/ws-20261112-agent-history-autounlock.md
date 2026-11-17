# ws-20261112-agent-history-autounlock

ADR 0494 amendment of 2026-11-12. The agent-history data volume (LUKS2) used to need the owner to type the passphrase after every
reboot, so a restart of the guest or its host left the store down until someone did. A boot unit now reads the passphrase from
OpenBao with a dedicated unlock AppRole and pipes it into the existing `agent-history-unlock`.

## What changed

- `agent-history-autounlock.service`, `agent-history-autounlock` and `agent-history-luks-passphrase` in the
  `agent_history_runtime` role (`agent_history_luks_autounlock_enabled`, off by default, on for the guest in
  `inventory/host_vars/agent-history.yml`). The value goes through one pipe: never an argument, an environment variable, a file
  or a log line. The unit retries every 30 seconds without limit.
- Fix: `agent-history.service` used `ConditionPathIsMount=`, which systemd does not have; it was ignored and the unit ran before the
  disk was unlocked. It is `ConditionPathIsMountPoint=` now.
- `tests/test_agent_history_autounlock.py`: static guards plus the real fetcher against a fake OpenBao (success, rejected login,
  missing key, unreachable).
- ADR 0494 amendment and the runbook section "Unattended unlock".

## Not done here (owner and OpenBao administrator)

1. Create the unlock policy and AppRole (read on `kv/data/services/agent-history/luks` only, address-bound, reusable secret id) and deliver its two files; the passphrase itself already exists there (key `passphrase`).
2. Converge with `make provision-agent-history-vm`, then prove the unlock in a quiet window (the runbook lists the steps).

No secret value is in this change, and none passed through the session that wrote it.
