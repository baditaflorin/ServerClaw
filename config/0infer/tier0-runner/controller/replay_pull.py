#!/usr/bin/env python3
"""Pull the recorded reachability signal for a controller REPLAY. Run on the monitoring VM (Prometheus on localhost:9090); writes JSON for replay.py.
  replay_pull.py OUT.json [DAYS]      default 15 days = the Prometheus retention
Signal: min/max across the independent public-edge probes (probe_success{job="public-edge-critical"}), one point per minute."""
import json, sys, time, urllib.parse, urllib.request

P = "http://localhost:9090/api/v1/query_range"
days = int(sys.argv[2]) if len(sys.argv) > 2 else 15
now = int(time.time()); start = now - days * 86400
out = {}
for name, q in (("edge_min", 'min(probe_success{job="public-edge-critical"})'), ("edge_max", 'max(probe_success{job="public-edge-critical"})')):
    pts, t = [], start
    while t < now:
        e = min(t + 10000 * 60, now)
        u = P + "?" + urllib.parse.urlencode({"query": q, "start": t, "end": e, "step": 60})
        for s in json.load(urllib.request.urlopen(u, timeout=120))["data"]["result"]:
            pts += [(int(float(a)), int(float(b))) for a, b in s["values"]]
        t = e
    out[name] = sorted(set(pts))
json.dump(out, open(sys.argv[1], "w"))
print({k: len(v) for k, v in out.items()})
