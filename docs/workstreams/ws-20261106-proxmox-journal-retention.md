# Proxmox journal retention

The unattended-operation audit found that the Proxmox host relied on journald's
filesystem-relative defaults and retained 3.1 GiB. Emergency storage recovery
vacuumed only after root free space crossed its threshold. Routine journal
retention should have its own fixed budget, so a larger filesystem does not
silently increase the log budget.

The reusable common-role journal-retention entrypoint installs a dedicated drop-in
on a systemd host or guest. The host control-loop role imports it by default:
1 GiB persistent, 256 MiB volatile, 30 days, one-day files, and 5 GiB persistent
free-space reserve. It backs up an existing file and restarts only journald on a
change. A tag allows applying this concern without replaying the host baseline.

Live first apply: 2026-11-06T16:30:47Z. The original main configuration is backed
up on the host. Journald restarted successfully and reported max 1 GiB, with
987.7 MiB current use. The role and receipt preserve the durable replay path.

The same limits were applied to the runtime guest on the inference fleet,
reclaiming 3,279,482,880 bytes of local journal storage. The production Docker
guest also had a daily logrotate failure: a legacy catch-all matched distro
logs twice. A source-managed policy now covers the four active fleet-tool
paths explicitly, with full-system validation and rollback in its targeted
Ansible apply. The service now completes successfully and its timer is active.

Plane registration was attempted; this fresh checkout has no private Plane
authentication overlay. The workstream shard is the authoritative fallback.

PR678 merged as `bdf914506728be8c6a81013b472864552161f126`. Both exact-head
Woodpecker pipelines passed. The host journal and production rotation playbooks
were replayed from that main commit with zero changes and no failures. The
inference runtime guest received the exact rendered template, differing only
in its provenance comment; both live journal files match the rendered source
hash. The mainline receipt records the evidence and platform version 0.179.57.
