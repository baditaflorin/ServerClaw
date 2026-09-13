# Proxmox storage recovery

Private-source definition for the `0mcp` and `0docker` host timers. It is
limited to journal/apt cleanup, guest TRIM, and resuming QEMU `io-error` guests
only after `local` is active and at least 50 GiB/5% is free. It never deletes
VM disks, snapshots, backups, containers, or application data.

Each host receives a unique ntfy credential, stored only at
`/etc/<host>-storage-recovery/ntfy-password` with mode `0600`. The identities
are write-only to `platform-proxmox-critical`. `0mcp` uses its private ntfy VM
endpoint; `0docker` uses the public endpoint. A marker emits one notification
per recovery episode and resets once the host is healthy.
