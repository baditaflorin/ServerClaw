#!/usr/bin/env python3
"""Publish per-backup-group freshness metrics of a Proxmox Backup Server datastore for node_exporter's textfile collector.

Walks the datastore directory tree (no API token, no secrets): <store>/{vm,ct,host}/<id>/<RFC3339 snapshot>/ for the root
namespace and <store>/ns/<name>/{vm,ct,host}/<id>/<snapshot>/ for namespaces (nested namespaces are walked too).

Metrics (labels datastore, namespace ("" is the root namespace), backup_type, backup_id):
  pbs_backup_group_last_snapshot_timestamp_seconds   newest snapshot time of the group
  pbs_backup_group_snapshot_count                    snapshots currently kept
  pbs_backup_collect_timestamp_seconds{datastore}    when this run finished (alert on staleness of the collector itself)

Installed on own-pbs as /usr/local/sbin/pbs-backup-metrics by a systemd timer (see docs/runbooks/pbs-0own-backups.md).
"""
import argparse
import calendar
import os
import re
import sys
import tempfile
import time

TS = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z$")
TYPES = ("vm", "ct", "host")


def snap_epoch(name):
    m = TS.match(name)
    if not m:
        return None
    y, mo, d, h, mi, s = (int(x) for x in m.groups())
    return calendar.timegm((y, mo, d, h, mi, s))


def scan_groups(base):
    """Yield (backup_type, backup_id, [epochs]) for the groups directly under one namespace directory."""
    for btype in TYPES:
        tdir = os.path.join(base, btype)
        if not os.path.isdir(tdir):
            continue
        for bid in sorted(os.listdir(tdir)):
            gdir = os.path.join(tdir, bid)
            if not os.path.isdir(gdir):
                continue
            epochs = [e for e in (snap_epoch(n) for n in os.listdir(gdir)) if e is not None]
            yield btype, bid, epochs


def walk(store):
    yield "", store
    stack = [("", store)]
    while stack:
        ns, base = stack.pop()
        nsroot = os.path.join(base, "ns")
        if not os.path.isdir(nsroot):
            continue
        for child in sorted(os.listdir(nsroot)):
            cdir = os.path.join(nsroot, child)
            if os.path.isdir(cdir):
                cns = child if not ns else ns + "/" + child
                yield cns, cdir
                stack.append((cns, cdir))


def esc(v):
    return v.replace("\\", "\\\\").replace('"', '\\"')


def render(datastore, store):
    out = [
        "# HELP pbs_backup_group_last_snapshot_timestamp_seconds Unix time of the newest snapshot of a PBS backup group.",
        "# TYPE pbs_backup_group_last_snapshot_timestamp_seconds gauge",
    ]
    counts = []
    for ns, base in walk(store):
        for btype, bid, epochs in scan_groups(base):
            if not epochs:
                continue
            lab = 'datastore="%s",namespace="%s",backup_type="%s",backup_id="%s"' % (esc(datastore), esc(ns), btype, esc(bid))
            out.append("pbs_backup_group_last_snapshot_timestamp_seconds{%s} %d" % (lab, max(epochs)))
            counts.append("pbs_backup_group_snapshot_count{%s} %d" % (lab, len(epochs)))
    out += [
        "# HELP pbs_backup_group_snapshot_count Snapshots currently kept for a PBS backup group.",
        "# TYPE pbs_backup_group_snapshot_count gauge",
    ] + counts + [
        "# HELP pbs_backup_collect_timestamp_seconds Unix time this collector last finished.",
        "# TYPE pbs_backup_collect_timestamp_seconds gauge",
        'pbs_backup_collect_timestamp_seconds{datastore="%s"} %d' % (esc(datastore), int(time.time())),
    ]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--datastore", default="own-pbs")
    ap.add_argument("--store-path", default="/mnt/pbs-datastore/store")
    ap.add_argument("--textfile-dir", default="/var/lib/prometheus/node-exporter/textfile")
    ap.add_argument("--stdout", action="store_true", help="print instead of writing the .prom file")
    args = ap.parse_args()
    if not os.path.isdir(args.store_path):
        print("store path %s not found" % args.store_path, file=sys.stderr)
        return 2
    text = render(args.datastore, args.store_path)
    if args.stdout:
        sys.stdout.write(text)
        return 0
    fd, tmp = tempfile.mkstemp(dir=args.textfile_dir, prefix=".pbs_backup.", suffix=".tmp")
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, os.path.join(args.textfile_dir, "pbs_backup.prom"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
