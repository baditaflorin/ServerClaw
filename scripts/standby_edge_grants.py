#!/usr/bin/env python3
"""Tailnet grants for the standby gateway's backends: the exact ports the 0mcp edge VM110 cannot reach today (output for config/tailscale/policy.hujson).

The standby gateway keeps every production pool's surviving servers, which are tailnet addresses (the infer runtime, three more pool runtimes). The edge's tailnet access is granted
by exact port (2026-10-16 list); the pools program has added about a hundred ports since, and the daily rehearsal's all-names probe (fleet-state standby-probe.sh) found 92 of 374
pool-served names failing with 504. This tool turns a measured reachability list into the grants and policy tests that close exactly that gap, nothing wider:

  standby_edge_grants.py --reach reach.txt [--src 100.84.241.55/32] [--emit grants|tests|both] [--verify]
  reach.txt   lines `OPEN|CLOSED <tailnet ip> <port>`: a TCP connect from the edge VM to every backend ip:port of the production pools (CLOSED = no grant, or nothing listening)
  --dst       <ip>[=<name>] limits/renames: only the destinations given are emitted (default: every ip that has a CLOSED port)

Only CLOSED pairs become grants, one grant per destination host (a /32, never a tag, never a range wider than the consecutive ports that are all needed), explicit `tcp:N` / `tcp:A-B`.
Each grant gets tests (accept: every port of it from the edge address) so the unattended reconciler (scripts/tailscale_policy_reconcile.py) accepts the change by its own guard, which
--verify runs on the output: only src/dst/ip keys, single /32 hosts, explicit ports, no management port, every (src, dst, port) covered by an added test.
A CLOSED port nothing listens on is a stale pool server, not a grant: check the destination first (`ss -ltn`), as the all-names probe's follow-up does; this tool cannot tell."""
import argparse
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_SRC = "100.84.241.55/32"        # edge-standby-0mcp (VM110), joined as tag:pool-runtime: its outbound access is granted by address


def compress(ports):
    """Sorted ports -> ['tcp:8081-8082', 'tcp:8107', ...]: a range only where every port in it is needed."""
    out, run = [], []
    for p in sorted(set(ports)):
        if run and p == run[-1] + 1:
            run.append(p)
        else:
            if run:
                out.append(run)
            run = [p]
    if run:
        out.append(run)
    return ["tcp:%d" % r[0] if len(r) == 1 else "tcp:%d-%d" % (r[0], r[-1]) for r in out]


def closed_by_destination(lines):
    by = defaultdict(set)
    for line in lines:
        parts = line.split()
        if len(parts) == 3 and parts[0] == "CLOSED" and parts[2].isdigit():
            by[parts[1]].add(int(parts[2]))
    return dict(by)


def build(closed, src):
    grants, tests = [], []
    host = src[:-3] if src.endswith("/32") else src
    for ip in sorted(closed):
        ports = sorted(closed[ip])
        grants.append({"src": [src], "dst": [ip + "/32"], "ip": compress(ports)})
        tests.append({"src": host, "accept": ["%s:%d" % (ip, p) for p in ports], "proto": "tcp"})
    return grants, tests


def hujson(items, indent="\t\t"):
    """Pretty HuJSON for a list of objects the way Tailscale stores the policy: one key per line, trailing commas, and consecutive single-line values aligned under each other
    (`"src": ...` / `"dst": ...` / `"ip":  ...`): the live policy is re-formatted that way on save, and a git file that is not already in that form shows up as a whitespace-only
    difference that the unattended reconciler would try to apply again and again (found 2026-10-18). Tailscale expands a list when its one-line text is long: seen on the live policy, a list of two-digit-octet endpoints
    of 84 characters (four `100.84.14.14:80xx`, 68 characters of endpoints) was stored expanded while the longest single-line list is 78, so the rule is the old
    sum of lengths over 70 OR a one-line JSON text over 80 (2026-10-21, grants of #533: the first one-line version of that test kept FleetTailnetPolicyOutOfSync
    firing and the reconciler re-applying it)."""
    out = []
    for g in items:
        out.append(indent + "{")
        entries = []                                              # (key, multi-line?, rendered value lines)
        for k, v in g.items():
            if isinstance(v, list) and len(v) > 1 and all(isinstance(x, str) for x in v) and (sum(len(x) for x in v) > 70 or len(json.dumps(v)) > 80):
                entries.append((k, True, [indent + "\t\t" + json.dumps(x) + "," for x in v]))
            else:
                entries.append((k, False, [json.dumps(v)]))
        i = 0
        while i < len(entries):
            if entries[i][1]:
                k, _, lines = entries[i]
                out.append(indent + "\t" + json.dumps(k) + ": [")
                out.extend(lines)
                out.append(indent + "\t],")
                i += 1
                continue
            j = i
            while j < len(entries) and not entries[j][1]:
                j += 1
            width = max(len(json.dumps(k)) for k, _, _ in entries[i:j])
            for k, _, lines in entries[i:j]:
                out.append(indent + "\t" + json.dumps(k) + ":" + " " * (width - len(json.dumps(k)) + 1) + lines[0] + ",")
            i = j
        out.append(indent + "},")
    return "\n".join(out)


def verify(grants, tests):
    spec = importlib.util.spec_from_file_location("tailscale_policy_reconcile", HERE / "tailscale_policy_reconcile.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["tailscale_policy_reconcile"] = mod
    spec.loader.exec_module(mod)
    errors = []
    for g in grants:
        errors += mod.grant_errors(g, {})
        errors += mod.coverage_errors(g, tests)
    return errors


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--reach", required=True)
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--emit", choices=("grants", "tests", "both"), default="both")
    ap.add_argument("--dst", action="append", default=[])
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args(argv)
    closed = closed_by_destination(open(a.reach).read().splitlines())
    if a.dst:
        closed = {ip: p for ip, p in closed.items() if ip in {d.split("=")[0] for d in a.dst}}
    if not closed:
        print("nothing is CLOSED: no grant is missing", file=sys.stderr)
        return 10
    grants, tests = build(closed, a.src)
    if a.verify:
        errs = verify(grants, tests)
        if errs:
            print("\n".join("GUARD: " + e for e in errs), file=sys.stderr)
            return 3
    if a.emit in ("grants", "both"):
        print(hujson(grants))
    if a.emit in ("tests", "both"):
        if a.emit == "both":
            print("\n// ---- tests ----")
        print(hujson(tests))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
