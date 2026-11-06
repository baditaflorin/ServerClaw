#!/usr/bin/env python3
"""Replay RECORDED reachability through the controller's real state machine (tier0_controller.step), to answer: would the rule have decided correctly on a real outage,
how late, and would it ever have fired by mistake?

  replay.py SERIES.json [--down N] [--up M]

SERIES.json: {"edge_min": [[ts, 0|1], ...], "edge_max": [[ts, 0|1], ...]}, one point per minute, min/max across the independent probes (Prometheus `min/max(probe_success{...})`).
  strict    tick = DOWN only if EVERY probe failed (max == 0), UP if any succeeded: the controller's own rule (UP if any vantage is UP, DOWN only if all are DOWN)
  sensitive tick = DOWN if ANY probe failed (min == 0): an upper bound for false positives (one failing app counts as an outage)
Missing minutes are UNKNOWN (counters hold)."""
import importlib.util, json, pathlib, sys, time

spec = importlib.util.spec_from_file_location("c", pathlib.Path(__file__).with_name("tier0_controller.py"))
c = importlib.util.module_from_spec(spec); sys.modules["c"] = c; spec.loader.exec_module(c)


def ticks(series, mode):
    """One tick per recorded point; a gap of more than 90 s becomes UNKNOWN ticks (one per missing minute): the controller never decides on missing data."""
    pts = sorted(series["edge_max" if mode == "strict" else "edge_min"])
    prev = None
    for t, v in pts:
        if prev is not None and t - prev > 90:
            for k in range(1, (t - prev) // 60):
                yield prev + 60 * k, "UNKNOWN"
        yield t, ("UP" if v == 1 else "DOWN")
        prev = t


def run(series, mode, down, up):
    s, dec, down_runs, cur = c.State(), [], [], None
    for t, tick in ticks(series, mode):
        if tick == "DOWN":
            cur = cur or [t, t]; cur[1] = t
        elif tick == "UP" and cur:
            down_runs.append(tuple(cur)); cur = None
        s, ev = c.step(s, tick, float(t), down, up)
        for e in ev: dec.append((t, e))
    if cur: down_runs.append(tuple(cur))
    return dec, down_runs


def fmt(t): return time.strftime("%m-%d %H:%MZ", time.gmtime(t))


if __name__ == "__main__":
    series = json.load(open(sys.argv[1]))
    args = sys.argv[2:]
    for down, up in ((5, 30),) if "--down" not in args else ((int(args[args.index("--down") + 1]), int(args[args.index("--up") + 1])),):
        pass
    print(f"data: {fmt(min(t for t, _ in series['edge_max']))} .. {fmt(max(t for t, _ in series['edge_max']))}, {len(series['edge_max'])} points")
    for mode in ("strict", "sensitive"):
        for down, up in ((3, 15), (5, 30), (10, 30)):
            dec, runs = run(series, mode, down, up)
            fo = [t for t, e in dec if e == "FAILOVER"]; fb = [t for t, e in dec if e == "FAILBACK"]
            print(f"\n[{mode:9s}] rule: {down} DOWN ticks -> failover, {up} UP ticks -> failback   decisions: {len(fo)} failover, {len(fb)} failback;  down runs seen: {len(runs)}")
            for a, b in runs:
                dur = (b - a) // 60 + 1
                d = next((t for t in fo if a <= t <= b + 60), None)
                print(f"    down {fmt(a)} -> {fmt(b)} ({dur:3d} min): " + (f"FAILOVER decided {fmt(d)} ({(d - a) // 60} min after it began)" if d else "no decision (shorter than the rule)"))
            for t in fb: print(f"    FAILBACK decided {fmt(t)}")
