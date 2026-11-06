"""Scenario tests of the Tier-0 executor (config/0infer/tier0-runner/executor/tier0_executor.py) with a scripted fake environment.

What is under test is the control logic of the part that ACTS: fencing, ordering, failure policy, resume, pause, locking, one run per episode, no automatic failback.
Every rule in the module docstring has a test; the last test throws 400 seeded random fault schedules at the executor and checks the invariants that must hold for ALL of them.
"""
import contextlib
import copy
import importlib.util
import pathlib
import random
import sys

import pytest

SRC = pathlib.Path(__file__).resolve().parents[1] / "config" / "0infer" / "tier0-runner" / "executor" / "tier0_executor.py"
spec = importlib.util.spec_from_file_location("ex", SRC)
ex = importlib.util.module_from_spec(spec)
sys.modules["ex"] = ex
spec.loader.exec_module(ex)

DOWN = {"vm704": "DOWN", "0mcp": "DOWN"}
UP = {"vm704": "UP", "0mcp": "UP"}
UNK = {"vm704": "DOWN", "0mcp": "UNKNOWN"}
CFG = ex.Cfg(dns_attempts=3, dns_backoff_s=60, stage_attempts=2, unknown_retries=2, unknown_gap_s=10, lock_wait_s=0)


class FakeEnv(ex.Env):
    def __init__(self):
        self.t = 10_000.0
        self.ctl = {"state": "PRIMARY_DOWN", "since": 9_000.0}
        self.probe_fn = lambda env: dict(DOWN)
        self.stage_rc = {}                 # name -> list of (rc, tail); the last entry repeats
        self.post = {}                     # name -> bool
        self.dns_script = [(0, "/var/lib/tier0-dns/revert-1.json")]
        self.verify_result = (True, "ok")
        self.pause = False
        self.lock_ok = True
        self.gate_missing = []
        self.run = ex.Run()
        self.events = []
        self.calls = []                    # ordered effectful calls
        self.probe_calls = 0
        self.after_stage = {}              # name -> callable(env) run after that stage call

    def now(self): return self.t
    def sleep(self, s): self.t += s
    def controller(self): return dict(self.ctl)

    def probe(self):
        self.probe_calls += 1
        return self.probe_fn(self)

    def stage(self, name, mode):
        self.calls.append(("stage", name, mode))
        lst = self.stage_rc.get(name, [(0, "")])
        rc, tail = lst.pop(0) if len(lst) > 1 else lst[0]
        if name in self.after_stage: self.after_stage[name](self)
        return ex.StepResult(rc, tail)

    def stage_postcondition(self, name, mode): return self.post.get(name, True)

    def dns_failover(self, mode):
        self.calls.append(("dns", mode))
        rc, extra = self.dns_script.pop(0) if len(self.dns_script) > 1 else self.dns_script[0]
        return ex.StepResult(rc, "", extra)

    def verify(self, mode):
        self.calls.append(("verify", mode))
        return self.verify_result

    def paused(self): return self.pause

    @contextlib.contextmanager
    def lock(self, wait_s): yield self.lock_ok

    def gate(self): return list(self.gate_missing)
    def load(self): return copy.deepcopy(self.run)          # a restart reloads from persisted state, not from memory
    def save(self, run): self.run = copy.deepcopy(run)
    def emit(self, event): self.events.append(event)
    def metrics(self, run, mode, gate_missing): pass

    def effects(self, kind=None): return [c for c in self.calls if kind is None or c[0] == kind]


def go(env, mode="live", cfg=CFG): return ex.tick(env, cfg, mode)


# ---- the clean path ----------------------------------------------------------------------------------------------------------------
def test_clean_failover_runs_every_step_once_in_order_and_ends_failed_over():
    env = FakeEnv(); run = go(env)
    assert [c[:2] for c in env.calls] == [("stage", "vault"), ("stage", "slice"), ("stage", "gateway"), ("stage", "domainscope"), ("dns", "live"), ("verify", "live")]
    assert run.phase == "FAILED_OVER" and not run.degraded and run.revert_file == "/var/lib/tier0-dns/revert-1.json"
    assert all(run.steps[s]["status"] == "ok" for s in ex.STEP_ORDER)
    assert [e["event"] for e in env.events][0] == "run_start" and env.events[-1]["event"] == "run_done"


def test_every_effectful_step_is_preceded_by_a_fresh_fence():
    env = FakeEnv(); go(env)
    assert env.probe_calls == 6          # precheck + vault + slice + gateway + domainscope + dns


# ---- shadow ------------------------------------------------------------------------------------------------------------------------
def test_shadow_records_the_decision_and_executes_nothing_then_waits_for_the_episode_to_end():
    env = FakeEnv(); run = go(env, "shadow")
    assert run.phase == "SHADOW_DONE" and env.calls == [] and env.probe_calls == 0 and "would run" in run.note
    for _ in range(5): go(env, "shadow")                          # still the same episode: no second decision, no effects
    assert env.calls == [] and sum(e["event"] == "shadow_decision" for e in env.events) == 1
    env.ctl = {"state": "NORMAL", "since": 9_500.0}; assert go(env, "shadow").phase == "IDLE"
    env.ctl = {"state": "PRIMARY_DOWN", "since": 12_000.0}; assert go(env, "shadow").phase == "SHADOW_DONE"      # a NEW episode decides again
    assert sum(e["event"] == "shadow_decision" for e in env.events) == 2


# ---- the fence ---------------------------------------------------------------------------------------------------------------------
def test_primary_answering_before_anything_starts_aborts_without_a_single_effect():
    env = FakeEnv(); env.probe_fn = lambda e: dict(UP)
    run = go(env)
    assert run.phase == "ABORTED_PRIMARY_BACK" and env.calls == []


def test_primary_returning_after_the_vault_stage_aborts_before_the_next_step_and_never_touches_dns():
    env = FakeEnv()
    env.after_stage["vault"] = lambda e: setattr(e, "probe_fn", lambda x: dict(UP))
    run = go(env)
    assert run.phase == "ABORTED_PRIMARY_BACK" and env.effects("stage") == [("stage", "vault", "live")] and env.effects("dns") == []
    assert "vault" in run.note or "fence before slice" in run.note


def test_an_unknown_vantage_is_retried_and_the_run_goes_on_when_it_clears():
    env = FakeEnv(); seq = [dict(UNK), dict(UNK)]
    env.probe_fn = lambda e: seq.pop(0) if seq else dict(DOWN)
    t0 = env.t; run = go(env)
    assert run.phase == "FAILED_OVER" and env.t - t0 >= 2 * CFG.unknown_gap_s


def test_a_vantage_that_stays_unknown_aborts_as_uncertain_never_acts_on_a_doubt():
    env = FakeEnv(); env.probe_fn = lambda e: dict(UNK)
    run = go(env)
    assert run.phase == "ABORTED_UNCERTAIN" and env.calls == []


def test_a_probe_that_raises_is_a_doubt_not_a_crash():
    env = FakeEnv()
    def boom(e): raise RuntimeError("ssh exploded")
    env.probe_fn = boom
    run = go(env)
    assert run.phase == "ABORTED_UNCERTAIN" and env.calls == []


def test_a_stage_that_refuses_because_the_primary_answers_aborts_instead_of_retrying():
    env = FakeEnv(); env.stage_rc["vault"] = [(4, "REFUSING: the 0docker site still answers. Two writable vaults = split brain.")]
    run = go(env)
    assert run.phase == "ABORTED_PRIMARY_BACK" and env.effects("stage") == [("stage", "vault", "live")]


# ---- failure policy ----------------------------------------------------------------------------------------------------------------
def test_vault_failure_aborts_with_dns_untouched():
    env = FakeEnv(); env.stage_rc["vault"] = [(3, "images missing")]
    run = go(env)
    assert run.phase == "FAILED" and env.effects("stage") == [("stage", "vault", "live")] * 2 and env.effects("dns") == []
    assert "DNS untouched" in run.note


def test_gateway_failure_aborts_before_dns_and_names_what_was_left_running():
    env = FakeEnv(); env.stage_rc["gateway"] = [(9, "nginx -t failed")]
    run = go(env)
    assert run.phase == "FAILED" and env.effects("dns") == [] and "vault,slice" in run.note


def test_slice_failure_is_degraded_but_the_run_still_reaches_dns():
    env = FakeEnv(); env.stage_rc["slice"] = [(5, "clash")]
    run = go(env)
    assert run.phase == "FAILED_OVER_DEGRADED" and run.degraded and run.steps["slice"]["status"] == "failed_optional" and env.effects("dns") == [("dns", "live")]


def test_a_stage_succeeding_on_its_second_attempt_counts_once():
    env = FakeEnv(); env.stage_rc["vault"] = [(1, "flaky"), (0, "")]
    run = go(env)
    assert run.phase == "FAILED_OVER" and run.steps["vault"]["attempts"] == 2


def test_already_promoted_is_done_only_if_the_postcondition_holds():
    env = FakeEnv(); env.stage_rc["vault"] = [(4, "REFUSING: /var/lib/tier0-promoted already exists on the standby (already promoted?)")]
    assert go(env).phase == "FAILED_OVER"                         # healthy: counts as done
    env = FakeEnv(); env.stage_rc["vault"] = [(4, "REFUSING: already exists (already promoted?)")]; env.post["vault"] = False
    run = go(env)
    assert run.phase == "FAILED" and run.steps["vault"]["status"] == "failed"      # present but unhealthy: a failure, NOT "primary is back"


def test_dns_transient_failures_are_retried_with_backoff_and_the_revert_file_is_kept():
    env = FakeEnv(); env.dns_script = [(1, ""), (1, ""), (0, "/r.json")]
    t0 = env.t; run = go(env)
    assert run.phase == "FAILED_OVER" and run.steps["dns"]["attempts"] == 3 and run.revert_file == "/r.json" and env.t - t0 >= 2 * CFG.dns_backoff_s


def test_dns_permanent_failure_ends_failed_and_says_it_may_be_partial():
    env = FakeEnv(); env.dns_script = [(1, "/partial.json")]
    run = go(env)
    assert run.phase == "FAILED" and "PARTIALLY" in run.note and "/partial.json" in run.note and len(env.effects("dns")) == CFG.dns_attempts


def test_primary_returning_while_dns_is_failing_stops_the_retries():
    env = FakeEnv(); env.dns_script = [(1, "/partial.json")]
    calls = {"n": 0}
    def probe(e):
        calls["n"] += 1
        return dict(DOWN) if e.effects("dns") == [] else dict(UP)    # after the first DNS attempt the primary answers
    env.probe_fn = probe
    run = go(env)
    assert run.phase == "FAILED" and len(env.effects("dns")) == 1 and "fence changed" in run.note and "/partial.json" in run.note


def test_verification_failure_after_dns_is_reported_not_hidden():
    env = FakeEnv(); env.verify_result = (False, "standby edge answers 200 for 0/3 sample names")
    run = go(env)
    assert run.phase == "FAILED" and "verification failed" in run.note and env.effects("dns")


# ---- resume, pause, lock -----------------------------------------------------------------------------------------------------------
def test_a_restart_continues_with_the_first_unfinished_step_and_repeats_nothing():
    env = FakeEnv()
    env.run = ex.Run(id="1", mode="live", episode=9_000.0, phase="RUNNING", started=9_900.0,
                     steps={"precheck": {"status": "ok", "attempts": 0, "rc": 0}, "vault": {"status": "ok", "attempts": 1, "rc": 0}, "slice": {"status": "ok", "attempts": 1, "rc": 0}})
    run = go(env)
    assert [c[:2] for c in env.calls] == [("stage", "gateway"), ("stage", "domainscope"), ("dns", "live"), ("verify", "live")] and run.phase == "FAILED_OVER"


def test_pause_halts_between_steps_and_resumes_where_it_stopped():
    env = FakeEnv(); env.after_stage["vault"] = lambda e: setattr(e, "pause", True)
    run = go(env)
    assert run.phase == "PAUSED" and [c[:2] for c in env.calls] == [("stage", "vault")]
    env.pause = False; env.after_stage = {}
    run = go(env)
    assert run.phase == "FAILED_OVER" and [c[:2] for c in env.calls] == [("stage", "vault"), ("stage", "slice"), ("stage", "gateway"), ("stage", "domainscope"), ("dns", "live"), ("verify", "live")]


def test_a_busy_lock_means_no_effects_and_the_next_tick_runs():
    env = FakeEnv(); env.lock_ok = False
    run = go(env)
    assert run.phase == "RUNNING" and env.calls == [] and any(e["event"] == "lock_busy" for e in env.events)
    env.lock_ok = True
    assert go(env).phase == "FAILED_OVER"


# ---- gate and modes ----------------------------------------------------------------------------------------------------------------
def test_live_refuses_when_the_promotion_gate_is_not_met_and_says_why():
    env = FakeEnv(); env.gate_missing = ["7 consecutive green daily rehearsals"]
    run = go(env, "live")
    assert run.phase == "ABORTED_GATE" and env.calls == [] and "7 consecutive green daily rehearsals" in run.note


def test_sim_mode_ignores_the_gate_and_uses_the_sim_flavour_everywhere():
    env = FakeEnv(); env.gate_missing = ["anything"]
    run = go(env, "sim")
    assert run.phase == "FAILED_OVER" and {c[-1] for c in env.calls} == {"sim"}


# ---- one run per episode, no automatic failback ------------------------------------------------------------------------------------
def test_after_the_run_nothing_automatic_happens_not_even_when_the_primary_comes_back():
    env = FakeEnv(); go(env); n = len(env.calls)
    for _ in range(5): go(env)
    assert len(env.calls) == n                                    # same episode: no second run
    env.ctl = {"state": "RECOVERING", "since": 12_000.0}; go(env)
    env.ctl = {"state": "NORMAL", "since": 12_500.0}; run = go(env)
    assert len(env.calls) == n and run.phase == "FAILED_OVER" and "failback is MANUAL" in run.note      # it only says so


def test_ack_after_a_manual_failback_returns_to_idle_and_a_new_episode_starts_a_new_run():
    env = FakeEnv(); go(env); n = len(env.calls)
    env.ctl = {"state": "NORMAL", "since": 12_500.0}; go(env)
    env.run.phase = "IDLE"                                         # what `tier0-executor ack` does
    env.ctl = {"state": "PRIMARY_DOWN", "since": 20_000.0}
    run = go(env)
    assert run.phase == "FAILED_OVER" and len(env.calls) == 2 * n and run.episode == 20_000.0


def test_an_aborted_episode_ends_when_the_controller_says_normal_and_can_trigger_again():
    env = FakeEnv(); env.probe_fn = lambda e: dict(UP)
    assert go(env).phase == "ABORTED_PRIMARY_BACK"
    env.ctl = {"state": "NORMAL", "since": 9_500.0}; assert go(env).phase == "IDLE"
    env.probe_fn = lambda e: dict(DOWN); env.ctl = {"state": "PRIMARY_DOWN", "since": 15_000.0}
    assert go(env).phase == "FAILED_OVER"


# ---- invariants under random faults -------------------------------------------------------------------------------------------------
KNOWN = {"IDLE", "SHADOW_DONE", "RUNNING", "PAUSED", "FAILED_OVER", "FAILED_OVER_DEGRADED", "ABORTED_PRIMARY_BACK", "ABORTED_UNCERTAIN", "ABORTED_GATE", "FAILED"}


@pytest.mark.parametrize("seed", range(400))
def test_invariants_hold_under_random_fault_schedules(seed):
    r = random.Random(seed)
    env = FakeEnv()
    env.probe_fn = lambda e: r.choice([dict(DOWN)] * 6 + [dict(UP), dict(UNK)])                  # mostly down, sometimes up, sometimes unknown
    for name in ("vault", "slice", "gateway", "domainscope"):
        env.stage_rc[name] = [(r.choice([0, 0, 0, 1, 3, 4, 9]), r.choice(["", "already exists (already promoted?)", "REFUSING: the 0docker site still answers"])) for _ in range(3)]
    env.dns_script = [(r.choice([0, 0, 1]), "/r%d.json" % i) for i in range(4)]
    env.post = {n: r.random() < 0.7 for n in ("vault", "slice", "gateway", "domainscope")}
    env.verify_result = (r.random() < 0.9, "x")
    env.pause = r.random() < 0.1
    mode = r.choice(["sim", "live"]); env.gate_missing = ["gate"] if (mode == "live" and r.random() < 0.15) else []
    for step in range(12):                                                                       # the timer ticks again and again, with the world changing in between
        if r.random() < 0.2: env.pause = not env.pause
        if r.random() < 0.15: env.lock_ok = not env.lock_ok
        run = go(env, mode)
        assert run.phase in KNOWN
    stages = [c for c in env.calls if c[0] == "stage"]
    dns = [c for c in env.calls if c[0] == "dns"]
    final = env.run
    if dns:                                                                                      # DNS (the point of no return) is only ever reached after the REQUIRED stages worked
        assert final.steps["vault"]["status"] == "ok" and final.steps["gateway"]["status"] == "ok"
    if final.phase in ("FAILED_OVER", "FAILED_OVER_DEGRADED"):
        assert final.steps["dns"]["status"] == "ok" and final.steps["verify"]["status"] == "ok"
    ok_steps = [n for n in ("vault", "slice", "gateway", "domainscope") if final.steps.get(n, {}).get("status") == "ok"]
    for n in ok_steps:                                                                           # a step that finished is never executed again (resume safety)
        assert final.steps[n]["attempts"] <= CFG.stage_attempts
    assert sum(1 for c in env.calls if c == ("dns", mode)) <= CFG.dns_attempts                   # bounded retries
    assert not (mode == "live" and env.gate_missing and (stages or dns))                         # a closed gate means no effect at all


# ---- the real environment's command construction (no process is started: subprocess.run is captured) -------------------------------
class _Cap:
    def __init__(self): self.argvs = []
    def __call__(self, argv, *a, **k):
        self.argvs.append(list(argv))
        class R: returncode = 0; stdout = "revert file: /nonexistent\n"; stderr = ""
        return R()


def test_real_env_builds_the_live_and_the_sim_commands_correctly(monkeypatch):
    cap = _Cap(); monkeypatch.setattr(ex.subprocess, "run", cap)
    monkeypatch.setattr(ex.os, "makedirs", lambda *a, **k: None)
    env = ex.RealEnv(ex.Cfg(edge_ip="203.0.113.1"))
    env.stage("vault", "live"); env.stage("slice", "live"); env.stage("gateway", "live"); env.stage("domainscope", "live")
    assert [a[1:] for a in cap.argvs] == [["tier0-vault-promote.sh", "--promote"], ["tier0-slice-promote.sh", "--promote"], ["tier0-gateway-promote.sh", "--promote"],
                                          ["tier0-domainscope-promote.sh", "--promote"]]
    cap.argvs.clear()
    env.stage("vault", "sim"); env.stage("slice", "sim"); env.stage("gateway", "sim"); env.stage("domainscope", "sim")
    assert [a[1:] for a in cap.argvs] == [["tier0-vault-promote.sh", "--rehearse", "--keep"], ["tier0-slice-promote.sh", "--rehearse"], ["tier0-gateway-promote.sh", "--rehearse"],
                                          ["tier0-domainscope-promote.sh", "--check"]]       # the simulation never boots the standby VM: that is the daily rehearsal's job
    cap.argvs.clear()
    env.dns_failover("live"); env.dns_failover("sim")
    live, sim = cap.argvs
    assert live[1:] == ["failover", "--to", "203.0.113.1", "--apply"] and "--only" not in live          # live moves everything on the primary address
    assert sim[1:] == ["failover", "--to", "203.0.113.1", "--only", "t0-sim.example.net", "--apply"]    # sim touches exactly ONE throwaway name, --to keeps its value


def test_live_never_gets_a_rehearse_flag_and_sim_never_gets_promote(monkeypatch):
    cap = _Cap(); monkeypatch.setattr(ex.subprocess, "run", cap); monkeypatch.setattr(ex.os, "makedirs", lambda *a, **k: None)
    env = ex.RealEnv(ex.Cfg())
    for n in ("vault", "slice", "gateway"):
        env.stage(n, "live"); env.stage(n, "sim")
    live = cap.argvs[0::2]; sim = cap.argvs[1::2]
    assert all("--promote" in a and "--rehearse" not in a for a in live)
    assert all("--rehearse" in a and "--promote" not in a for a in sim)


def test_the_simulation_never_gets_promote_or_rehearse_for_the_domainscope_stage(monkeypatch):
    cap = _Cap(); monkeypatch.setattr(ex.subprocess, "run", cap); monkeypatch.setattr(ex.os, "makedirs", lambda *a, **k: None)
    env = ex.RealEnv(ex.Cfg())
    env.stage("domainscope", "sim"); env.stage("domainscope", "live")
    sim, live = cap.argvs
    assert "--check" in sim and "--promote" not in sim and "--rehearse" not in sim
    assert "--promote" in live and "--check" not in live


# ---- the DomainScope stage is optional: it must never hold back the DNS flip of everything else -----------------------------------
def test_a_failed_domainscope_stage_degrades_the_run_but_dns_still_flips():
    env = FakeEnv(); env.stage_rc["domainscope"] = [(5, "the standby VM did not start")]
    run = go(env)
    assert run.phase == "FAILED_OVER_DEGRADED" and run.degraded and run.steps["domainscope"]["status"] == "failed_optional"
    assert env.effects("dns") == [("dns", "live")] and run.steps["dns"]["status"] == "ok" and run.steps["verify"]["status"] == "ok"
    assert [c[2] for c in env.calls if c[:2] == ("stage", "domainscope")] == ["live"]                          # ONE attempt: an optional stage is reported, not retried, before the DNS flip


def test_the_required_stages_still_get_their_second_attempt_but_domainscope_does_not():
    env = FakeEnv(); env.stage_rc["gateway"] = [(5, "transient"), (0, "")]; env.stage_rc["domainscope"] = [(5, "agent did not answer"), (0, "")]
    run = go(env)
    assert run.steps["gateway"]["status"] == "ok" and run.steps["gateway"]["attempts"] == 2
    assert run.steps["domainscope"]["status"] == "failed_optional" and run.steps["domainscope"]["attempts"] == 1 and run.degraded        # its retry would delay the DNS flip of everything else


def test_each_stage_has_its_own_time_budget_and_domainscope_is_bounded_tighter(monkeypatch):
    seen = {}
    class R:
        returncode = 0; stdout = ""; stderr = ""
    def fake_run(argv, *a, **k):
        seen[argv[1]] = k.get("timeout"); return R()
    monkeypatch.setattr(ex.subprocess, "run", fake_run); monkeypatch.setattr(ex.os, "makedirs", lambda *a, **k: None)
    env = ex.RealEnv(ex.Cfg())
    for n in ("vault", "slice", "gateway", "domainscope"):
        env.stage(n, "live")
    assert seen["tier0-vault-promote.sh"] == seen["tier0-slice-promote.sh"] == seen["tier0-gateway-promote.sh"] == 900 and seen["tier0-domainscope-promote.sh"] == 600


def test_the_primary_answering_during_the_domainscope_stage_aborts_before_dns():
    env = FakeEnv(); env.stage_rc["domainscope"] = [(4, "REFUSING: the primary answers from here (203.0.113.2:443)")]
    run = go(env)
    assert run.phase == "ABORTED_PRIMARY_BACK" and env.effects("dns") == [] and env.effects("verify") == []
    assert "domainscope refused" in run.note


def test_a_domainscope_failure_and_a_slice_failure_together_still_flip_dns_and_say_both():
    env = FakeEnv(); env.stage_rc["slice"] = [(5, "clash")]; env.stage_rc["domainscope"] = [(5, "boom")]
    run = go(env)
    assert run.phase == "FAILED_OVER_DEGRADED" and run.steps["slice"]["status"] == "failed_optional" and run.steps["domainscope"]["status"] == "failed_optional"
    assert env.effects("dns") == [("dns", "live")]


def test_the_domainscope_stage_runs_after_the_gateway_so_the_edge_it_is_verified_through_exists():
    assert ex.STEP_ORDER.index("domainscope") == ex.STEP_ORDER.index("gateway") + 1 and ex.STEP_ORDER.index("domainscope") < ex.STEP_ORDER.index("dns")
    assert "domainscope" in ex.OPTIONAL and "domainscope" in ex.EFFECTFUL                                    # optional, and fenced like every effectful step


# ---- verification polls: found by the first live simulation (the authoritative server needs seconds to show a new record) ----------------
class _Clock:
    def __init__(self): self.t = 1000.0
    def time(self): return self.t
    def sleep(self, s): self.t += s


def _verify_env(monkeypatch, dns_ready_after, edge_ok=True, wait=150):
    clock = _Clock()
    monkeypatch.setattr(ex.time, "time", clock.time); monkeypatch.setattr(ex.time, "sleep", clock.sleep)
    monkeypatch.setattr(ex.os, "makedirs", lambda *a, **k: None)
    seen = {"polls": 0}
    def fake_run(argv, *a, **k):
        class R: returncode = 0; stderr = ""; stdout = ""
        r = R()
        if argv[:3] == ["dig", "+short", "NS"]: r.stdout = "ns1.example.\nns2.example.\n"
        elif argv[0] == "dig":
            seen["polls"] += 1
            r.stdout = "203.0.113.1\n" if clock.t >= 1000.0 + dns_ready_after else "203.0.113.2\n"
        elif argv[0] == "curl": r.stdout = "200" if edge_ok else "502"
        return r
    monkeypatch.setattr(ex.subprocess, "run", fake_run)
    return ex.RealEnv(ex.Cfg(verify_wait_s=wait)), clock, seen


def test_verify_waits_for_the_new_record_to_show_instead_of_judging_the_first_look(monkeypatch):
    env, clock, seen = _verify_env(monkeypatch, dns_ready_after=20)
    ok, why = env.verify("sim")
    assert ok and seen["polls"] > 2 and 20 <= clock.t - 1000.0 < 40


def test_verify_gives_up_after_the_wait_and_says_how_many_names_were_seen(monkeypatch):
    env, clock, seen = _verify_env(monkeypatch, dns_ready_after=10_000, wait=30)
    ok, why = env.verify("sim")
    assert not ok and "0/1" in why and "30 s" in why and clock.t - 1000.0 < 60


def test_live_verify_also_needs_the_standby_edge_to_answer(monkeypatch):
    env, _, _ = _verify_env(monkeypatch, dns_ready_after=0, edge_ok=False, wait=30)
    ok, why = env.verify("live")
    assert not ok and "standby edge answers 200 for 0/3" in why
    env, _, _ = _verify_env(monkeypatch, dns_ready_after=0, edge_ok=True)
    assert env.verify("live")[0]


def test_the_simulation_polls_for_the_moved_record_instead_of_sampling_once():
    # source-level pin: tier0_sim.py is a script run daily on the runner, not importable here. The authoritative nameservers of the zone show a new record a few seconds apart and `dig NS` rotates which
    # one is asked first, so a single immediate sample after the DNS stage flaked (2026-10-18 06:52Z: every step ok, "only the throwaway name was moved" FAIL, critical Tier0SimFailed).
    src = (pathlib.Path(__file__).resolve().parents[1] / "config" / "0infer" / "tier0-runner" / "executor" / "tier0_sim.py").read_text()
    line = next(l for l in src.splitlines() if "only the throwaway name was moved to the standby edge" in l)
    assert "wait_for(cfg.edge_ip" in line and "authoritative() ==" not in line
