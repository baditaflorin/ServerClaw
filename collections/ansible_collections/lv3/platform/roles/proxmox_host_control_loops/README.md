# proxmox_host_control_loops

Converges the ADR 0226 host-resident control-loop baseline on the Proxmox
host by installing a managed reconcile script plus matching `systemd` service,
timer, and path units.

Inputs: unit names, filesystem roots, timer cadence, and timeout semantics for
the host reconcile loop. Retry is delegated to the timer, path trigger, or an
explicit operator start instead of a service-level restart loop.
Outputs: `/usr/local/libexec/lv3-host-control-loop-reconcile.py`,
`/etc/systemd/system/lv3-host-control-loop-reconcile.{service,timer,path}`,
and verification state under `/var/lib/lv3-host-control-loops`.
