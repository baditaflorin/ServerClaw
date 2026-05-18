# ADR 0184 Live Apply Summary

- Source commit applied: `7170cd157adaedb865a9c34b28f7e5fbdf1f818f`
- Platform version observed during verification: `0.130.31`
- Verified guest labels live on: `110`, `120`, `130`, `140`, `150`, `160`

## Replay Notes

1. The stock `make provision-guests` workflow was replayed first from the latest-main worktree.
2. That replay failed on existing platform drift outside ADR 0184:
   - `qm status 151` reported that `postgres-replica-lv3` does not exist.
   - the configured template `9002` for `lv3-postgres-host` is also absent on the host.
3. To avoid mixing ADR 0184 with standby reprovisioning work, the guest converge was replayed again with a scoped `proxmox_guests_active` override for the guests that actually exist: `110/120/130/140/150/160`.
4. That scoped replay successfully applied the new failure-domain and anti-affinity tags to the existing managed guests.
5. `backup-lv3` still reported only the legacy `backup;lv3;pbs` tags after the replay, so one explicit follow-up command was executed on the host:

```bash
qm set 160 --tags "aag-control-plane-recovery;backup;exc-same-domain;fd-host-proxmox-host;lv3;pbs;pc-recovery"
```

6. Final verification confirmed the expected tag set on all existing managed guests and re-confirmed that `151` remains absent.

## Merge Notes

- Protected integration files were intentionally left unchanged on this branch.
- The missing `151` standby VM should be treated as separate live drift, not silently absorbed into ADR 0184 merge work.
