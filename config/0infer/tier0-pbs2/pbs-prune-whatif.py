#!/usr/bin/env python3
"""Read-only "what would a retention change free?" for a Proxmox Backup Server datastore (run as root on the PBS VM, idle I/O priority).

For every snapshot it reads the .fidx/.didx indexes and records which snapshots reference each chunk (one bit per snapshot, so a datastore of ~10^6 chunks and ~10^2 snapshots
needs ~200 MB). The bytes a deletion frees are the chunks that ONLY the deleted snapshots reference (a chunk shared with a surviving snapshot, in any group or namespace, stays).
Garbage collection reclaims them after its atime grace (24 h) on the next GC run.

  pbs-prune-whatif.py                              per-group table: snapshots, bytes only the OLDEST / the NEWEST snapshot holds, bytes only the whole group holds
  pbs-prune-whatif.py keep-last=2:ns/0docker/vm/100,ns/0database/vm/100  drop=ns/0own/vm/630,ns/0own/vm/640 ...
        scenarios: `keep-last=N:<group>[,<group>...]` keeps the N newest snapshots of those groups and deletes the rest;
                   `drop=<group>[,<group>...]` deletes every snapshot of those groups; `keep-last=N:*` applies to every group.
A group is written as its datastore path relative to the root: `vm/100`, `ns/0docker/vm/100`, `ns/0docker/host/ct108-live`.
Never modifies the datastore. Environment: PBS_STORE (default /srv/pbs-datastore)."""
import collections
import os
import sys
import time

ROOT = os.environ.get("PBS_STORE", "/srv/pbs-datastore")
CH = ROOT + "/.chunks"


def digests(path):
    with open(path, "rb") as f:
        f.read(4096)
        rest = f.read()
    if path.endswith(".fidx"):
        return (rest[i:i + 32] for i in range(0, len(rest) - 31, 32))
    return (rest[i + 8:i + 40] for i in range(0, len(rest) - 39, 40))


def groups_under(base):
    """Yield (group path relative to ROOT, absolute group dir) for every vm/ct/host group below base and below its namespaces."""
    for kind in ("vm", "ct", "host"):
        kd = f"{base}/{kind}"
        if os.path.isdir(kd):
            for gid in sorted(os.listdir(kd)):
                yield os.path.relpath(f"{kd}/{gid}", ROOT), f"{kd}/{gid}"
    nd = f"{base}/ns"
    if os.path.isdir(nd):
        for n in sorted(os.listdir(nd)):
            yield from groups_under(f"{nd}/{n}")


t0 = time.time()
keys = []                                   # snapshot index -> (group, snapshot name)
order = collections.defaultdict(list)       # group -> [snapshot index, oldest first]
holders = {}                                # chunk digest (bytes) -> bitmask of the snapshots that reference it
for grel, gdir in groups_under(ROOT):
    for sn in sorted(x for x in os.listdir(gdir) if x[:2] == "20" and os.path.isdir(f"{gdir}/{x}")):
        bit = 1 << len(keys)
        order[grel].append(len(keys))
        keys.append((grel, sn))
        seen = set()
        for fn in os.listdir(f"{gdir}/{sn}"):
            if fn.endswith((".fidx", ".didx")):
                try:
                    seen.update(digests(f"{gdir}/{sn}/{fn}"))
                except OSError:
                    pass
        for d in seen:
            holders[d] = holders.get(d, 0) | bit
        del seen

size = {}
disk = 0
for d1 in os.listdir(CH):
    p1 = f"{CH}/{d1}"
    if os.path.isdir(p1):
        for fn in os.listdir(p1):
            try:
                st = os.stat(f"{p1}/{fn}")
                size[bytes.fromhex(fn)] = st.st_size
                disk += st.st_blocks * 512
            except (OSError, ValueError):
                continue


def mask_of(indices):
    m = 0
    for i in indices:
        m |= 1 << i
    return m


def freed_by(indices):
    """Bytes held ONLY by the given snapshots (a chunk any other snapshot references stays)."""
    dm = mask_of(indices)
    return sum(size.get(d, 0) for d, m in holders.items() if m & dm and not (m & ~dm))


def gb(n):
    return f"{n / 1e9:8.1f}"


def groups_arg(who):
    out = list(order) if who == "*" else who.split(",")
    for g in out:
        if g not in order:
            sys.exit(f"unknown group {g!r}; known: {sorted(order)}")
    return out


print(f"PBS what-if {time.strftime('%F %T', time.gmtime())}Z store={ROOT} scan {time.time() - t0:.0f}s: {len(keys)} snapshots in {len(order)} groups, {len(size)} chunk files, "
      f"on-disk {disk / 1e9:.0f} GB, referenced {sum(size.get(d, 0) for d in holders) / 1e9:.0f} GB")
if len(sys.argv) == 1:
    print(f"{'group':<38}{'snaps':>6}{'oldest holds GB':>17}{'newest holds GB':>17}{'whole group GB':>16}   (bytes ONLY that snapshot / that whole group holds)")
    for g in sorted(order):
        idx = order[g]
        print(f"{g:<38}{len(idx):>6}{gb(freed_by([idx[0]])):>17}{gb(freed_by([idx[-1]])):>17}{gb(freed_by(idx)):>16}")
    print("\nsnapshots per group, oldest first (MM-DDTHH):")
    for g in sorted(order):
        print(f"  {g}: " + " ".join(keys[i][1][5:13] for i in order[g]))
else:
    delete = []
    labels = []
    for a in sys.argv[1:]:
        if a.startswith("keep-last="):
            n, who = a[len("keep-last="):].split(":", 1)
            for g in groups_arg(who):
                delete += order[g][:-int(n)]
            labels.append(a)
        elif a.startswith("drop="):
            for g in groups_arg(a[len("drop="):]):
                delete += order[g]
            labels.append(a)
        else:
            sys.exit(f"unknown scenario {a!r}")
    delete = sorted(set(delete))
    per_group = collections.defaultdict(list)
    for i in delete:
        per_group[keys[i][0]].append(i)
    print("scenario: " + "  ".join(labels))
    print(f"deletes {len(delete)} snapshots in {len(per_group)} groups; frees {gb(freed_by(delete)).strip()} GB once GC has run (chunks shared with surviving snapshots stay)")
    for g, idx in sorted(per_group.items()):
        print(f"  {g:<38} deletes {len(idx)} of {len(order[g])} snapshots, frees {gb(freed_by(idx)).strip()} GB on its own")
