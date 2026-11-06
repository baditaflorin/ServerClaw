"""The DNS approval gate of the tier0 executor (live mode waits for `tier0-executor approve`; sim and shadow never wait)."""
import importlib.util
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "config" / "0infer" / "tier0-runner" / "executor" / "tier0_executor.py"
spec = importlib.util.spec_from_file_location("tier0_executor", SRC)
ex = importlib.util.module_from_spec(spec)
sys.modules["tier0_executor"] = ex
spec.loader.exec_module(ex)


class FakeEnv(ex.Env):
    def __init__(self, probes=None, approved=False):
        self.probes = list(probes or [{"vm704": "DOWN", "0mcp": "DOWN"}])
        self.is_approved = approved
        self.calls, self.events, self.saved, self.t = [], [], None, 1000.0

    def now(self): return self.t
    def sleep(self, s): self.t += s
    def controller(self): return {"state": "PRIMARY_DOWN", "since": 1.0}
    def probe(self): return self.probes.pop(0) if len(self.probes) > 1 else self.probes[0]
    def stage(self, name, mode): self.calls.append(("stage", name, mode)); return ex.StepResult(0, "ok")
    def stage_postcondition(self, name, mode): return True
    def dns_failover(self, mode): self.calls.append(("dns", mode)); return ex.StepResult(0, "ok", "/tmp/revert")
    def verify(self, mode): return True, "ok"
    def paused(self): return False
    def approved(self, run): return self.is_approved
    def lock(self, wait_s): raise NotImplementedError
    def gate(self): return []
    def load(self): return self.saved or ex.Run()
    def save(self, run): self.saved = run
    def emit(self, event): self.events.append(event)
    def metrics(self, run, mode, gate_missing): pass


def run_live(env, cfg=None):
    run = ex.Run(id="r1", mode="live", phase="RUNNING", started=1.0)
    ex.execute(env, cfg or ex.Cfg(), run)
    return run


class DnsApprovalGate(unittest.TestCase):
    def test_live_waits_before_dns_until_approved(self):
        env = FakeEnv()
        run = run_live(env)
        self.assertEqual(run.phase, "AWAITING_DNS_APPROVAL")
        self.assertNotIn(("dns", "live"), env.calls)
        self.assertEqual([c[1] for c in env.calls if c[0] == "stage"], ["vault", "slice", "gateway", "domainscope"])
        self.assertEqual([e["event"] for e in env.events].count("awaiting_dns_approval"), 1)

    def test_waiting_notifies_once_and_resumes_after_approval(self):
        env = FakeEnv()
        run = run_live(env)
        run.phase = "RUNNING"                      # what tick() does every minute
        ex.execute(env, ex.Cfg(), run)
        self.assertEqual([e["event"] for e in env.events].count("awaiting_dns_approval"), 2)  # execute() alone re-emits only because tick() resets the phase
        env.is_approved = True
        run.phase = "RUNNING"
        ex.execute(env, ex.Cfg(), run)
        self.assertEqual(run.phase, "FAILED_OVER")
        self.assertIn(("dns", "live"), env.calls)

    def test_primary_coming_back_while_waiting_aborts(self):
        env = FakeEnv(probes=[{"vm704": "DOWN", "0mcp": "DOWN"}] * 6 + [{"vm704": "UP", "0mcp": "DOWN"}])
        run = run_live(env)
        self.assertEqual(run.phase, "AWAITING_DNS_APPROVAL")
        env.is_approved = True
        run.phase = "RUNNING"
        ex.execute(env, ex.Cfg(), run)
        self.assertEqual(run.phase, "ABORTED_PRIMARY_BACK")
        self.assertNotIn(("dns", "live"), env.calls)

    def test_sim_never_waits(self):
        env = FakeEnv()
        run = ex.Run(id="r2", mode="sim", phase="RUNNING", started=1.0)
        ex.execute(env, ex.Cfg(), run)
        self.assertEqual(run.phase, "FAILED_OVER")
        self.assertIn(("dns", "sim"), env.calls)

    def test_approval_can_be_disabled_by_config(self):
        env = FakeEnv()
        run = run_live(env, ex.Cfg(dns_approval=False))
        self.assertEqual(run.phase, "FAILED_OVER")

    def test_real_env_approval_names_the_run(self):
        import tempfile, os
        cfg = ex.Cfg()
        env = ex.RealEnv.__new__(ex.RealEnv)
        with tempfile.TemporaryDirectory() as d:
            env.DIR = d
            run = ex.Run(id="r1")
            self.assertFalse(ex.RealEnv.approved(env, run))
            open(os.path.join(d, "APPROVE_DNS"), "w").write("r0\n")
            self.assertFalse(ex.RealEnv.approved(env, run))          # an old approval does not cover this run
            open(os.path.join(d, "APPROVE_DNS"), "w").write("r1\n")
            self.assertTrue(ex.RealEnv.approved(env, run))


if __name__ == "__main__":
    unittest.main()
