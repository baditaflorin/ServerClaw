#!/usr/bin/env python3
"""Last event time per hypervisor in OpenObserve host_logs, as a node-exporter textfile (added 2026-11-01).

Runs on VM 630 (OpenObserve itself) every 2 minutes. A hypervisor's journal shipper can die, hang or lose its network without any
other signal, and its logs are what we read after an incident. A host with no event in the 6 h window is written with timestamp 0
(so the alert fires), but when the query itself fails only openobserve_log_freshness_up 0 is written: a probe that reads nothing
must say so instead of reporting every host silent. The credential is read from the local secret file and never printed.
"""
from __future__ import annotations

import base64
import glob
import json
import os
import re
import sys
import time
import urllib.request

HYPERVISORS = ["0pipe", "0mcp", "0infer", "0docker-hypervisor", "0own"]  # host label in host_logs; add a host here when it gets a shipper
STREAM = "host_logs"
WINDOW_SECONDS = 6 * 3600
BASE = os.environ.get("OPENOBSERVE_URL", "http://127.0.0.1:5080")
SECRETS = "/opt/openobserve/secrets/openobserve_root_password"
OUT = os.environ.get("TEXTFILE", "/var/lib/prometheus/node-exporter/textfile/openobserve-log-freshness.prom")


def root_user() -> str:
    for path in sorted(glob.glob("/opt/openobserve/compose.y*") + glob.glob("/opt/openobserve/.env")):
        m = re.search(r"ZO_ROOT_USER_EMAIL[=:]\s*['\"]?([^\s'\"]+)", open(path).read())
        if m:
            return m.group(1)
    raise RuntimeError("root user not found")


def last_events() -> dict[str, int]:
    token = base64.b64encode(f"{root_user()}:{open(SECRETS).read().strip()}".encode()).decode()
    now = int(time.time())
    hosts = ",".join("'%s'" % h for h in HYPERVISORS)
    body = {"query": {"sql": f"select host, max(_timestamp) as m from {STREAM} where host in ({hosts}) group by host",
                      "start_time": (now - WINDOW_SECONDS) * 1_000_000, "end_time": now * 1_000_000}}
    req = urllib.request.Request(f"{BASE}/api/default/_search", data=json.dumps(body).encode(),
                                 headers={"Authorization": "Basic " + token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        hits = json.load(r)["hits"]
    return {h["host"]: int(h["m"]) // 1_000_000 for h in hits}


def main() -> int:
    lines = ["# TYPE openobserve_log_freshness_up gauge", "# TYPE openobserve_log_last_event_timestamp_seconds gauge"]
    try:
        seen = last_events()
        lines.append("openobserve_log_freshness_up 1")
        for h in HYPERVISORS:
            lines.append(f'openobserve_log_last_event_timestamp_seconds{{stream="{STREAM}",host="{h}",role="hypervisor"}} {seen.get(h, 0)}')
        rc = 0
    except Exception as e:  # noqa: BLE001 - any failure means the probe is blind
        print("log freshness probe failed:", type(e).__name__, file=sys.stderr)
        lines.append("openobserve_log_freshness_up 0")
        rc = 1
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, OUT)
    return rc


if __name__ == "__main__":
    sys.exit(main())
