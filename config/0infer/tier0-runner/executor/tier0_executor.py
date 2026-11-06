#!/usr/bin/env python3
"""tier0-executor: the part that ACTS once the controller has decided that the primary site (0docker) is down.

Modes (file /etc/tier0-executor/mode, default `shadow`):
  shadow  records what it WOULD do for each controller decision; executes nothing
  sim     runs the real stages in their REHEARSE flavour (domainscope: its read-only --check, booting the standby VM is the daily rehearsal's job) and the DNS stage on a
          throwaway test name (the daily full-cycle simulation uses this)
  live    the real failover. Refuses unless the promotion gate holds (Env.gate()).

The run (order fixed, same code in every mode, only the effects differ):
  precheck -> vault -> slice -> gateway -> domainscope -> dns -> verify
Rules, each of them tested in tests/test_tier0_executor.py:
  * FENCE: before EVERY effectful step both vantage points must say DOWN. UP aborts at once, UNKNOWN is retried a few times and then aborts: never act on a doubt.
  * Single instance (flock) and resumable: progress is persisted after every step, a restart continues with the first unfinished step; a stage that answers "already
    promoted" (exit 4 with 'already') counts as done only if its postcondition holds.
  * Failure policy: vault and gateway are REQUIRED (abort, DNS untouched: a dead primary is better than a dead standby); slice and domainscope are OPTIONAL (degraded, the
    run goes on: one service's web tier must never hold back the DNS flip of the other ~430 names, so domainscope gets ONE attempt and a 10 minute budget); DNS is retried
    with back-off and is the point of no return. An abort before DNS leaves users unaffected.
  * No destructive automatic teardown in live mode: an abort leaves what was started running and says exactly what (alert), because a promoted vault may already hold writes.
  * APPROVAL (live mode only, Cfg.dns_approval): after the stages are up the run WAITS before the DNS step (phase AWAITING_DNS_APPROVAL, metric
    tier0_executor_awaiting_dns_approval) until a person or agent runs `tier0-executor approve`. Every tick re-checks the fence while it waits: if the primary comes
    back, the run aborts. sim and shadow never wait.
  * PAUSE file stops the run between steps. After DONE the executor does NOTHING automatic: failback is a deliberate act (vault handback is not scripted) -> `ack`.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Callable, Dict, List, Optional, Tuple

MODES = ("shadow", "sim", "live")
STEP_ORDER = ["precheck", "vault", "slice", "gateway", "domainscope", "dns", "verify"]
EFFECTFUL = {"vault", "slice", "gateway", "domainscope", "dns"}
OPTIONAL = {"slice", "domainscope"}     # a failed optional stage degrades the run (alert) but never blocks the DNS flip of the other ~430 names
STAGES_RUN = ("vault", "slice", "gateway", "domainscope")


@dataclass
class StepResult:
    rc: int
    tail: str = ""
    extra: str = ""          # e.g. the DNS revert file path


@dataclass
class Cfg:
    edge_ip: str = "203.0.113.1"
    sample_names: Tuple[str, ...] = ("a11y-quick.0crawl.com", "apikey-service.0exec.com", "fleet-secrets.0exec.com")
    dns_attempts: int = 10
    dns_backoff_s: int = 60
    stage_attempts: int = 2
    stage_attempts_by: Dict[str, int] = field(default_factory=lambda: {"domainscope": 1})    # an optional stage that failed once is reported, not retried: the DNS flip must not wait for it
    stage_timeout_s: int = 900
    stage_timeout_by: Dict[str, int] = field(default_factory=lambda: {"domainscope": 600})   # normal run ~215 s; a hang costs at most 10 minutes before the DNS flip, not 30
    unknown_retries: int = 3
    unknown_gap_s: int = 10
    lock_wait_s: int = 180
    dns_approval: bool = True          # live mode only: wait for `tier0-executor approve` before the DNS step
    verify_wait_s: int = 150          # DNS changes take seconds to show at the authoritative servers: verification POLLS, it never judges the first look


@dataclass
class Run:
    id: str = ""
    mode: str = "shadow"
    episode: float = 0.0
    phase: str = "IDLE"
    steps: Dict[str, dict] = field(default_factory=dict)
    revert_file: str = ""
    note: str = ""
    degraded: bool = False
    started: float = 0.0
    ended: float = 0.0


# ---- the only impure interface; RealEnv talks to the system, FakeEnv (tests) and SimEnv (daily simulation) script it -------------------
class Env:
    def now(self) -> float: raise NotImplementedError
    def sleep(self, s: float) -> None: raise NotImplementedError
    def controller(self) -> dict: raise NotImplementedError                     # {"state": NORMAL|SUSPECT|PRIMARY_DOWN|RECOVERING, "since": float}
    def probe(self) -> Dict[str, str]: raise NotImplementedError               # vantage -> UP|DOWN|UNKNOWN, fresh
    def stage(self, name: str, mode: str) -> StepResult: raise NotImplementedError   # run the vault|slice|gateway stage in the flavour of `mode`
    def stage_postcondition(self, name: str, mode: str) -> bool: raise NotImplementedError
    def dns_failover(self, mode: str) -> StepResult: raise NotImplementedError
    def verify(self, mode: str) -> Tuple[bool, str]: raise NotImplementedError    # DNS at the authoritative server + the standby edge answers
    def paused(self) -> bool: raise NotImplementedError
    def approved(self, run: "Run") -> bool: return True                        # has a person/agent approved the DNS step of THIS run? (RealEnv overrides; scripted envs approve)
    def lock(self, wait_s: float) -> "contextlib.AbstractContextManager": raise NotImplementedError   # yields True if acquired
    def gate(self) -> List[str]: raise NotImplementedError                      # what is missing for live mode (empty = ok)
    def load(self) -> Run: raise NotImplementedError
    def save(self, run: Run) -> None: raise NotImplementedError
    def emit(self, event: dict) -> None: raise NotImplementedError
    def metrics(self, run: Run, mode: str, gate_missing: List[str]) -> None: raise NotImplementedError


def fence(env: Env, cfg: Cfg) -> Tuple[bool, str]:
    """True only if EVERY vantage point says DOWN right now. UP = the primary answers (abort). UNKNOWN is retried, then treated as 'cannot confirm' (abort)."""
    detail = ""
    for attempt in range(cfg.unknown_retries + 1):
        try:
            p = env.probe()
        except Exception as e:                                        # a probe that raises is a doubt, never a crash and never a DOWN
            p = {"probe_error": "UNKNOWN"}; detail = f"probe raised {type(e).__name__}"
        if any(v == "UP" for v in p.values()):
            return False, f"primary answers ({p})"
        if p and all(v == "DOWN" for v in p.values()):
            return True, "all vantage points DOWN"
        detail = f"cannot confirm ({p})"
        if attempt < cfg.unknown_retries:
            env.sleep(cfg.unknown_gap_s)
    return False, detail


def _step(run: Run, name: str) -> dict:
    return run.steps.setdefault(name, {"status": "pending", "attempts": 0, "rc": None})


def _abort(env: Env, run: Run, phase: str, why: str) -> None:
    run.phase, run.note, run.ended = phase, why, env.now()
    env.emit({"event": "run_stop", "phase": phase, "why": why, "run": run.id})
    env.save(run)


def execute(env: Env, cfg: Cfg, run: Run) -> None:
    """Continue `run` from its first unfinished step. Persists after every step."""
    mode = run.mode
    for name in STEP_ORDER:
        st = _step(run, name)
        if st["status"] in ("ok", "skipped", "failed_optional"):
            continue
        if env.paused():
            run.phase = "PAUSED"; run.note = f"PAUSE file present before step {name}"
            env.emit({"event": "paused", "before": name, "run": run.id}); env.save(run)
            return
        if name in EFFECTFUL or name == "precheck":
            if name == "precheck" and mode == "live":
                missing = env.gate()
                if missing:
                    _abort(env, run, "ABORTED_GATE", "promotion gate not met: " + "; ".join(missing)); return
            ok, why = fence(env, cfg)
            if not ok:
                # before DNS nothing user-visible happened: this is an abort, not a failure
                _abort(env, run, "ABORTED_PRIMARY_BACK" if "answers" in why else "ABORTED_UNCERTAIN", f"fence before {name}: {why}"); return
        if name == "dns" and mode == "live" and cfg.dns_approval and not env.approved(run):
            if run.phase != "AWAITING_DNS_APPROVAL":
                env.emit({"event": "awaiting_dns_approval", "run": run.id, "started": started(run)})
            run.phase = "AWAITING_DNS_APPROVAL"
            run.note = f"standby services up ({started(run)}); DNS repoint waits for `tier0-executor approve`; the primary is confirmed DOWN on every tick"
            env.save(run); return
        if name == "precheck":
            st.update(status="ok", rc=0); env.save(run); env.emit({"event": "step", "step": name, "status": "ok", "run": run.id}); continue

        if name in STAGES_RUN:
            res = None
            attempts = cfg.stage_attempts_by.get(name, cfg.stage_attempts)
            for attempt in range(1, attempts + 1):
                st["attempts"] = attempt; env.save(run)
                res = env.stage(name, mode)
                if res.rc == 0:
                    break
                if res.rc == 4 and "already" in res.tail.lower():      # promoted by an earlier attempt of this run: done only if it really is healthy
                    if env.stage_postcondition(name, mode):
                        res = StepResult(0, res.tail); break
                    res = StepResult(1, "already promoted but its postcondition fails: " + res.tail[-200:])
                elif res.rc == 4:                                     # REFUSING because the primary answers: the stage's own fence disagrees with ours
                    st.update(status="failed", rc=res.rc); env.emit({"event": "step", "step": name, "status": "refused", "rc": 4, "run": run.id})
                    _abort(env, run, "ABORTED_PRIMARY_BACK", f"{name} refused: the primary answers"); return
                env.emit({"event": "step_retry", "step": name, "attempt": attempt, "rc": res.rc, "run": run.id})
            if res.rc == 0:
                st.update(status="ok", rc=0)
            elif name in OPTIONAL:
                st.update(status="failed_optional", rc=res.rc); run.degraded = True
            else:
                st.update(status="failed", rc=res.rc)
                env.emit({"event": "step", "step": name, "status": "failed", "rc": res.rc, "tail": res.tail[-300:], "run": run.id})
                _abort(env, run, "FAILED", f"required stage {name} failed (rc {res.rc}); DNS untouched, users unaffected; started parts left running: {started(run)}"); return
            env.save(run); env.emit({"event": "step", "step": name, "status": st["status"], "rc": st["rc"], "run": run.id}); continue

        if name == "dns":
            res = None
            for attempt in range(1, cfg.dns_attempts + 1):
                st["attempts"] = attempt; env.save(run)
                if attempt > 1:
                    ok, why = fence(env, cfg)           # the primary may have come back while DNS was failing: stop rather than leave half the names moved
                    if not ok:
                        run.revert_file = res.extra if res and res.extra else run.revert_file
                        _abort(env, run, "FAILED", f"dns incomplete and the fence changed ({why}); revert file: {run.revert_file or 'none'}; run `tier0-dns plan` / `tier0-dns failback`"); return
                res = env.dns_failover(mode)
                if res.extra: run.revert_file = res.extra
                if res.rc == 0:
                    break
                env.emit({"event": "step_retry", "step": "dns", "attempt": attempt, "rc": res.rc, "run": run.id})
                if attempt < cfg.dns_attempts: env.sleep(cfg.dns_backoff_s)
            if res.rc != 0:
                st.update(status="failed", rc=res.rc)
                _abort(env, run, "FAILED", f"dns failed after {cfg.dns_attempts} attempts (rc {res.rc}); may be PARTIALLY applied; revert file: {run.revert_file or 'none'}"); return
            st.update(status="ok", rc=0); env.save(run); env.emit({"event": "step", "step": "dns", "status": "ok", "revert": run.revert_file, "run": run.id}); continue

        if name == "verify":
            ok, why = env.verify(mode)
            if not ok:
                st.update(status="failed", rc=1)
                _abort(env, run, "FAILED", f"failed over but verification failed: {why}"); return
            st.update(status="ok", rc=0); env.save(run); env.emit({"event": "step", "step": "verify", "status": "ok", "run": run.id})
    run.phase = "FAILED_OVER_DEGRADED" if run.degraded else "FAILED_OVER"
    run.ended = env.now(); run.note = "failover complete; failback is manual (scripts/tier0/tier0-failback.sh --check, then --execute --yes-failback)"
    env.emit({"event": "run_done", "phase": run.phase, "run": run.id}); env.save(run)


def started(run: Run) -> str:
    return ",".join(n for n in STAGES_RUN if run.steps.get(n, {}).get("status") == "ok") or "nothing"


def tick(env: Env, cfg: Cfg, mode: str) -> Run:
    """One evaluation (the timer calls this every minute). Returns the persisted run state."""
    assert mode in MODES
    run = env.load()
    ctl = env.controller()
    state, since = ctl.get("state", "NORMAL"), float(ctl.get("since", 0))

    if run.phase in ("SHADOW_DONE", "ABORTED_PRIMARY_BACK", "ABORTED_UNCERTAIN", "ABORTED_GATE") and state == "NORMAL":
        run.phase, run.note = "IDLE", "episode over"; env.save(run)
    if run.phase in ("FAILED_OVER", "FAILED_OVER_DEGRADED") and state == "NORMAL" and run.note.startswith("failover complete"):
        run.note = "PRIMARY BACK and stable: failback is MANUAL: tier0-failback.sh --check, then --execute --yes-failback (vault handback, DNS back, standby teardown, and it acknowledges this run)"
        env.emit({"event": "primary_back", "run": run.id}); env.save(run)
    if run.phase == "PAUSED" and not env.paused():
        run.phase = "RUNNING"
    if run.phase == "AWAITING_DNS_APPROVAL":
        run.phase = "RUNNING"                  # re-evaluated every tick: execute() fences again and parks the run here once more if still unapproved

    if run.phase == "IDLE" and state == "PRIMARY_DOWN" and run.episode != since:
        run = Run(id=f"{int(env.now())}", mode=mode, episode=since, phase="RUNNING", started=env.now())
        env.emit({"event": "run_start", "run": run.id, "mode": mode, "episode": since})
        if mode == "shadow":
            run.phase, run.note, run.ended = "SHADOW_DONE", "SHADOW: would run " + " -> ".join(STEP_ORDER), env.now()
            env.emit({"event": "shadow_decision", "plan": STEP_ORDER, "run": run.id}); env.save(run)
            return run
        env.save(run)

    if run.phase == "RUNNING":
        with env.lock(cfg.lock_wait_s) as got:
            if not got:
                env.emit({"event": "lock_busy", "run": run.id}); return run
            execute(env, cfg, run)
    return run


# ---- real environment ------------------------------------------------------------------------------------------------------------------
class RealEnv(Env):
    CTL_STATE = "/var/lib/tier0-controller/state.json"
    DIR = "/var/lib/tier0-executor"
    PROM = "/var/lib/prometheus/node-exporter/tier0_executor.prom"
    RUN = "/usr/local/bin/tier0-run"
    DNS = "/usr/local/sbin/tier0-dns"
    LOCK = "/run/tier0-chain.lock"
    SIM_NAME = "t0-sim.example.net"
    STAGES = {   # name -> script ; flavour per mode below
        "vault": "tier0-vault-promote.sh", "slice": "tier0-slice-promote.sh", "gateway": "tier0-gateway-promote.sh", "domainscope": "tier0-domainscope-promote.sh",
    }

    def __init__(self, cfg: Cfg):
        self.cfg = cfg
        os.makedirs(self.DIR, exist_ok=True)

    def now(self): return time.time()
    def sleep(self, s): time.sleep(s)

    def controller(self):
        try:
            d = json.load(open(self.CTL_STATE))
            return {"state": d["state"], "since": d["since"]}
        except (OSError, ValueError, KeyError):
            return {"state": "NORMAL", "since": 0}

    def probe(self):
        sys.path.insert(0, "/opt/tier0-runner/controller")
        import tier0_controller as c   # the controller's own probes: one definition of "down"
        return {"vm704": c.vantage_local(), "0mcp": c.vantage_remote()}

    def _argv(self, name: str, mode: str) -> List[str]:
        script = self.STAGES[name]
        if mode == "live":
            return [self.RUN, script, "--promote"]
        if name == "domainscope":
            return [self.RUN, script, "--check"]      # sim: readiness only (hypervisor answers, VM rests, bundle parses). Booting the VM is the daily rehearsal's job, not the simulation's
        # sim: the REHEARSE flavour; the vault rehearsal is kept for the gateway test and removed by the simulation driver
        return [self.RUN, script, "--rehearse"] + (["--keep"] if name == "vault" else [])

    def stage(self, name, mode):
        try:
            r = subprocess.run(self._argv(name, mode), capture_output=True, text=True, timeout=self.cfg.stage_timeout_by.get(name, self.cfg.stage_timeout_s))
            return StepResult(r.returncode, (r.stdout + r.stderr)[-2000:])
        except subprocess.TimeoutExpired:
            return StepResult(124, "timeout")

    def stage_postcondition(self, name, mode):
        # live: the promoted vault/keystore answer on the standby; slice/gateway: the edge answers for a sample name
        try:
            if name == "vault":
                port = 18140 if mode == "live" else 18142          # the rehearsal vault runs on throwaway ports
                r = subprocess.run(["runuser", "-u", "t0runner", "--", "env", "HOME=/var/lib/t0runner", "ssh", "-o", "BatchMode=yes", "0mcp_docker_build",
                                    f"curl -fsS -m 5 http://10.10.10.30:{port}/health"], capture_output=True, text=True, timeout=60)
                return r.returncode == 0 and "ok" in r.stdout
            return self.verify(mode)[0]
        except Exception:
            return False

    def dns_failover(self, mode):
        argv = [self.DNS, "failover", "--to", self.cfg.edge_ip] + (["--only", self.SIM_NAME] if mode == "sim" else []) + ["--apply"]
        r = subprocess.run(argv, capture_output=True, text=True, timeout=1800)
        rev = ""
        for line in (r.stdout + r.stderr).splitlines():
            if line.startswith("revert file:"): rev = line.split(":", 1)[1].strip()
        return StepResult(r.returncode, (r.stdout + r.stderr)[-1500:], rev if rev and os.path.exists(rev) else "")

    def _shows_edge(self, name: str) -> bool:
        zone = ".".join(name.split(".")[-2:])
        for server in subprocess.run(["dig", "+short", "NS", zone], capture_output=True, text=True).stdout.split()[:2]:
            a = subprocess.run(["dig", "+short", "+time=3", "+tries=2", "@" + server, name, "A"], capture_output=True, text=True).stdout.split()
            if self.cfg.edge_ip in a:
                return True
        return False

    def _edge_answers(self, name: str) -> bool:
        r = subprocess.run(["curl", "-sk", "-m", "10", "-o", "/dev/null", "-w", "%{http_code}", "--resolve", f"{name}:443:{self.cfg.edge_ip}", f"https://{name}/health"], capture_output=True, text=True)
        return r.stdout.strip() == "200"

    def verify(self, mode):
        names = self.cfg.sample_names if mode == "live" else (self.SIM_NAME,)
        deadline = time.time() + self.cfg.verify_wait_s
        pending = list(names)
        while pending:
            pending = [n for n in pending if not self._shows_edge(n)]
            if not pending or time.time() >= deadline:
                break
            time.sleep(3)
        if pending:
            return False, f"authoritative DNS shows the standby edge for {len(names) - len(pending)}/{len(names)} sample names after {self.cfg.verify_wait_s} s"
        if mode != "live":
            return True, "sim: DNS verified"
        good = set()
        while len(good) < len(names) and time.time() < deadline + 60:
            good |= {n for n in names if n not in good and self._edge_answers(n)}
            if len(good) >= max(2, len(names) - 1):
                break
            time.sleep(3)
        return (len(good) >= max(2, len(names) - 1)), f"standby edge answers 200 for {len(good)}/{len(names)} sample names"

    def paused(self): return os.path.exists("/var/lib/tier0-controller/PAUSE") or os.path.exists(f"{self.DIR}/PAUSE")

    def approved(self, run):
        try:                                   # the file names the run it approves: an old approval never covers a new episode
            return open(f"{self.DIR}/APPROVE_DNS").read().strip() == run.id
        except OSError:
            return False

    @contextlib.contextmanager
    def lock(self, wait_s):
        fd = os.open(self.LOCK, os.O_CREAT | os.O_RDWR, 0o600)
        got, deadline = False, time.time() + wait_s
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); got = True; break
            except OSError:
                if time.time() >= deadline: break
                time.sleep(5)
        try:
            yield got
        finally:
            if got: fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def gate(self):
        """What is still missing before `live` may act: the written promotion gate (README), machine-checked."""
        missing = []
        now = time.time()

        def hist(path):
            try:
                return [json.loads(l) for l in open(path).read().splitlines() if l.strip()]
            except OSError:
                return []

        def consecutive_green_days(rows, need):
            days = {}
            for r in rows:
                d = time.strftime("%Y-%m-%d", time.gmtime(r["ts"]))
                days[d] = days.get(d, True) and r.get("rc") == 0
            ordered = sorted(days.items())[-need:]
            return len(ordered) == need and all(v for _, v in ordered)
        if not consecutive_green_days(hist("/var/lib/tier0-runner/rehearsal-history.jsonl"), 7): missing.append("7 consecutive green daily rehearsals")
        if not consecutive_green_days(hist("/var/lib/tier0-runner/sim-history.jsonl"), 7): missing.append("7 consecutive green full-cycle simulations")
        try:
            last = float([l.split()[1] for l in open("/var/lib/prometheus/node-exporter/tier0_runner_dns_drill.prom") if l.startswith("tier0_runner_dns_drill_last_success_timestamp_seconds")][0])
            if now - last > 35 * 86400: missing.append("a green DNS drill within 35 days")
        except (OSError, IndexError, ValueError):
            missing.append("a green DNS drill within 35 days")
        ch = hist("/var/lib/tier0-controller/history.jsonl")
        if not ch or now - ch[0]["ts"] < 7 * 86400: missing.append("7 days of shadow controller history")
        else:
            worst = run_ = 0
            for r in ch:
                run_ = run_ + 1 if r.get("tick") == "UNKNOWN" else 0
                worst = max(worst, run_)
            if worst > 15: missing.append(f"controller blind for {worst} consecutive ticks during the shadow period (limit 15)")
        if self.paused(): missing.append("PAUSE file present")
        return missing

    def load(self):
        try:
            d = json.load(open(f"{self.DIR}/current.json")); return Run(**d)
        except (OSError, ValueError, TypeError):
            return Run()

    def save(self, run):
        tmp = f"{self.DIR}/current.json.tmp"
        json.dump(asdict(run), open(tmp, "w"), indent=1); os.replace(tmp, f"{self.DIR}/current.json")

    def emit(self, event):
        event = dict(event, ts=int(time.time()))
        os.makedirs(f"{self.DIR}/log", exist_ok=True)
        with open(f"{self.DIR}/log/events.jsonl", "a") as f: f.write(json.dumps(event) + "\n")
        print(json.dumps(event))

    def metrics(self, run, mode, gate_missing):
        phases = ("IDLE", "SHADOW_DONE", "RUNNING", "PAUSED", "FAILED_OVER", "FAILED_OVER_DEGRADED", "ABORTED_PRIMARY_BACK", "ABORTED_UNCERTAIN", "ABORTED_GATE", "FAILED", "AWAITING_DNS_APPROVAL")
        out = ["# TYPE tier0_executor_last_run_timestamp_seconds gauge", f"tier0_executor_last_run_timestamp_seconds {int(time.time())}"]
        out += [f'tier0_executor_phase{{phase="{p}"}} {1 if run.phase == p else 0}' for p in phases]
        out += [f'tier0_executor_mode{{mode="{m}"}} {1 if m == mode else 0}' for m in MODES]
        out += [f"tier0_executor_gate_missing {len(gate_missing)}", f"tier0_executor_degraded {1 if run.degraded else 0}",
                f"tier0_executor_awaiting_dns_approval {1 if run.phase == 'AWAITING_DNS_APPROVAL' else 0}"]
        tmp = self.PROM + ".tmp"; open(tmp, "w").write("\n".join(out) + "\n"); os.chmod(tmp, 0o644); os.replace(tmp, self.PROM)


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tick"
    cfg = Cfg()
    env = RealEnv(cfg)
    try:
        mode = open("/etc/tier0-executor/mode").read().strip()
    except OSError:
        mode = "shadow"
    if mode not in MODES:
        print(f"unknown mode {mode!r}: using shadow"); mode = "shadow"
    if cmd == "tick":
        run = tick(env, cfg, mode)
        env.metrics(run, mode, env.gate() if mode != "shadow" else [])
        print(f"mode={mode} phase={run.phase} {run.note}")
    elif cmd == "status":
        run = env.load(); print(json.dumps(asdict(run), indent=1)); print("gate missing:", env.gate())
    elif cmd == "ack":
        run = env.load()
        if run.phase in ("FAILED_OVER", "FAILED_OVER_DEGRADED", "FAILED", "PAUSED", "AWAITING_DNS_APPROVAL", "ABORTED_GATE", "ABORTED_PRIMARY_BACK", "ABORTED_UNCERTAIN"):
            run.phase, run.note = "IDLE", "acknowledged by a person/agent after failback or cleanup"; env.save(run); env.emit({"event": "ack", "run": run.id}); print("ok: IDLE")
        else:
            print(f"nothing to acknowledge in phase {run.phase}")
    elif cmd == "approve":
        run = env.load()
        if run.phase != "AWAITING_DNS_APPROVAL":
            print(f"nothing to approve in phase {run.phase}"); return 1
        os.makedirs(env.DIR, exist_ok=True)
        open(f"{env.DIR}/APPROVE_DNS", "w").write(run.id + "\n"); env.emit({"event": "dns_approved", "run": run.id}); print(f"approved run {run.id}: the next tick repoints DNS")
    elif cmd == "plan":
        print(" -> ".join(STEP_ORDER), "| mode:", mode, "| gate missing:", env.gate())
    else:
        print(__doc__); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
