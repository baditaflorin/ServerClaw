#!/usr/bin/env python3
"""tier0-controller, SHADOW MODE ONLY.

Decides, from independent vantage points, whether the primary site (0docker) is down, keeps a small state machine and exports metrics.
It performs NO action. When its rule says "fail over" or "fail back" it records the exact command a person or agent runs ("WOULD RUN ...").
Automatic mode does not exist on purpose: it is added only after the rule has run clean against reality and the failover chain has been rehearsed
three times in a row from the runner.

The rule (frozen; the same inputs always give the same decision):
  * a vantage point is UP if any probe from it succeeded, DOWN if every probe failed, UNKNOWN if the vantage point itself could not be used
    (for example the ssh hop failed). UNKNOWN never counts as DOWN.
  * a tick is UP if any vantage is UP, DOWN only if ALL vantages are DOWN, otherwise UNKNOWN (counters hold, nothing is decided).
  * NORMAL -> SUSPECT on the first DOWN tick; SUSPECT -> PRIMARY_DOWN after DOWN_TICKS consecutive DOWN ticks (the failover decision, once);
    an UP tick while SUSPECT returns to NORMAL.
  * PRIMARY_DOWN -> RECOVERING on the first UP tick; RECOVERING -> NORMAL after UP_TICKS consecutive UP ticks (the failback decision, once);
    a DOWN tick while RECOVERING returns to PRIMARY_DOWN without a second failover decision (the standby is still the active site).
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict

PRIMARY = os.environ.get("T0C_PRIMARY", "203.0.113.2")
PORTS = [int(p) for p in os.environ.get("T0C_PORTS", "22,443").split(",")]
DOWN_TICKS = int(os.environ.get("T0C_DOWN_TICKS", "5"))
UP_TICKS = int(os.environ.get("T0C_UP_TICKS", "30"))
STATE_DIR = os.environ.get("T0C_STATE_DIR", "/var/lib/tier0-controller")
PROM = os.environ.get("T0C_PROM", "/var/lib/prometheus/node-exporter/tier0_controller.prom")
# MEASUREMENT ONLY (never part of the decision rule above): do the apps answer while the host does? Collected during the shadow period so "host up, apps dead" can be judged on data.
APP_TARGETS = [t for t in os.environ.get("T0C_APP_TARGETS", "a11y-quick.0crawl.com,cors-scanner.0crawl.com,apikey-service.0exec.com").split(",") if t]
APP_PROM = os.environ.get("T0C_APP_PROM", PROM.replace("tier0_controller.prom", "tier0_controller_app.prom"))
REMOTE_VANTAGE = os.environ.get("T0C_REMOTE_VANTAGE", "0mcp_docker_build")  # ssh alias of the runner (t0runner) on the other site
STATES = ("NORMAL", "SUSPECT", "PRIMARY_DOWN", "RECOVERING")


@dataclass
class State:
    state: str = "NORMAL"
    down_ticks: int = 0
    up_ticks: int = 0
    since: float = field(default_factory=time.time)


def classify(vantages: dict[str, str]) -> str:
    """vantages: name -> UP|DOWN|UNKNOWN. Returns the tick class UP|DOWN|UNKNOWN."""
    values = list(vantages.values())
    if any(v == "UP" for v in values):
        return "UP"
    if values and all(v == "DOWN" for v in values):
        return "DOWN"
    return "UNKNOWN"


def step(s: State, tick: str, now: float, down_ticks: int = DOWN_TICKS, up_ticks: int = UP_TICKS) -> tuple[State, list[str]]:
    """Pure transition function. Returns the new state and the decisions taken on this tick."""
    n = State(s.state, s.down_ticks, s.up_ticks, s.since)
    events: list[str] = []
    if tick == "UNKNOWN":
        return n, events  # nothing decided, counters hold
    if tick == "DOWN":
        n.up_ticks = 0
        n.down_ticks += 1
        if n.state == "NORMAL":
            n.state, n.since = "SUSPECT", now
        if n.state == "SUSPECT" and n.down_ticks >= down_ticks:
            n.state, n.since = "PRIMARY_DOWN", now
            events.append("FAILOVER")
        elif n.state == "RECOVERING":
            n.state, n.since = "PRIMARY_DOWN", now  # still the standby's turn: no second failover decision
    else:  # UP
        n.down_ticks = 0
        if n.state == "SUSPECT":
            n.state, n.up_ticks, n.since = "NORMAL", 0, now
        elif n.state == "PRIMARY_DOWN":
            n.state, n.up_ticks, n.since = "RECOVERING", 1, now
        elif n.state == "RECOVERING":
            n.up_ticks += 1
            if n.up_ticks >= up_ticks:
                n.state, n.up_ticks, n.since = "NORMAL", 0, now
                events.append("FAILBACK")
        else:
            n.up_ticks = 0
    return n, events


# ---- probes (the only impure part) -----------------------------------------------------------------------------------
def tcp_ok(host: str, port: int, timeout: float = 5.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def vantage_local() -> str:
    return "UP" if any(tcp_ok(PRIMARY, p) for p in PORTS) else "DOWN"


def vantage_remote() -> str:
    """Probe from the other site through the runner's restricted ssh. ssh failure = UNKNOWN, never DOWN."""
    probe = " ".join(f"timeout 5 bash -c '</dev/tcp/{PRIMARY}/{p}' 2>/dev/null && echo up:{p} || echo down:{p};" for p in PORTS)
    try:
        r = subprocess.run(["runuser", "-u", "t0runner", "--", "env", "HOME=/var/lib/t0runner", "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", REMOTE_VANTAGE, probe],
                           capture_output=True, text=True, timeout=45)
    except (subprocess.TimeoutExpired, OSError):
        return "UNKNOWN"
    if r.returncode != 0:
        return "UNKNOWN"
    out = r.stdout.split()
    if not out:
        return "UNKNOWN"
    return "UP" if any(o.startswith("up:") for o in out) else "DOWN"


def app_probe(host: str, timeout: float = 8.0) -> int:
    """1 if https://<host>/health answers like a live service (2xx/3xx, or 401/403 from the auth gate), else 0. Pure measurement."""
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://{host}/health", headers={"User-Agent": "tier0-controller-probe"}), timeout=timeout) as r:
            return 1 if r.status < 400 else 0
    except urllib.error.HTTPError as e:
        return 1 if e.code in (401, 403) else 0
    except Exception:
        return 0


def write_app_metrics(tick: str, now: float, targets: list[str] | None = None, probe=app_probe) -> dict[str, int]:
    """Writes APP_PROM. host_up_apps_down is 1 when the host-level tick says UP but EVERY app target fails (the blind spot of the TCP rule). Never raises."""
    results: dict[str, int] = {}
    try:
        results = {t: probe(t) for t in (APP_TARGETS if targets is None else targets)}
        apps_down = 1 if (tick == "UP" and results and not any(results.values())) else 0
        out = ["# TYPE tier0_controller_app_probe_ok gauge"] + [f'tier0_controller_app_probe_ok{{target="{t}"}} {v}' for t, v in sorted(results.items())]
        out += ["# TYPE tier0_controller_host_up_apps_down gauge", f"tier0_controller_host_up_apps_down {apps_down}",
                "# TYPE tier0_controller_app_probe_last_run_timestamp_seconds gauge", f"tier0_controller_app_probe_last_run_timestamp_seconds {int(now)}"]
        tmp = APP_PROM + ".tmp"
        open(tmp, "w").write("\n".join(out) + "\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, APP_PROM)
    except Exception:
        pass
    return results


# ---- state + metrics -------------------------------------------------------------------------------------------------
def load() -> State:
    try:
        d = json.load(open(os.path.join(STATE_DIR, "state.json")))
        return State(d["state"], d["down_ticks"], d["up_ticks"], d["since"])
    except (OSError, ValueError, KeyError):
        return State()


def save(s: State) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = os.path.join(STATE_DIR, "state.json.tmp")
    json.dump(asdict(s), open(tmp, "w"))
    os.replace(tmp, os.path.join(STATE_DIR, "state.json"))


def history(line: dict) -> None:
    p = os.path.join(STATE_DIR, "history.jsonl")
    with open(p, "a") as f:
        f.write(json.dumps(line) + "\n")
    try:  # keep the last 5000 lines
        lines = open(p).read().splitlines()
        if len(lines) > 6000:
            open(p, "w").write("\n".join(lines[-5000:]) + "\n")
    except OSError:
        pass


def write_metrics(s: State, vantages: dict[str, str], tick: str, now: float) -> None:
    code = {"UP": 1, "DOWN": 0, "UNKNOWN": -1}
    out = ["# TYPE tier0_controller_last_run_timestamp_seconds gauge", f"tier0_controller_last_run_timestamp_seconds {int(now)}",
           "# TYPE tier0_controller_state gauge"]
    out += [f'tier0_controller_state{{state="{x}"}} {1 if s.state == x else 0}' for x in STATES]
    out += ["# TYPE tier0_controller_vantage_status gauge"]
    out += [f'tier0_controller_vantage_status{{vantage="{k}"}} {code[v]}' for k, v in sorted(vantages.items())]
    out += ["# TYPE tier0_controller_tick_status gauge", f"tier0_controller_tick_status {code[tick]}",
            "# TYPE tier0_controller_consecutive_down_ticks gauge", f"tier0_controller_consecutive_down_ticks {s.down_ticks}",
            "# TYPE tier0_controller_consecutive_up_ticks gauge", f"tier0_controller_consecutive_up_ticks {s.up_ticks}",
            "# TYPE tier0_controller_would_failover gauge", f"tier0_controller_would_failover {1 if s.state in ('PRIMARY_DOWN', 'RECOVERING') else 0}",
            '# TYPE tier0_controller_mode gauge', 'tier0_controller_mode{mode="shadow"} 1']
    tmp = PROM + ".tmp"
    open(tmp, "w").write("\n".join(out) + "\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, PROM)


def main() -> int:
    now = time.time()
    if os.path.exists(os.path.join(STATE_DIR, "PAUSE")):
        print("PAUSE file present: not evaluating")
        return 0
    vantages = {"vm704": vantage_local(), "0mcp": vantage_remote()}
    tick = classify(vantages)
    prev = load()
    new, events = step(prev, tick, now)
    save(new)
    write_metrics(new, vantages, tick, now)
    write_app_metrics(tick, now)
    history({"ts": int(now), "vantages": vantages, "tick": tick, "state": new.state, "events": events})
    msg = f"tick={tick} vantages={vantages} state={prev.state}->{new.state} down={new.down_ticks} up={new.up_ticks}"
    print(msg)
    for e in events:
        if e == "FAILOVER":
            print(f"DECISION FAILOVER (shadow, nothing executed): WOULD RUN: tier0-run tier0-failover.sh --promote ; then the DNS stage ({PRIMARY} unreachable from {len(vantages)} vantage points for {DOWN_TICKS} ticks)")
        else:
            print(f"DECISION FAILBACK (shadow, nothing executed): WOULD RUN: DNS back from git, tier0-run tier0-failover.sh teardown stages ({PRIMARY} answered for {UP_TICKS} consecutive ticks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
