#!/usr/bin/env python3
"""Full-cycle SIMULATION of automatic failover on throwaway objects: the same executor code as live, injected outage and recovery.

  tier0_sim.py clean     inject the outage -> executor (sim mode: the real stages in their REHEARSE flavour, DNS on the throwaway name t0-sim.example.net)
                         -> injected recovery (the executor must do nothing on its own) -> the exact inverse operations (what a person/agent runs for the failback)
                         -> everything removed again. Daily.
  tier0_sim.py abort     same start, but the primary "answers again" right after the vault stage: the executor must stop at the next fence, never touch DNS, and the
                         simulation then removes the vault rehearsal it left. Weekly.

What it proves that the unit tests cannot: the real stage scripts, the real runner ssh, the real DNS API and the real authoritative servers behave as the executor assumes,
and nothing is left behind on the 0mcp hosts. What it does not prove: a real outage (see the README ladder). Needs root (token from the local vault standby).
Exports tier0_sim_* metrics and appends to /var/lib/tier0-runner/sim-history.jsonl (the promotion gate counts consecutive green days from it).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tier0_executor as ex  # noqa: E402

REC = ["python3", "/opt/tier0-runner/fleet-state/scripts/tier0/dns-reconcile.py"]
ZONE, NAME = "example.net", "t0-sim"
FQDN = f"{NAME}.{ZONE}"
PRIMARY_IP = "203.0.113.2"
HIST = "/var/lib/tier0-runner/sim-history.jsonl"
DRILL_DIR = "/var/lib/tier0-dns/drill"


class SimEnv(ex.RealEnv):
    """The real environment with the world injected: the controller's decision and the probes come from the simulation, everything else is real."""
    DIR = "/var/lib/tier0-sim"
    PROM = "/var/lib/prometheus/node-exporter/tier0_sim.prom"

    def __init__(self, cfg):
        super().__init__(cfg)
        self.primary_down = True
        self.ctl_state = "PRIMARY_DOWN"
        self.episode = time.time()
        self.hooks = {}
        self.timings = {}

    def controller(self): return {"state": self.ctl_state, "since": self.episode}
    def probe(self):
        v = "DOWN" if self.primary_down else "UP"
        return {"vm704": v, "0mcp": v}
    def gate(self): return []

    def stage(self, name, mode):
        t = time.time(); res = super().stage(name, mode); self.timings[name] = round(time.time() - t, 1)
        if name in self.hooks: self.hooks[name](self)
        return res

    def dns_failover(self, mode):
        t = time.time(); res = super().dns_failover(mode); self.timings["dns"] = round(time.time() - t, 1); return res

    def verify(self, mode):
        t = time.time(); res = super().verify(mode); self.timings["verify"] = round(time.time() - t, 1); return res


def token():
    return subprocess.run(["/opt/tier0-runner/bin/tier0-secret", "hcloud_token_fleet_core"], capture_output=True, text=True).stdout.strip()


def reconcile(*args):
    return subprocess.run(REC + list(args), input=token() + "\n", capture_output=True, text=True, timeout=600)


def authoritative(name=FQDN):
    ns = subprocess.run(["dig", "+short", "NS", ZONE], capture_output=True, text=True).stdout.split()[0]
    return subprocess.run(["dig", "+short", "+time=3", "+tries=2", "@" + ns, name, "A"], capture_output=True, text=True).stdout.strip().split("\n")[0]


def wait_for(want, tries=40):
    for _ in range(tries):
        if authoritative() == want: return True
        time.sleep(2)
    return False


def runner_ssh(host, cmd):
    return subprocess.run(["runuser", "-u", "t0runner", "--", "env", "HOME=/var/lib/t0runner", "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", host, cmd],
                          capture_output=True, text=True, timeout=120)


def leftovers():
    out = []
    if "rehearsal" in runner_ssh("0mcp_docker_build", "sudo docker ps -a --format '{{.Names}}'").stdout: out.append("rehearsal containers on 0mcp_docker_build")
    if runner_ssh("0mcp_nginx", "sudo test -d /etc/nginx/t0g -o -d /etc/nginx/t0-rehearsal").returncode == 0: out.append("edge config on 0mcp_nginx")
    if runner_ssh("0mcp_staging_runtime", "test -f /var/lib/tier0-slice-restored").returncode == 0: out.append("slice files on 0mcp_staging_runtime")
    return out


def chain(script, *args):
    return subprocess.run(["/usr/local/bin/tier0-run", script, *args], capture_output=True, text=True, timeout=900).returncode


def main() -> int:
    variant = sys.argv[1] if len(sys.argv) > 1 else "clean"
    assert variant in ("clean", "abort")
    t0 = time.time(); results, problems = [], []

    def check(label, cond, detail=""):
        results.append((label, bool(cond)))
        print(f"  {'ok  ' if cond else 'FAIL'} {label}" + (f"  [{detail}]" if detail and not cond else ""))
        if not cond: problems.append(label)

    cfg = ex.Cfg(dns_attempts=3, dns_backoff_s=20)
    env = SimEnv(cfg)
    for f in (f"{env.DIR}/current.json",):
        if os.path.exists(f): os.remove(f)
    print(f"tier0 sim [{variant}] at {time.strftime('%FT%TZ', time.gmtime())}: throwaway name {FQDN}")
    revert = ""
    try:
        reconcile("set", "--zone", ZONE, "--name", NAME, "--type", "A", "--value", PRIMARY_IP, "--ttl", "60", "--apply")
        check("throwaway record created on the primary address", wait_for(PRIMARY_IP))
        if variant == "abort":
            env.hooks["vault"] = lambda e: setattr(e, "primary_down", False)         # the primary 'answers again' right after the vault stage

        run = ex.tick(env, cfg, "sim")
        revert = run.revert_file
        if variant == "clean":
            check("executor reached FAILED_OVER", run.phase == "FAILED_OVER", f"phase {run.phase}: {run.note}")
            check("every step ok", all(run.steps.get(s, {}).get("status") == "ok" for s in ex.STEP_ORDER), json.dumps({k: v["status"] for k, v in run.steps.items()}))
            check("only the throwaway name was moved to the standby edge", wait_for(cfg.edge_ip, tries=15))     # the authoritative servers show a new record a few seconds apart: poll, never one sample (flaked 2026-10-18)
            n_events = sum(1 for _ in open(f"{env.DIR}/log/events.jsonl"))
            env.primary_down, env.ctl_state = True, "NORMAL"       # injected recovery
            run2 = ex.tick(env, cfg, "sim")
            check("on recovery the executor does nothing on its own (failback is manual)", "failback is MANUAL" in run2.note and
                  not any(e.get("event") == "step" for e in [json.loads(l) for l in list(open(f"{env.DIR}/log/events.jsonl"))[n_events:]]))
            # the manual failback, exactly as a person/agent would run it: teardown of the kept parts, then DNS from the revert file
            check("vault rehearsal torn down", chain("tier0-vault-promote.sh", "--teardown-rehearsal") == 0)
            check("gateway rehearsal torn down", chain("tier0-gateway-promote.sh", "--teardown-rehearsal") == 0)
            fb = subprocess.run(["/usr/local/sbin/tier0-dns", "failback", "--file", revert, "--apply"], capture_output=True, text=True, timeout=900)
            check("exact DNS failback from the revert file", fb.returncode == 0 and wait_for(PRIMARY_IP), fb.stdout[-200:])
            again = subprocess.run(["/usr/local/sbin/tier0-dns", "failback", "--file", revert], capture_output=True, text=True, timeout=900)
            check("the failback is idempotent", "0 to restore" in again.stdout, again.stdout[-120:])
            run.phase = "IDLE"; env.save(run)                      # what `tier0-executor ack` does
        else:
            check("executor aborted because the primary answered again", run.phase == "ABORTED_PRIMARY_BACK", f"phase {run.phase}: {run.note}")
            check("only the vault stage ran", run.steps.get("vault", {}).get("status") == "ok" and "slice" not in {k for k, v in run.steps.items() if v["status"] == "ok"})
            check("DNS was never touched", authoritative() == PRIMARY_IP and not run.revert_file)
            check("vault rehearsal torn down by the simulation", chain("tier0-vault-promote.sh", "--teardown-rehearsal") == 0)
    except Exception as e:   # the simulation itself must never leave debris behind
        problems.append(f"exception {type(e).__name__}: {e}"); print("EXCEPTION", type(e).__name__, e)
    finally:
        chain("tier0-vault-promote.sh", "--teardown-rehearsal"); chain("tier0-gateway-promote.sh", "--teardown-rehearsal")
        reconcile("unset", "--zone", ZONE, "--name", NAME, "--type", "A", "--apply")
        if revert and os.path.exists(revert):
            os.makedirs(DRILL_DIR, mode=0o700, exist_ok=True); os.replace(revert, os.path.join(DRILL_DIR, os.path.basename(revert)))   # never the 'newest revert file' of a REAL failback
        gone = False
        for _ in range(30):
            if not authoritative(): gone = True; break
            time.sleep(2)
        check("throwaway record deleted", gone)
        left = leftovers()
        check("nothing left on the 0mcp hosts", not left, ", ".join(left))
    rc = 1 if problems else 0
    dur = int(time.time() - t0)
    lines = ["# TYPE tier0_sim_last_run_timestamp_seconds gauge", f"tier0_sim_last_run_timestamp_seconds{{variant=\"{variant}\"}} {int(time.time())}",
             f"tier0_sim_last_exit_code{{variant=\"{variant}\"}} {rc}", f"tier0_sim_last_duration_seconds{{variant=\"{variant}\"}} {dur}"]
    lines += [f'tier0_sim_step_seconds{{variant="{variant}",step="{k}"}} {v}' for k, v in sorted(env.timings.items())]
    if rc == 0: lines.append(f"tier0_sim_last_success_timestamp_seconds{{variant=\"{variant}\"}} {int(time.time())}")
    path = f"/var/lib/prometheus/node-exporter/tier0_sim_{variant}.prom"
    open(path + ".tmp", "w").write("\n".join(lines) + "\n"); os.chmod(path + ".tmp", 0o644); os.replace(path + ".tmp", path)
    os.makedirs(os.path.dirname(HIST), exist_ok=True)
    open(HIST, "a").write(json.dumps({"ts": int(time.time()), "rc": rc, "variant": variant, "seconds": dur, "steps": env.timings}) + "\n")
    print(f"tier0 sim [{variant}]: {'PASS' if rc == 0 else 'FAIL ' + '; '.join(problems)} in {dur} s; step seconds {env.timings}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
