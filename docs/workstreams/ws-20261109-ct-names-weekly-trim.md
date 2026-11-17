# CT names weekly trim

On 2026-11-09 the reader stopped on its IO-pressure guard after the VM's weekly fstrim started against the capped 1 TiB CT volume. The blocked trim was stopped and the reader resumed.

The CT volume's fstab entry now has `X-fstrim.notrim`. The exact systemd fstrim command's dry run skips that volume and still selects root and EFI; the timer is active, and the reader continued and committed checkpoints. The script and rollback procedure are in `config/0own/ct-names/`. The backup of the previous fstab is on the VM under `/root/ct-names-backups/`.

The ZFS zvol held about 408 GiB while the guest had about 8 GiB of files. The exclusion leaves space reclamation as an operational follow-up; do not mistake guest free space for free pool space. The runbook records the capacity checks and manual trim cautions.

## Unattended reclaim follow-up

A paced, checkpointed block-group trim and a hypervisor zvol exporter are installed and enabled. Safety checks require the expected filesystem and disk, healthy reader metrics, and low IO pressure. A single inherited lock prevents overlapping a stuck trim. Central alerts for missing metrics, errors, stalled progress and zvol growth are required before enabling the timer. On 2026-11-09 the timer first deferred under pressure, then completed a block group and persisted the 128 MiB cursor. The central Prometheus instance scraped both exporters and loaded the seven rules; the reader continued to advance. A full sweep and a sustained reduction of the actual zvol allocation have not yet been observed.
