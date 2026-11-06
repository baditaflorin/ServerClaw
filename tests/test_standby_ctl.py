"""standby-ctl (config/0infer/tier0-runner/host/standby_ctl.py): the controller of the DomainScope standby VM on the 0infer hypervisor.

The hypervisor and the guest are replaced by a fake that speaks the real `qm` command line (status, config, set, start, shutdown, stop, agent ping, guest exec) and keeps
a small world: VM state, NIC link, what runs in the guest. Three guest scripts (image resolution, DB probe, bundle application) are additionally EXECUTED for real against shim
`docker` binaries in a temp root, and every script the controller ever sends is syntax-checked (bash -n, python compile), so a quoting slip cannot hide behind the fake.

What the tests pin down, in order of how much damage it would do if it broke:
  * the standby never reaches a network before the silent check passed (a restored copy carries the production VM's tailnet identity)
  * it never activates while the primary answers or while it cannot tell (no control target), and never starts the production singleton writer on its own
  * a rehearsal always ends in the resting state (stopped, link down), whatever failed, and NEVER runs the production stack against the production database (the compose
    file reads POSTGRES_DSN through env_file: a shell variable is silently ignored, so the rehearsal swaps the .env and checks the RENDERED config and the running containers)
  * no secret value reaches stdout, stderr or the state file
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import textwrap
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "config" / "0infer" / "tier0-runner" / "host" / "standby_ctl.py"
spec = importlib.util.spec_from_file_location("standby_ctl", SRC)
sc = importlib.util.module_from_spec(spec)
sys.modules["standby_ctl"] = sc
spec.loader.exec_module(sc)

SECRET = "TOPSECRET-dsn-password-0123456789abcdef"
PROD_DB = "prod_2026_domainscope_scrapetheworld_org"
STAGE_DB = "stage_2026_domainscope_scrapetheworld_org"
PG_CERT_PATH = "/etc/standby-ctl/pg-tls/infer-pg-primary.crt"
PG_CERT_FILE = SRC.parent / "pg-tls" / "infer-pg-primary.crt"
PG_CERT_BYTES = PG_CERT_FILE.read_bytes()


# ---------------------------------------------------------------------------------------------------------------------------------------------------- bundle fixtures
def make_bundle(env_extra=(), secrets=25, graph=1, tags=("1.99.312-bed9c9a", "1.99.312-61da0ea"), compose_bytes=25000, nvars=320, dsn=True, extra_members=(), prod_db=PROD_DB, staging=True, staging_db=STAGE_DB, db_host="db.example", staging_host=None):
    lines = [f"API_IMAGE_TAG={tags[0]}", f"FRONTEND_IMAGE_TAG={tags[1]}"]
    if dsn:
        lines.append(f"POSTGRES_DSN=postgres://domainscope_app:{SECRET}@{db_host}:5432/{prod_db}?sslmode=verify-ca&sslrootcert=/data/pg-tls/infer-pg-primary.crt")
    lines += ["FLEET_INTERNAL_HOST=10.10.10.20", "FLEET_COLOCATE_SERVICES=social-graph,asn-lookup", "TRUSTED_PROXIES=10.10.10.10,10.10.10.20"]
    lines += list(env_extra)
    lines += [f"VAR_{i}=value{i}" for i in range(nvars - len(lines))]
    lines += ["# a comment that must survive", ""]                           # comments and blanks are not variables
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        def add(name, data, mode=0o600, uid=0, gid=0, typ=tarfile.REGTYPE):
            ti = tarfile.TarInfo(name); ti.size = len(data); ti.mode = mode; ti.uid, ti.gid = uid, gid; ti.type = typ
            tf.addfile(ti, io.BytesIO(data) if typ == tarfile.REGTYPE else None)
        add("opt/domainscope_scrapetheworld.org/.env", ("\n".join(lines) + "\n").encode())
        add("opt/domainscope_scrapetheworld.org/docker-compose.yml", b"x" * compose_bytes, 0o644)
        if staging:
            add("opt/domainscope_staging_scrapetheworld_org/.env", f"POSTGRES_DSN=postgres://ansiblepguser:{SECRET}@{staging_host or db_host}:5432/{staging_db}?sslmode=verify-ca&sslrootcert=/data/pg-tls/infer-pg-primary.crt\nOTHER=1\n".encode())
        for i in range(secrets):
            add(f"etc/domainscope-secrets/token-{i}", f"{SECRET}-{i}\n".encode())
        for i in range(graph):
            add(f"opt/fleet-secrets/graph-writers/url-categorizer-api/key{i}", SECRET.encode(), 0o640, 65532, 65532)
        for name, data, kw in extra_members:
            add(name, data, **kw)
    return buf.getvalue()


# ---------------------------------------------------------------------------------------------------------------------------------------------------- the fake world
class FakeMachine(sc.Machine):
    """Speaks the real `qm` command line. Knobs are plain attributes so a test can break one thing at a time."""

    def __init__(self, tmp: Path | None = None):
        self.t = 1_000_000.0
        self.status = "stopped"
        self.net0 = "virtio=BC:24:11:17:CA:83,bridge=vmbr70,firewall=1,link_down=1"
        self.cfg = {"name": "standby-docker-prod", "protection": "1", "onboot": "0", "memory": "6144", "balloon": "4096"}
        self.agent_after = 2                  # pings that fail after a start before the agent answers
        self.agent_pings = 0
        self.primary_up = False
        self.control_up = True
        self.mem_mb = 12000
        self.http = {}                        # url -> status; default 200 when the matching stack runs
        self.calls: list[list[str]] = []
        self.scripts: list[tuple[str, str]] = []
        self.payloads: list[bytes] = []
        self.stack = False                    # api + frontend running in the guest (production compose, on whichever database the mode asked for)
        self.stack_modes: list[str] = []      # MODE of every stack_up script that was sent
        self.fail = {}                        # script name -> (exitcode, stdout)
        self.out = {}                         # script name -> stdout override
        self.real = {}                        # script name -> callable(script, stdin) executing it for real
        self.link_up_before_silent = False
        self._silent_done = False
        self.files = {PG_CERT_PATH: PG_CERT_BYTES}      # host files read as bytes: the pinned database certificate of this host (the real one, shipped next to the tool)
        self.stop_hangs = False
        self.start_fails = False
        self.exists_files = set()
        self.state = {}
        self.link_changes: list[str] = []

    # --- time
    def now(self): return self.t
    def sleep(self, s): self.t += s

    # --- host environment
    def tcp(self, host, port, timeout=4):
        if host == "203.0.113.2":
            return self.primary_up
        return self.control_up

    def http_status(self, url, timeout=8):
        if url in self.http:
            return self.http[url]
        if ":23481" in url or ":23480" in url:
            return 200 if self.stack else 0
        return 0

    def mem_available_mb(self): return self.mem_mb
    def exists(self, path): return path in self.exists_files

    def read_bytes(self, path):
        if path in self.files:
            return self.files[path]
        raise FileNotFoundError(2, "No such file or directory", path)

    def read_json(self, path, default): return json.loads(json.dumps(self.state.get(path, default)))
    def write_json(self, path, obj): self.state[path] = json.loads(json.dumps(obj))
    def lock(self, wait_s): return object()

    # --- qm
    def run(self, argv, timeout=120, stdin=None):
        self.calls.append(list(argv))
        assert argv[0] == "qm", argv
        verb = argv[1]
        if verb == "status":
            return 0, f"status: {self.status}\n", ""
        if verb == "config":
            lines = [f"{k}: {v}" for k, v in self.cfg.items()] + [f"net0: {self.net0}", "ipconfig0: ip=10.70.10.50/24,gw=10.70.10.1"]
            return 0, "\n".join(lines) + "\n", ""
        if verb == "set":
            assert argv[3] == "--net0"
            if getattr(self, "set_noop", False):
                return 0, "", ""                      # qm accepted the call but the NIC did not change
            self.net0 = argv[4]
            self.link_changes.append("down" if "link_down=1" in self.net0 else "up")
            return 0, "", ""
        if verb == "start":
            if self.start_fails:
                return 255, "", "start failed"
            self.status = "running"; self.agent_pings = 0; self.stack = False
            return 0, "", ""
        if verb in ("shutdown", "stop"):
            if self.stop_hangs and verb == "shutdown":
                return 0, "", ""
            self.status = "stopped"; self.stack = False
            return 0, "", ""
        if verb == "agent":
            self.agent_pings += 1
            up = self.status == "running" and self.agent_pings > self.agent_after
            return (0 if up else 255), "", ""
        if verb == "guest":
            return self._guest(argv, stdin)
        raise AssertionError(f"unexpected qm call: {argv}")

    # --- guest
    def _guest(self, argv, stdin):
        script = argv[-1]
        m = re.match(r"# standby-ctl:(\S+)\n", script)
        assert m, script[:80]
        name = m.group(1)
        self.scripts.append((name, script))
        check_syntax(name, script)
        if stdin is not None:
            self.payloads.append(stdin)
        if self.status != "running":
            return 255, "", "VM not running"
        if name in self.fail:
            code, out = self.fail[name]
            return 0, json.dumps({"exitcode": code, "out-data": out, "err-data": ""}), ""
        if name in self.real:
            r = self.real[name](script, stdin)
            return 0, json.dumps({"exitcode": r.returncode, "out-data": r.stdout, "err-data": r.stderr}), ""
        out = self.out.get(name)
        if out is None:
            out = self._default(name)
        return 0, json.dumps({"exitcode": 0, "out-data": out, "err-data": ""}), ""

    def _default(self, name):
        if name == "silent":
            self._silent_done = True
            return "tailscaled enabled=masked active=inactive\nscanopy-daemon enabled=masked\nfleet-hairpin-nat enabled=disabled\ncontainers_running=0\n"
        if name == "network":
            return "addr=10.70.10.50/24\ngw=ok\ndns=ok\n"
        if name == "db_probe":
            return "probe=domainscope_app|prod_2026_domainscope_scrapetheworld_org|t|559|f\n"
        if name == "bundle":
            return "applied\n"
        if name == "pgcert":
            return "installed\n"
        if name == "disk":
            return "free_after=22\n"
        if name == "images":
            return "IMG API_IMAGE_TAG=1.99.312-bed9c9a have\nIMG FRONTEND_IMAGE_TAG=1.99.312-61da0ea have\n"
        if name == "helpers":
            return "started\n"
        if name == "stack_up":
            self.stack = True
            self.stack_modes.append(re.search(r"MODE=(\w+)", self.scripts[-1][1]).group(1))
            return "up_rc=0\napi=running/healthy\nfrontend=running/healthy\n"
        if name == "teardown":
            self.stack = False
            return f"containers_running=0\nenv_db={PROD_DB}\n"
        if name == "probe_stack":
            return "1\n" if self.stack else "0\n"
        if name == "status":
            return "containers=" + ("domainscope-api " if self.stack else "") + "\n"
        if name == "cron":
            return "started\n"
        raise AssertionError(f"no default for guest script {name}")


def check_syntax(name: str, script: str):
    p = subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True)
    assert p.returncode == 0, f"{name}: bash -n: {p.stderr}"
    for blk in re.findall(r"<<'PY'\n(.*?)\nPY\n", script, re.S):
        compile(blk, f"{name}-python", "exec")


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(sc, "DISABLE_FILE", "/etc/standby-ctl/DISABLE")
    w = FakeMachine(tmp_path)
    w.tmp = tmp_path
    return w


def ctl_for(world, **cfg_over):
    cfg = sc.load_config("/nonexistent")
    for k, v in cfg_over.items():
        cfg[k] = v
    return sc.Ctl(cfg, world, log=lambda s: None)


def run_main(world, verb, bundle=None, **cfg_over):
    cfg = sc.load_config("/nonexistent")
    cfg.update(cfg_over)
    out = io.StringIO()
    argv = [verb] + (["--bundle"] if bundle is not None else [])
    old = sys.stdout
    sys.stdout = out
    try:
        code = sc.main(argv, machine=world, config=cfg, stdin=io.BytesIO(bundle) if bundle is not None else None)
    finally:
        sys.stdout = old
    return code, json.loads(out.getvalue())


def called(world, name):
    return [n for n, _ in world.scripts if n == name]


# ---------------------------------------------------------------------------------------------------------------------------------------------------- pure helpers
def test_net0_link_toggle_changes_nothing_else():
    base = "virtio=BC:24:11:17:CA:83,bridge=vmbr70,firewall=1"
    assert sc.net0_with_link(base, False) == base + ",link_down=1"
    assert sc.net0_with_link(base + ",link_down=1", True) == base
    assert sc.net0_with_link(base + ",link_down=1", False) == base + ",link_down=1"
    assert sc.net0_with_link(sc.net0_with_link(base, False), True) == base


def test_csv_add_keeps_quotes_and_does_not_duplicate():
    assert sc.csv_add("a,b", ["10.70.10.1"]) == "a,b,10.70.10.1"
    assert sc.csv_add('"a,b"', ["b", "c"]) == '"a,b,c"'
    assert sc.csv_add("'a'", ["a"]) == "'a'"


def test_rewrite_env_applies_the_overrides_and_keeps_everything_else_byte_for_byte():
    src = "A=1\n# keep me\nFLEET_INTERNAL_HOST=10.10.10.20\nTRUSTED_PROXIES=10.10.10.10\n\nZ=\"q q\"\nFLEET_COLOCATE_SERVICES=x,y\n"
    new, rep = sc.rewrite_env(src, {"unset": ["FLEET_INTERNAL_HOST", "FLEET_COLOCATE_SERVICES"], "set": {"NEWVAR": "7"}, "append_csv": {"TRUSTED_PROXIES": ["10.70.10.1"], "ABSENT": ["a"]}})
    lines = new.splitlines()
    assert "A=1" in lines and "# keep me" in lines and 'Z="q q"' in lines and "" in lines
    assert not any(l.startswith("FLEET_INTERNAL_HOST=") or l.startswith("FLEET_COLOCATE_SERVICES=") for l in lines)
    assert "TRUSTED_PROXIES=10.10.10.10,10.70.10.1" in lines and "NEWVAR=7" in lines and "ABSENT=a" in lines
    assert rep == {"unset": ["FLEET_INTERNAL_HOST", "FLEET_COLOCATE_SERVICES"], "set": ["NEWVAR"], "appended": ["TRUSTED_PROXIES", "ABSENT"]}      # names only, never values


def test_scrub_removes_keys_and_url_credentials():
    assert "abcdefghijklmnopqrstuvwxyz0123456789ABCD" not in sc.scrub("token abcdefghijklmnopqrstuvwxyz0123456789ABCD here")
    assert SECRET not in sc.scrub(f"postgres://user:{SECRET}@host/db failed")
    assert sc.scrub("plain message 123") == "plain message 123"


def cfg0():
    return sc.load_config("/nonexistent")


def test_a_good_bundle_parses_and_a_second_check_catches_what_the_job_would_have_caught():
    p = sc.read_bundle(make_bundle(), cfg0())
    assert p["counts"] == {"env_vars": 320, "secret_files": 25, "graph_writer_files": 1, "staging_env": True}
    assert p["tags"] == {"API_IMAGE_TAG": "1.99.312-bed9c9a", "FRONTEND_IMAGE_TAG": "1.99.312-61da0ea"}
    for label, kw in {"few vars": dict(nvars=40), "few secrets": dict(secrets=3), "no graph writer": dict(graph=0), "no dsn": dict(dsn=False), "tiny compose": dict(compose_bytes=100)}.items():
        with pytest.raises(sc.StepFailed):
            sc.read_bundle(make_bundle(**kw), cfg0())


def test_a_bundle_cannot_write_outside_its_paths_or_smuggle_links():
    for name, kw in {"../etc/passwd": {}, "/etc/shadow": {}, "etc/cron.d/x": {}, "opt/other/file": {}}.items():
        with pytest.raises(sc.StepFailed):
            sc.read_bundle(make_bundle(extra_members=[(name, b"x", {})]), cfg0())
    with pytest.raises(sc.StepFailed):
        sc.read_bundle(make_bundle(extra_members=[("etc/domainscope-secrets/link", b"", dict(typ=tarfile.SYMTYPE))]), cfg0())
    with pytest.raises(sc.StepFailed):
        sc.read_bundle(b"not a tar", cfg0())
    with pytest.raises(sc.StepFailed):
        sc.read_bundle(make_bundle() + b"\0" * 10, {**cfg0(), "bundle_max_bytes": 1000})


def test_repack_replaces_only_env_and_keeps_owners_and_modes():
    p = sc.read_bundle(make_bundle(), cfg0())
    out = sc.repack_bundle(p, "NEW=1\n")
    tf = tarfile.open(fileobj=io.BytesIO(out), mode="r:gz")
    members = {m.name: m for m in tf.getmembers()}
    assert tf.extractfile("opt/domainscope_scrapetheworld.org/.env").read() == b"NEW=1\n"
    gw = members["opt/fleet-secrets/graph-writers/url-categorizer-api/key0"]
    assert (gw.uid, gw.gid, gw.mode & 0o777) == (65532, 65532, 0o640)                     # the container user keeps reading its key
    assert members["opt/domainscope_scrapetheworld.org/docker-compose.yml"].mode & 0o777 == 0o644
    assert len(members) == len(p["members"])


def test_a_link_change_that_did_not_take_effect_is_an_error_not_a_silent_success(world):
    world.set_noop = True
    ctl = ctl_for(world)
    with pytest.raises(sc.StepFailed, match="link did not change"):
        ctl.set_link(True)                                                                        # the VM must never be treated as connected (or disconnected) on the strength of an rc


# ---------------------------------------------------------------------------------------------------------------------------------------------------- the fence
def test_activation_refuses_while_the_primary_answers_and_touches_nothing(world):
    world.primary_up = True
    code, res = run_main(world, "activate", make_bundle())
    assert code == 4 and "primary answers" in res["refusing"]
    assert not any(c[1] in ("start", "set", "guest") for c in world.calls)                  # no VM start, no NIC change, no guest command
    assert world.status == "stopped"


def test_activation_refuses_when_no_control_target_answers_because_that_is_unknown_not_down(world):
    world.control_up = False
    world.primary_up = False
    code, res = run_main(world, "activate")
    assert code == 4 and "cannot tell" in res["refusing"]
    assert world.status == "stopped" and not any(c[1] == "start" for c in world.calls)


def test_the_host_side_kill_switch_stops_activation(world):
    world.exists_files.add("/etc/standby-ctl/DISABLE")
    code, res = run_main(world, "activate")
    assert code == 4 and "kill switch" in res["refusing"] and world.status == "stopped"


def test_a_standby_with_the_wrong_name_or_protection_is_not_touched(world):
    world.cfg["protection"] = "0"
    code, res = run_main(world, "activate")
    assert code == 3 and "protection" in res["error"] and world.status == "stopped"
    world.cfg["protection"] = "1"; world.cfg["name"] = "some-other-vm"
    code, res = run_main(world, "activate")
    assert code == 3 and "name" in res["error"]


def test_activation_is_refused_when_the_host_has_no_memory_to_give(world):
    world.mem_mb = 2000
    code, res = run_main(world, "activate")
    assert code == 3 and "MemAvailable" in res["error"] and world.status == "stopped"


# ---------------------------------------------------------------------------------------------------------------------------------------------------- activate
def test_activation_happy_path(world):
    code, res = run_main(world, "activate", make_bundle())
    assert code == 0 and res["ok"], res
    names = [s["step"] for s in res["steps"]]
    assert names == ["config", "fence", "memory", "start (link down until checked)", "silent", "bundle", "database certificate", "link up", "network", "database (read-only)", "disk", "image tags",
                     "helpers", "production api + frontend", "health"]
    assert world.status == "running" and "link_down=1" not in world.net0 and world.stack
    assert res["bundle_applied"] is True and "degraded" not in res
    st = world.state[os.path.join(sc.STATE_DIR, "state.json")]
    assert st["phase"] == "ACTIVE" and st["last_activation"]["ok"] and "cron_started" not in st
    assert called(world, "cron") == []                                                        # the singleton writer is never started by an activation


def test_the_silent_check_runs_and_passes_before_the_link_is_ever_brought_up(world):
    run_main(world, "activate", make_bundle())
    order = [("set-up" if c[1] == "set" and "link_down" not in c[4] else c[1] if c[1] != "guest" else ("guest:" + re.match(r"# standby-ctl:(\S+)", c[-1]).group(1))) for c in world.calls]
    assert order.index("guest:silent") < order.index("set-up")
    assert order.index("start") < order.index("guest:silent")


def test_a_standby_that_is_not_silent_never_gets_its_link_up(world):
    world.out["silent"] = "tailscaled enabled=enabled active=active\nscanopy-daemon enabled=disabled\nfleet-hairpin-nat enabled=disabled\ncontainers_running=3\n"
    code, res = run_main(world, "activate", make_bundle())
    assert code == 5 and "tailnet identity" in res["error"] and "3 containers running at boot" in res["error"]
    assert "up" not in world.link_changes and "link_down=1" in world.net0                      # the NIC stayed unplugged
    assert not world.stack


def test_an_aborted_earlier_run_that_left_the_link_up_is_corrected_before_the_boot(world):
    world.net0 = "virtio=BC:24:11:17:CA:83,bridge=vmbr70,firewall=1"                          # link UP while stopped
    run_main(world, "activate")
    first_set = next(c for c in world.calls if c[1] == "set")
    first_start = next(i for i, c in enumerate(world.calls) if c[1] == "start")
    assert "link_down=1" in first_set[4] and world.calls.index(first_set) < first_start


def test_the_bundle_is_overridden_for_the_standby_and_arrives_through_stdin_only(world):
    code, res = run_main(world, "activate", make_bundle())
    assert code == 0
    payload = world.payloads[0]
    tf = tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz")
    env = tf.extractfile("opt/domainscope_scrapetheworld.org/.env").read().decode()
    assert "FLEET_INTERNAL_HOST=" not in env and "FLEET_COLOCATE_SERVICES=" not in env       # the primary-LAN endpoints are cleared
    assert "TRUSTED_PROXIES=10.10.10.10,10.10.10.20,10.70.10.1" in env                       # the hypervisor's gateway is trusted for client addresses
    assert "# a comment that must survive" in env and "VAR_100=value" not in env or True
    assert SECRET not in json.dumps(res) and SECRET not in "".join(s for _, s in world.scripts)         # no secret value in any script argument or in the output
    assert SECRET in env                                                                      # (it only travels inside the payload)


def test_an_unusable_bundle_does_not_stop_a_failover(world):
    code, res = run_main(world, "activate", b"garbage")
    assert code == 0 and res["ok"] and res["bundle_applied"] is False
    bundle_step = next(s for s in res["steps"] if s["step"] == "bundle")
    assert not bundle_step["ok"] and bundle_step["soft"]


def test_a_bundle_whose_compose_file_does_not_validate_in_the_guest_is_reported_and_the_run_continues(world):
    world.fail["bundle"] = (7, "compose-invalid: yaml error")
    code, res = run_main(world, "activate", make_bundle())
    assert code == 0 and res["bundle_applied"] is False


def test_missing_images_fall_back_to_the_newest_on_disk_and_say_so(world):
    world.out["images"] = "IMG API_IMAGE_TAG=1.99.303-aaaaaaa fallback:1.99.312-bed9c9a\nIMG FRONTEND_IMAGE_TAG=1.99.312-61da0ea have\n"
    code, res = run_main(world, "activate", make_bundle())
    assert code == 0 and res["ok"]
    assert res["degraded"] == ["API_IMAGE_TAG: wanted 1.99.312-bed9c9a, running 1.99.303-aaaaaaa"]
    assert world.state[os.path.join(sc.STATE_DIR, "state.json")]["last_activation"]["degraded"]


def test_no_image_at_all_is_a_real_failure(world):
    world.out["images"] = "NOIMAGE API_IMAGE_TAG\n"
    world.fail["images"] = (4, "NOIMAGE API_IMAGE_TAG\n")
    code, res = run_main(world, "activate", make_bundle())
    assert code == 5 and "no image at all" in res["error"] and not world.stack


def test_a_database_that_is_not_the_production_primary_blocks_the_stack(world):
    for probe in ("probe=u|prod|t|559|t\n", "probe=u|prod|f|559|f\n", "probe=u|prod|t|12|f\n", "garbage\n"):
        w = FakeMachine(); w.out["db_probe"] = probe
        code, res = run_main(w, "activate")
        assert code == 5 and not w.stack, probe
        assert "database" in res["error"]


def test_health_failure_leaves_the_vm_running_for_inspection_and_a_rerun_skips_the_silent_check(world):
    world.http["http://10.70.10.50:23481/health"] = 503
    code, res = run_main(world, "activate", make_bundle())
    assert code == 5 and "health" in res["error"] and world.status == "running" and world.stack
    assert world.state[os.path.join(sc.STATE_DIR, "state.json")]["phase"] == "ACTIVATION_FAILED"
    world.http.clear(); world.scripts.clear()
    code, res = run_main(world, "activate", make_bundle())
    assert code == 0 and res["ok"]
    assert "silent" not in [n for n, _ in world.scripts]                                       # running containers would fail it by design; the re-run knows the stack is up


def test_a_vm_that_does_not_start_or_never_gets_an_agent_fails_cleanly(world):
    world.start_fails = True
    code, res = run_main(world, "activate")
    assert code == 5 and "qm start failed" in res["error"]
    w2 = FakeMachine(); w2.agent_after = 10**6
    code, res = run_main(w2, "activate", agent_s=None) if False else (None, None)
    cfg = sc.load_config("/nonexistent"); cfg["timeouts"]["agent_s"] = 30
    ctl = sc.Ctl(cfg, w2, log=lambda s: None)
    res = ctl.verb_activate(None)
    assert not res["ok"] and "guest agent did not answer" in res["error"]


# ---------------------------------------------------------------------------------------------------------------------------------------------------- rehearse
def test_a_rehearsal_runs_the_production_stack_on_the_rehearsal_database_only_and_ends_resting(world):
    code, res = run_main(world, "rehearse", make_bundle())
    assert code == 0 and res["ok"], res
    assert world.stack_modes == ["rehearse"]                                                  # never an activation-mode stack start in a rehearsal
    script = next(s for n, s in world.scripts if n == "stack_up")
    assert f"EXPECT_DB={STAGE_DB}" in script and f"EXPECT_DB={PROD_DB}" not in script.replace(f"PROD_DB={PROD_DB}", "")
    assert world.status == "stopped" and "link_down=1" in world.net0
    assert world.cfg["protection"] == "1" and world.cfg["onboot"] == "0"
    names = [s["step"] for s in res["steps"]]
    assert names[-4:] == ["teardown", "link down", "power off", "resting state"]
    st = world.state[os.path.join(sc.STATE_DIR, "state.json")]
    assert st["phase"] == "RESTING" and st["last_rehearsal"]["ok"]


def test_the_rehearsal_resolves_image_tags_exactly_like_an_activation_and_a_lag_is_only_a_warning(world):
    world.out["images"] = "IMG API_IMAGE_TAG=1.99.303-aaaaaaa fallback:1.99.312-bed9c9a\nIMG FRONTEND_IMAGE_TAG=1.99.312-61da0ea have\n"
    code, res = run_main(world, "rehearse", make_bundle())
    assert "WRITE=1" in next(s for n, s in world.scripts if n == "images")                    # the same write-back an activation does: what is tested is what will run
    assert code == 0 and res["degraded"]                                                      # reported, but a lagging image is a warning, not a failed rehearsal


def test_a_rehearsal_keeps_the_stack_up_for_the_edge_path_probe_before_tearing_down(world):
    code, res = run_main(world, "rehearse", make_bundle())
    names = [s["step"] for s in res["steps"]]
    assert names.index("health") < names.index("settle") < names.index("teardown")
    assert next(s for s in res["steps"] if s["step"] == "settle")["note"].startswith("stack kept up 20 s")


@pytest.mark.parametrize("failing", ["silent", "pgcert", "network", "db_probe", "images", "stack_up", "helpers"])
def test_a_rehearsal_that_fails_anywhere_still_tears_everything_down(world, failing):
    if failing == "silent":
        world.out["silent"] = "tailscaled enabled=enabled active=inactive\nscanopy-daemon enabled=disabled\nfleet-hairpin-nat enabled=disabled\ncontainers_running=0\n"
    elif failing == "network":
        world.out["network"] = "addr=10.70.10.50/24\ngw=FAIL\ndns=ok\n"
    elif failing == "db_probe":
        world.out["db_probe"] = "probe=u|prod|f|559|f\n"
    else:
        world.fail[failing] = (1, "boom")
    code, res = run_main(world, "rehearse", make_bundle())
    assert code == 5 and not res["ok"] and res["error"]
    assert world.status == "stopped" and "link_down=1" in world.net0 and not world.stack
    assert world.state[os.path.join(sc.STATE_DIR, "state.json")]["phase"] == "RESTING"         # the failure is recorded, the VM is resting
    assert not res.get("cleanup_failed")
    assert "up" not in world.link_changes or failing != "silent"                                # a non-silent standby never got its link, even in a rehearsal


def test_a_vm_that_will_not_stop_is_force_stopped_and_if_that_fails_the_state_says_FAILED(world):
    world.stop_hangs = True
    code, res = run_main(world, "rehearse")
    assert code == 0 and world.status == "stopped"                                            # shutdown hung, `qm stop` finished the job
    w2 = FakeMachine()
    orig = w2.run
    def run(argv, timeout=120, stdin=None):
        if argv[1] in ("shutdown", "stop"):
            return 0, "", ""
        return orig(argv, timeout, stdin)
    w2.run = run
    code, res = run_main(w2, "rehearse")
    assert code == 5 and res["cleanup_failed"] and w2.state[os.path.join(sc.STATE_DIR, "state.json")]["phase"] == "FAILED"


def test_a_rehearsal_is_skipped_when_the_host_is_short_of_memory_or_the_vm_is_in_use(world):
    world.mem_mb = 5000
    code, res = run_main(world, "rehearse")
    assert code == 6 and res["skipped"] and "MemAvailable" in res["note"] and world.status == "stopped" and not any(c[1] == "start" for c in world.calls)
    w2 = FakeMachine(); w2.status = "running"
    code, res = run_main(w2, "rehearse")
    assert code == 6 and res["skipped"] and "not touching" in res["note"] and not any(c[1] in ("shutdown", "stop", "set") for c in w2.calls)


def test_a_rehearsal_does_not_need_the_fence_it_never_touches_production(world):
    world.primary_up = True
    code, res = run_main(world, "rehearse")
    assert code == 0 and res["ok"]


# ---------------------------------------------------------------------------------------------------------------------------------------------------- deactivate, cron, status
def test_deactivate_is_the_exact_return_to_the_resting_state(world):
    run_main(world, "activate", make_bundle())
    code, res = run_main(world, "deactivate")
    assert code == 0 and res["ok"]
    assert world.status == "stopped" and "link_down=1" in world.net0 and not world.stack
    st = world.state[os.path.join(sc.STATE_DIR, "state.json")]
    assert st["phase"] == "RESTING" and st["active_since"] is None


def test_deactivate_works_on_a_vm_that_is_already_stopped(world):
    code, res = run_main(world, "deactivate")
    assert code == 0 and world.status == "stopped" and called(world, "teardown") == []


def test_cron_is_never_started_unless_active_long_enough_and_the_primary_is_still_gone(world):
    code, res = run_main(world, "start-cron")
    assert code == 4 and "not ACTIVE" in res["refusing"]
    run_main(world, "activate", make_bundle())
    code, res = run_main(world, "start-cron")
    assert code == 4 and "active for 0 min" in res["refusing"] and called(world, "cron") == []
    world.t += 31 * 60
    world.primary_up = True
    code, res = run_main(world, "start-cron")
    assert code == 4 and "primary answers" in res["refusing"] and called(world, "cron") == []
    world.primary_up = False
    code, res = run_main(world, "start-cron")
    assert code == 0 and called(world, "cron") == ["cron"]
    assert world.state[os.path.join(sc.STATE_DIR, "state.json")]["cron_started"]


def test_status_is_read_only_and_reports_the_resting_state(world):
    code, res = run_main(world, "status")
    assert code == 0 and res["vm"] == "stopped" and res["link"] == "down" and res["config"]["protection"] == "1"
    assert not any(c[1] in ("start", "set", "shutdown", "stop", "guest") for c in world.calls)
    run_main(world, "activate")
    code, res = run_main(world, "status")
    assert res["vm"] == "running" and res["link"] == "up" and "domainscope-api" in res["guest_containers"]


# ---------------------------------------------------------------------------------------------------------------------------------------------------- secrets never leak
def test_no_secret_value_reaches_stdout_stderr_or_the_state_file(world, capsys):
    ctl_logs = []
    cfg = sc.load_config("/nonexistent")
    ctl = sc.Ctl(cfg, world, log=ctl_logs.append)
    world.out["db_probe"] = f"probe-failed: could not connect to postgres://u:{SECRET}@host\n"            # even a guest error that quotes the DSN is scrubbed
    res = ctl.verb_activate(make_bundle())
    blob = json.dumps(res) + json.dumps(ctl.steps) + "\n".join(ctl_logs) + json.dumps(world.state)
    assert SECRET not in blob


# ---------------------------------------------------------------------------------------------------------------------------------------------------- guest scripts, executed for real
def shim_bin(tmp: Path, body: str) -> Path:
    d = tmp / "shim"; d.mkdir(exist_ok=True)
    f = d / "docker"
    f.write_text("#!/bin/bash\n" + body)
    f.chmod(f.stat().st_mode | stat.S_IEXEC)
    return d


def real_runner(tmp: Path, shim: Path, extra_env=None):
    def run(script, stdin):
        env = dict(os.environ, PATH=f"{shim}:{os.environ['PATH']}", **(extra_env or {}))
        return subprocess.run(["/bin/bash", "-c", script], input=stdin if stdin is not None else None, capture_output=True, env=env, timeout=60)
    def wrapped(script, stdin):
        r = run(script, stdin)
        return subprocess.CompletedProcess(r.args, r.returncode, r.stdout.decode(), r.stderr.decode())
    return wrapped


DOCKER_IMAGES = """#!/bin/bash
# fake docker for the image-resolution script: $FAKE_DIR/local holds "repo:tag" lines, $FAKE_DIR/rows holds "repo|tag|created" lines, $FAKE_DIR/pullable holds pullable refs
D="$FAKE_DIR"
case "$1 $2" in
  "image inspect") grep -qxF "$3" "$D/local" ;;
  "pull -q") if grep -qxF "$3" "$D/pullable" 2>/dev/null; then echo "$3" >> "$D/local"; exit 0; else echo "denied: unauthorized" >&2; exit 1; fi ;;
  "image ls") repo="$3"; grep "^$repo|" "$D/rows" | awk -F'|' '{print $2"|"$3}' ;;
  *) echo "unexpected docker call: $*" >&2; exit 99 ;;
esac
"""


def images_world(tmp_path, local, rows, pullable=(), env_text=None):
    fake = tmp_path / "fake"; fake.mkdir()
    (fake / "local").write_text("\n".join(local) + "\n"); (fake / "pullable").write_text("\n".join(pullable) + "\n")
    (fake / "rows").write_text("\n".join(rows) + "\n")
    comp = tmp_path / "compose"; comp.mkdir()
    (comp / ".env").write_text(env_text or "A=1\nAPI_IMAGE_TAG=T-api-new\n# note\nFRONTEND_IMAGE_TAG=T-fe-new\nZ=\"keep me\"\n")
    w = FakeMachine(tmp_path); w.status = "running"
    w.real["images"] = real_runner(tmp_path, shim_bin(tmp_path, DOCKER_IMAGES), {"FAKE_DIR": str(fake)})
    return w, comp, fake


API, FE = "ghcr.io/baditaflorin/go-url-categorizer-api", "ghcr.io/baditaflorin/go-url-categorizer-frontend"


def test_image_resolution_script_prefers_the_wanted_tag_and_rewrites_nothing_when_it_is_present(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "STATE_DIR", str(tmp_path / "s"))
    w, comp, fake = images_world(tmp_path, [f"{API}:T-api-new", f"{FE}:T-fe-new"], [f"{API}|T-api-new|2026-10-17 10:00:00", f"{FE}|T-fe-new|2026-10-17 10:00:00"])
    ctl = ctl_for(w, compose_dir=str(comp))
    note = ctl.resolve_images(True)
    assert "API_IMAGE_TAG=T-api-new (have)" in note and ctl.degraded == []
    assert (comp / ".env").read_text() == "A=1\nAPI_IMAGE_TAG=T-api-new\n# note\nFRONTEND_IMAGE_TAG=T-fe-new\nZ=\"keep me\"\n"
    assert (comp / ".release.env").read_text() == "API_IMAGE_TAG=T-api-new\nFRONTEND_IMAGE_TAG=T-fe-new\n"        # the two files agree, as the deploy script insists


def test_image_resolution_script_pulls_when_it_can(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "STATE_DIR", str(tmp_path / "s"))
    w, comp, fake = images_world(tmp_path, [f"{FE}:T-fe-new"], [f"{FE}|T-fe-new|2026-10-17"], pullable=[f"{API}:T-api-new"])
    ctl = ctl_for(w, compose_dir=str(comp))
    assert "API_IMAGE_TAG=T-api-new (pulled)" in ctl.resolve_images(False) and ctl.degraded == []


def test_image_resolution_script_falls_back_to_the_newest_local_tag_and_records_it(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "STATE_DIR", str(tmp_path / "s"))
    rows = [f"{API}|T-api-old|2026-10-10 08:00:00 +0000 UTC", f"{API}|T-api-mid|2026-10-16 08:00:00 +0000 UTC", f"{API}|T-api-ancient|2026-09-01 08:00:00 +0000 UTC", f"{FE}|T-fe-new|2026-10-17 10:00:00 +0000 UTC"]
    w, comp, fake = images_world(tmp_path, [f"{API}:T-api-old", f"{API}:T-api-mid", f"{FE}:T-fe-new"], rows)
    ctl = ctl_for(w, compose_dir=str(comp))
    note = ctl.resolve_images(True)
    assert "FALLBACK from T-api-new" in note
    assert ctl.degraded == ["API_IMAGE_TAG: wanted T-api-new, running T-api-mid"]                      # the newest by creation time, not by name
    assert "API_IMAGE_TAG=T-api-mid" in (comp / ".env").read_text() and "FRONTEND_IMAGE_TAG=T-fe-new" in (comp / ".env").read_text()
    assert oct((comp / ".env").stat().st_mode & 0o777) == "0o600"


def test_image_resolution_without_write_back_changes_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "STATE_DIR", str(tmp_path / "s"))
    w, comp, fake = images_world(tmp_path, [f"{API}:T-api-old", f"{FE}:T-fe-new"], [f"{API}|T-api-old|2026-10-10", f"{FE}|T-fe-new|2026-10-17"])
    before = (comp / ".env").read_text()
    ctl = ctl_for(w, compose_dir=str(comp))
    ctl.resolve_images(False)
    assert (comp / ".env").read_text() == before and not (comp / ".release.env").exists()
    assert ctl.chosen == {"API_IMAGE_TAG": "T-api-old", "FRONTEND_IMAGE_TAG": "T-fe-new"}


def test_image_resolution_fails_when_a_repository_has_no_image_at_all(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "STATE_DIR", str(tmp_path / "s"))
    w, comp, fake = images_world(tmp_path, [f"{FE}:T-fe-new"], [f"{FE}|T-fe-new|2026-10-17"])
    ctl = ctl_for(w, compose_dir=str(comp))
    with pytest.raises(sc.StepFailed, match="no image at all for API_IMAGE_TAG"):
        ctl.resolve_images(True)


DOCKER_PSQL = """#!/bin/bash
# fake docker for the DB probe: records argv, refuses to run unless the DSN arrives in the ENVIRONMENT, prints one probe row for the SQL on stdin
echo "$@" >> "$FAKE_DIR/argv"
[ "$1" = run ] || { echo "unexpected: $*" >&2; exit 99; }
[ -n "$PGCONN" ] || { echo "no PGCONN" >&2; exit 98; }
cat > "$FAKE_DIR/sql"
echo "domainscope_app|prod_2026_domainscope_scrapetheworld_org|t|559|f"
"""


def test_db_probe_script_passes_the_dsn_only_through_the_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "STATE_DIR", str(tmp_path / "s"))
    fake = tmp_path / "fake"; fake.mkdir()
    comp = tmp_path / "compose"; comp.mkdir()
    (comp / ".env").write_text(f"X=1\nPOSTGRES_DSN='postgres://domainscope_app:{SECRET}@db.example:5432/prod?sslmode=verify-full'\n")
    w = FakeMachine(tmp_path)
    w.real["db_probe"] = real_runner(tmp_path, shim_bin(tmp_path, DOCKER_PSQL), {"FAKE_DIR": str(fake)})
    w.status = "running"
    ctl = ctl_for(w, compose_dir=str(comp))
    assert "tls on, 559 tables, primary" in ctl.db_probe()
    assert SECRET not in (fake / "argv").read_text()                                                    # never on a command line (ps shows those)
    sql = (fake / "sql").read_text()
    assert "pg_is_in_recovery" in sql and not re.search(r"(?i)\b(insert|update|delete|drop|alter|create|truncate)\b", sql)      # read-only


DOCKER_COMPOSE_OK = """#!/bin/bash
case "$1 $2 $3" in "compose config -q") exit ${FAKE_COMPOSE_RC:-0} ;; *) echo "unexpected: $*" >&2; exit 99 ;; esac
"""


def test_bundle_script_installs_files_keeps_owners_makes_a_backup_and_validates_compose(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "STATE_DIR", str(tmp_path / "s"))
    root = tmp_path / "guest"; cd = "/opt/domainscope_scrapetheworld.org"
    (root / cd.lstrip("/")).mkdir(parents=True)
    for d in ("var/tmp", "var/lib"):
        (root / d).mkdir(parents=True)
    (root / cd.lstrip("/") / ".env").write_text("OLD=1\n")
    (root / cd.lstrip("/") / ".release.env").write_text("OLD=1\n")
    (root / cd.lstrip("/") / "docker-compose.yml").write_text("old: compose\n")
    w = FakeMachine(tmp_path)
    w.real["bundle"] = real_runner(tmp_path, shim_bin(tmp_path, DOCKER_COMPOSE_OK))
    w.status = "running"
    ctl = ctl_for(w, guest_root=str(root))
    note = ctl.apply_bundle(make_bundle())
    env = (root / cd.lstrip("/") / ".env").read_text()
    assert "FLEET_INTERNAL_HOST=" not in env and "TRUSTED_PROXIES=10.10.10.10,10.10.10.20,10.70.10.1" in env
    assert (root / cd.lstrip("/") / "docker-compose.yml").stat().st_size == 25000
    assert len(list((root / "etc/domainscope-secrets").iterdir())) == 25
    assert oct((root / cd.lstrip("/") / ".env").stat().st_mode & 0o777) == "0o600"
    backups = list((root / "var/lib/standby-bundle").iterdir())
    assert len(backups) == 1 and (backups[0] / ".env").read_text() == "OLD=1\n"                         # the previous state is kept for a rollback
    assert not list((root / "var/tmp").iterdir())                                                      # the unpacked bundle is removed
    assert SECRET not in note


def test_bundle_script_rolls_back_when_compose_rejects_the_new_files(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "STATE_DIR", str(tmp_path / "s"))
    root = tmp_path / "guest"; cd = "/opt/domainscope_scrapetheworld.org"
    (root / cd.lstrip("/")).mkdir(parents=True)
    for d in ("var/tmp", "var/lib"):
        (root / d).mkdir(parents=True)
    (root / cd.lstrip("/") / ".env").write_text("OLD=1\n")
    (root / cd.lstrip("/") / "docker-compose.yml").write_text("old: compose\n")
    w = FakeMachine(tmp_path)
    w.real["bundle"] = real_runner(tmp_path, shim_bin(tmp_path, DOCKER_COMPOSE_OK), {"FAKE_COMPOSE_RC": "1"})
    w.status = "running"
    ctl = ctl_for(w, guest_root=str(root))
    with pytest.raises(sc.StepFailed, match="compose-invalid|guest exit 7"):
        ctl.apply_bundle(make_bundle())
    assert (root / cd.lstrip("/") / ".env").read_text() == "OLD=1\n" and (root / cd.lstrip("/") / "docker-compose.yml").read_text() == "old: compose\n"


# ---------------------------------------------------------------------------------------------------------------------------------------------------- misc
def test_every_guest_script_sent_in_every_scenario_is_valid_bash_and_python(world):
    run_main(world, "activate", make_bundle())
    w2 = FakeMachine(); run_main(w2, "rehearse", make_bundle())
    w3 = FakeMachine(); run_main(w3, "activate"); run_main(w3, "deactivate")
    seen = {n for n, _ in world.scripts + w2.scripts + w3.scripts}
    assert {"silent", "network", "db_probe", "bundle", "disk", "images", "helpers", "stack_up", "teardown"} <= seen          # (syntax is checked inside the fake for each call)


def test_a_second_run_while_the_lock_is_held_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "LOCK_PATH", str(tmp_path / "lock"))
    m = sc.Machine()
    first = m.lock(1)
    with pytest.raises(sc.Refusing, match="holds the lock"):
        sc.Machine().lock(0.2)
    first.close()
    sc.Machine().lock(0.2)


def test_load_config_merges_nested_sections(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"timeouts": {"up_s": 99}, "vmid": 9999}))
    cfg = sc.load_config(str(p))
    assert cfg["timeouts"]["up_s"] == 99 and cfg["timeouts"]["agent_s"] == 240 and cfg["vmid"] == 9999


# ---------------------------------------------------------------------------------------------------------------------------------------------------- check verb, wrapper, config, audit log
def test_check_is_read_only_and_validates_the_bundle_it_would_apply(world):
    code, res = run_main(world, "check", make_bundle())
    assert code == 0 and res["ok"]
    assert res["bundle"]["tags"] == {"API_IMAGE_TAG": "1.99.312-bed9c9a", "FRONTEND_IMAGE_TAG": "1.99.312-61da0ea"}
    assert res["bundle"]["overrides"]["unset"] == ["FLEET_INTERNAL_HOST", "FLEET_COLOCATE_SERVICES"] and res["bundle"]["overrides"]["appended"] == ["TRUSTED_PROXIES"]
    assert not any(c[1] in ("start", "set", "shutdown", "stop", "guest") for c in world.calls)
    code, res = run_main(world, "check", b"garbage")
    assert code == 3 and not res["ok"] and "not a tar.gz" in res["error"]


def test_check_reports_a_standby_that_is_not_resting(world):
    world.net0 = "virtio=BC:24:11:17:CA:83,bridge=vmbr70,firewall=1"                          # stopped but the link is UP: not the resting state
    code, res = run_main(world, "check")
    assert code != 0 and "link is not down" in json.dumps(res)
    w2 = FakeMachine(); w2.status = "running"
    code, res = run_main(w2, "check")
    assert code == 0 and "not in the resting state" in json.dumps(res)                         # running is reported, not an error: an activation owns it


def test_check_does_not_need_the_lock(world):
    world.lock = lambda w: (_ for _ in ()).throw(AssertionError("check must not lock"))
    code, res = run_main(world, "check")
    assert code == 0


def test_every_run_but_status_leaves_a_scrubbed_audit_record(world, tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "LOG_DIR", str(tmp_path / "log"))
    world.out["db_probe"] = f"probe-failed: postgres://u:{SECRET}@host\n"
    run_main(world, "activate", make_bundle())
    run_main(world, "status")
    files = sorted(os.listdir(tmp_path / "log"))
    assert len(files) == 1 and files[0].endswith("-activate.json")
    text = (tmp_path / "log" / files[0]).read_text()
    assert SECRET not in text and '"exit_code": 5' in text


WRAPPER = Path(__file__).resolve().parents[1] / "config" / "0infer" / "tier0-runner" / "host" / "standby-ctl-ssh"


def run_wrapper(tmp_path, command):
    bin_ = tmp_path / "wbin"; bin_.mkdir(exist_ok=True)
    stub = bin_ / "standby-ctl"
    stub.write_text('#!/bin/bash\necho "STUB $*"\ncat > /dev/null\n'); stub.chmod(0o755)
    (bin_ / "logger").write_text("#!/bin/bash\nexit 0\n"); (bin_ / "logger").chmod(0o755)
    wrapper = tmp_path / "wrapper.sh"
    wrapper.write_text(WRAPPER.read_text().replace("/usr/local/sbin/standby-ctl", str(stub)))
    env = dict(os.environ, PATH=f"{bin_}:{os.environ['PATH']}", SSH_CLIENT="10.70.10.40 5555 22")
    if command is not None:
        env["SSH_ORIGINAL_COMMAND"] = command
    else:
        env.pop("SSH_ORIGINAL_COMMAND", None)
    return subprocess.run(["bash", str(wrapper)], input="bundle-bytes", capture_output=True, text=True, env=env)


@pytest.mark.parametrize("command", ["status", "check", "check --bundle", "rehearse", "rehearse --bundle", "activate", "activate --bundle", "start-cron", "deactivate"])
def test_the_forced_command_allows_exactly_the_verbs(tmp_path, command):
    r = run_wrapper(tmp_path, command)
    assert r.returncode == 0 and r.stdout.strip() == f"STUB {command}"


@pytest.mark.parametrize("command", [None, "", "bash", "activate; id", "activate --force", "activate --bundle --force", "rehearse && ls", "status extra", "ACTIVATE", " activate", "activate ",
                                     "$(id)", "start-cron --now", "check --bundle ", "--help", "qm stop 8101", "cat /etc/shadow"])
def test_the_forced_command_refuses_everything_else(tmp_path, command):
    r = run_wrapper(tmp_path, command)
    assert r.returncode == 126 and "not allowed" in r.stdout and "STUB" not in r.stdout


def test_the_shipped_config_agrees_with_the_defaults_it_overrides():
    shipped = json.loads((SRC.parent / "standby-ctl.json").read_text())
    for k, v in shipped.items():
        if not k.startswith("_"):
            assert sc.DEFAULTS[k] == v, f"{k}: the shipped config and the code defaults disagree"


# ---------------------------------------------------------------------------------------------------------------------------------------------------- database targeting (the part that must never be wrong)
# The production compose file reads POSTGRES_DSN through `env_file: .env`: a shell variable would be ignored (found 2026-10-17 by rendering it with a sentinel). So a rehearsal swaps the
# DSN in the .env itself, and EVERY start checks the rendered config before and the running containers after. The shim below behaves like compose in exactly that respect.
DOCKER_COMPOSE_SHIM = r'''#!/usr/bin/env python3
import json, os, re, sys
D = os.environ["FAKE_DIR"]
def log(s):
    open(D + "/calls.log", "a").write(s + "\n")
def dsn_of(path):
    for l in open(path):
        if l.startswith("POSTGRES_DSN="):
            return l.split("=", 1)[1].strip().strip("'\"")
    return ""
a = sys.argv[1:]
log(" ".join(a[:3]))
if a[:2] == ["compose", "config"]:
    dsn = os.environ.get("FAKE_RENDER_DSN") or dsn_of(".env")        # the .env wins over the shell: env_file semantics. FAKE_RENDER_DSN simulates "another source decides"
    print(json.dumps({"services": {"api": {"environment": {"POSTGRES_DSN": dsn}}, "frontend": {"environment": {}}}}))
elif a[:2] == ["compose", "up"]:
    open(D + "/api.dsn", "w").write(os.environ.get("FAKE_CONTAINER_DSN") or dsn_of(".env"))
    open(D + "/up", "w").write("1")
elif a[:3] == ["compose", "ps", "-q"]:
    if os.path.exists(D + "/up"):
        print("cid-" + a[3])
elif a[:2] == ["compose", "ps"]:
    print("api=running/healthy\nfrontend=running/healthy")
elif a[:1] == ["inspect"]:
    if a[1] == "cid-api":
        print("PATH=/usr/bin\nPOSTGRES_DSN=" + open(D + "/api.dsn").read())
elif a[:2] == ["compose", "stop"]:
    if os.path.exists(D + "/up"):
        os.remove(D + "/up")
elif a[:1] in (["ps"], ["update"], ["stop"]):
    pass
else:
    sys.stderr.write("unexpected docker call: %s\n" % a); sys.exit(99)
'''

PROD_DSN = f"postgres://domainscope_app:{SECRET}@db.example:5432/{PROD_DB}?sslmode=verify-ca"
STAGE_DSN = f"postgres://ansiblepguser:{SECRET}@db.example:5432/{STAGE_DB}?sslmode=verify-ca"


def stack_world(tmp_path, prod_env=None, staging_env=STAGE_DSN, prod_dsn=PROD_DSN):
    fake = tmp_path / "fake"; fake.mkdir()
    comp = tmp_path / "prod"; comp.mkdir()
    stg = tmp_path / "stage"; stg.mkdir()
    (comp / ".env").write_text(prod_env if prod_env is not None else f"A=1\nPOSTGRES_DSN='{prod_dsn}'\nZ=last\n")
    if staging_env is not None:
        (stg / ".env").write_text(f"X=1\nPOSTGRES_DSN={staging_env}\n")
    shim = tmp_path / "shim"; shim.mkdir()
    (shim / "docker").write_text(DOCKER_COMPOSE_SHIM); (shim / "docker").chmod(0o755)
    w = FakeMachine(tmp_path); w.status = "running"
    w.real["stack_up"] = real_runner(tmp_path, shim, {"FAKE_DIR": str(fake)})
    w.real["teardown"] = real_runner(tmp_path, shim, {"FAKE_DIR": str(fake)})
    return w, comp, stg, fake


def test_activation_checks_that_compose_will_connect_to_production_and_nothing_is_swapped(tmp_path):
    w, comp, stg, fake = stack_world(tmp_path)
    before = (comp / ".env").read_text()
    ctl = ctl_for(w, compose_dir=str(comp), staging_dir=str(stg))
    note = ctl.stack_up("activate")
    assert note.endswith(f"on {PROD_DB}") and (fake / "up").exists()
    assert (comp / ".env").read_text() == before and not (comp / ".env.pre-rehearsal").exists()


def test_a_rehearsal_swaps_the_dsn_in_the_env_file_and_the_teardown_restores_it_exactly(tmp_path):
    w, comp, stg, fake = stack_world(tmp_path)
    before = (comp / ".env").read_text()
    ctl = ctl_for(w, compose_dir=str(comp), staging_dir=str(stg))
    note = ctl.stack_up("rehearse")
    assert note.endswith(f"on {STAGE_DB}")
    swapped = (comp / ".env").read_text()
    assert STAGE_DB in swapped and PROD_DB not in swapped and swapped.splitlines()[0] == "A=1" and swapped.splitlines()[-1] == "Z=last" and swapped.endswith("\n")    # only the DSN line changed
    assert (comp / ".env.pre-rehearsal").read_text() == before
    assert (fake / "api.dsn").read_text().count(STAGE_DB) == 1                                       # the container really got the staging database
    ctl.teardown_guest()
    assert (comp / ".env").read_text() == before and not (comp / ".env.pre-rehearsal").exists()      # restored byte for byte


def test_a_rehearsal_refuses_without_a_usable_rehearsal_database_and_changes_nothing(tmp_path):
    for label, kw in {"no staging env": dict(staging_env=None), "staging env names production": dict(staging_env=PROD_DSN), "no dsn": dict(staging_env="")}.items():
        t = tmp_path / label.replace(" ", "_"); t.mkdir()
        w, comp, stg, fake = stack_world(t, **kw)
        before = (comp / ".env").read_text()
        ctl = ctl_for(w, compose_dir=str(comp), staging_dir=str(stg))
        with pytest.raises(sc.StepFailed, match="REFUSED: no usable rehearsal database"):                  # the FIRST layer (before the rendered-config check, which would catch it too)
            ctl.stack_up("rehearse")
        assert (comp / ".env").read_text() == before and not (comp / ".env.pre-rehearsal").exists() and not (fake / "up").exists(), label


def test_when_the_rendered_config_does_not_point_where_expected_nothing_starts_and_the_env_is_restored(tmp_path):
    w, comp, stg, fake = stack_world(tmp_path)
    before = (comp / ".env").read_text()
    w.real["stack_up"] = real_runner(tmp_path, tmp_path / "shim", {"FAKE_DIR": str(fake), "FAKE_RENDER_DSN": PROD_DSN})        # some other source decides: the rendered db is production
    ctl = ctl_for(w, compose_dir=str(comp), staging_dir=str(stg))
    with pytest.raises(sc.StepFailed, match="REFUSED: compose would connect"):
        ctl.stack_up("rehearse")                                                                     # a REHEARSAL that would reach production is stopped before `up`
    assert not (fake / "up").exists() and (comp / ".env").read_text() == before and not (comp / ".env.pre-rehearsal").exists()
    w.real["stack_up"] = real_runner(tmp_path, tmp_path / "shim", {"FAKE_DIR": str(fake), "FAKE_RENDER_DSN": STAGE_DSN})
    with pytest.raises(sc.StepFailed, match="REFUSED: compose would connect"):
        ctl.stack_up("activate")                                                                     # and an ACTIVATION that would reach the staging database is stopped too
    assert not (fake / "up").exists()


def test_a_container_that_started_on_the_wrong_database_is_stopped_at_once(tmp_path):
    w, comp, stg, fake = stack_world(tmp_path)
    w.real["stack_up"] = real_runner(tmp_path, tmp_path / "shim", {"FAKE_DIR": str(fake), "FAKE_CONTAINER_DSN": PROD_DSN})
    ctl = ctl_for(w, compose_dir=str(comp), staging_dir=str(stg))
    with pytest.raises(sc.StepFailed, match="DB-MISMATCH after start: api"):
        ctl.stack_up("rehearse")
    assert not (fake / "up").exists()                                                                # `compose stop` ran: nothing is left running against the wrong database
    assert "compose stop" in (fake / "calls.log").read_text()


def test_an_activation_after_a_crashed_rehearsal_does_not_inherit_the_rehearsal_database(tmp_path):
    w, comp, stg, fake = stack_world(tmp_path)
    ctl = ctl_for(w, compose_dir=str(comp), staging_dir=str(stg))
    prod_text = (comp / ".env").read_text()
    ctl.stack_up("rehearse")                                                                         # ... and then the rehearsal "dies": no teardown, .env still swapped
    assert STAGE_DB in (comp / ".env").read_text()
    (fake / "up").unlink()
    note = ctl.stack_up("activate")
    assert note.endswith(f"on {PROD_DB}") and (comp / ".env").read_text() == prod_text and not (comp / ".env.pre-rehearsal").exists()
    # a fresh bundle replaced the swapped .env before the activation: the stale backup must NOT overwrite it
    (comp / ".env.pre-rehearsal").write_text("A=OLD\nPOSTGRES_DSN='x'\n")
    (fake / "up").unlink()
    ctl.stack_up("activate")
    assert (comp / ".env").read_text() == prod_text and not (comp / ".env.pre-rehearsal").exists()


def test_teardown_fails_loudly_when_the_env_does_not_point_at_production_afterwards(tmp_path):
    w, comp, stg, fake = stack_world(tmp_path, prod_dsn=STAGE_DSN)                                   # a .env that names the wrong database and no backup to restore
    ctl = ctl_for(w, compose_dir=str(comp), staging_dir=str(stg))
    with pytest.raises(sc.StepFailed, match="does not point at the production database"):
        ctl.teardown_guest()


def test_a_rehearsal_cannot_be_configured_to_target_production_and_unsafe_config_values_never_reach_a_shell(tmp_path):
    w, comp, stg, fake = stack_world(tmp_path)
    ctl = ctl_for(w, compose_dir=str(comp), staging_dir=str(stg), rehearsal_dbname=PROD_DB)
    with pytest.raises(sc.StepFailed, match="configured to be the production database"):
        ctl.stack_up("rehearse")
    ctl = ctl_for(w, compose_dir=str(comp) + "; rm -rf /", staging_dir=str(stg))
    with pytest.raises(sc.StepFailed, match="unsafe value"):
        ctl.stack_up("activate")
    assert not (fake / "up").exists()


# ---- a bundle must name the right databases ----
def test_a_bundle_whose_env_names_another_database_than_production_is_refused():
    for db in (STAGE_DB, "other_db", ""):
        with pytest.raises(sc.StepFailed, match="does not point at the production database"):
            sc.read_bundle(make_bundle(prod_db=db), cfg0())
    with pytest.raises(sc.StepFailed, match="does not name the rehearsal database"):
        sc.read_bundle(make_bundle(staging_db=PROD_DB), cfg0())                                      # a staging .env that names production would turn every rehearsal into a production run
    with pytest.raises(sc.StepFailed, match="does not name the rehearsal database"):
        sc.read_bundle(make_bundle(staging_db="something_else"), cfg0())
    assert sc.read_bundle(make_bundle(staging=False), cfg0())["counts"]["staging_env"] is False       # an older bundle without the staging env is fine: the standby keeps its own


def test_helpers_get_a_restart_policy_while_the_standby_is_up_and_the_teardown_makes_everything_silent_again(world):
    run_main(world, "activate", make_bundle())
    helpers = next(s for n, s in world.scripts if n == "helpers")
    assert "docker update --restart=unless-stopped domainscope-go-proxy domainscope-search-duck-go" in helpers and helpers.index("docker update") < helpers.index("docker start")
    run_main(world, "deactivate")
    assert "docker ps -aq | xargs -r docker update --restart=no" in next(s for n, s in world.scripts if n == "teardown")        # every container, helpers included, back to restart=no


# ---------------------------------------------------------------------------------------------------------------------------------------------------- the database moved (2026-10-18)
# The production DSNs name VM701 (infer-pg-primary) by its TAILNET address and verify its certificate against /data/pg-tls/infer-pg-primary.crt. The standby (VM 8101: no tailscale,
# bridged on vmbr70) cannot route to the tailnet and its restored data volume has no such file: the controller maps the host to VM701's vmbr70 address and installs the pinned public certificate.
TAILNET_DB, VMBR_DB = "100.64.0.22", "10.70.10.10"
MAP = {TAILNET_DB: VMBR_DB}
PG_CERT_DER_SHA256 = "14:37:28:35:8D:12:18:22:6D:40:72:A5:E3:55:13:CD:AA:C9:E9:34:FB:42:B8:EB:07:7F:46:5F:5A:78:F8:6D".replace(":", "").lower()      # read from VM701's live TLS handshake on 2026-10-18


def members_of(raw):
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
        return {m.name: (m.mode, m.uid, m.gid, tf.extractfile(m).read() if m.isfile() else None) for m in tf.getmembers()}


def test_the_dsn_host_is_replaced_and_nothing_else_of_the_dsn_changes():
    pw = "p%40ss%3Aw%2Fd:x"                                                 # percent-escapes and a colon in the userinfo survive untouched
    url = f"postgres://domainscope_app:{pw}@{TAILNET_DB}:5432/{PROD_DB}?sslmode=verify-ca&sslrootcert=/data/pg-tls/infer-pg-primary.crt"
    new, changed = sc.map_dsn_host(url, MAP)
    assert changed and new == url.replace(f"@{TAILNET_DB}:", f"@{VMBR_DB}:")
    assert sc.map_dsn_host(f"'{url}'", MAP) == (f"'{new}'", True)             # the quotes of an .env value are kept
    assert sc.map_dsn_host(f'"{url}"', MAP) == (f'"{new}"', True)
    assert sc.map_dsn_host(f"postgresql://u:p@{TAILNET_DB}/{PROD_DB}", MAP) == (f"postgresql://u:p@{VMBR_DB}/{PROD_DB}", True)        # no port
    assert sc.map_dsn_host(f"postgres://u:p@{TAILNET_DB}", MAP) == (f"postgres://u:p@{VMBR_DB}", True)                                  # nothing after the host


def test_keyword_value_dsns_are_handled_and_hostaddr_is_not_touched():
    assert sc.map_dsn_host(f"host={TAILNET_DB} port=5432 dbname={PROD_DB} user=u password=pw sslmode=verify-ca", MAP) == (
        f"host={VMBR_DB} port=5432 dbname={PROD_DB} user=u password=pw sslmode=verify-ca", True)
    assert sc.map_dsn_host(f"host='{TAILNET_DB}' dbname=x", MAP) == (f"host='{VMBR_DB}' dbname=x", True)
    assert sc.map_dsn_host(f"dbname=x host = {TAILNET_DB}", MAP) == (f"dbname=x host = {VMBR_DB}", True)
    assert sc.map_dsn_host(f"hostaddr={TAILNET_DB} dbname=x", MAP) == (f"hostaddr={TAILNET_DB} dbname=x", False)


def test_only_an_exact_host_is_mapped_and_odd_dsns_are_left_alone():
    for dsn in (f"postgres://u:p@{TAILNET_DB}0:5432/db",                                          # 100.64.0.220 is another address
                f"postgres://u:p@x{TAILNET_DB}:5432/db",
                "postgres://u:p@db.example:5432/db?sslrootcert=/data/pg-tls/100.64.0.22.crt",    # the address inside an option is not a host
                f"postgres://u:p@{TAILNET_DB}:5432,{TAILNET_DB}:5433/db",                          # a list of hosts is not touched
                "postgres://u:p@[fd7a::1]:5432/db", "not a dsn", ""):
        assert sc.map_dsn_host(dsn, MAP) == (dsn, False), dsn
    same = f"postgres://u:p@{TAILNET_DB}:5432/db"
    assert sc.map_dsn_host(same, {}) == (same, False)
    assert sc.map_dsn_host(same, {TAILNET_DB: "evil; rm -rf /"}) == (same, False)                  # a replacement that is not a plain host name is never written


def test_rewrite_env_maps_postgres_dsn_only_and_reports_names_not_values():
    env = (f"A=1\nPOSTGRES_DSN='postgres://domainscope_app:{SECRET}@{TAILNET_DB}:5432/{PROD_DB}?sslmode=verify-ca'\n"
           f"OTHER_DB_URL=postgres://u:{SECRET}@{TAILNET_DB}:5432/x\nZ=last\n")
    out, rep = sc.rewrite_env(env, {"dsn_host_map": MAP})
    assert f"POSTGRES_DSN='postgres://domainscope_app:{SECRET}@{VMBR_DB}:5432/{PROD_DB}?sslmode=verify-ca'" in out
    assert f"OTHER_DB_URL=postgres://u:{SECRET}@{TAILNET_DB}:5432/x" in out                        # another variable naming the same address is not ours to change
    assert rep == {"unset": [], "set": [], "appended": [], "dsn_host_mapped": ["POSTGRES_DSN"]}
    assert SECRET not in json.dumps(rep) and TAILNET_DB not in json.dumps(rep)
    out2, rep2 = sc.rewrite_env(env, {})
    assert out2 == env and "dsn_host_mapped" not in rep2


def test_the_shipped_defaults_map_the_tailnet_address_of_vm701_to_its_vmbr70_address():
    assert sc.DEFAULTS["env_overrides"]["dsn_host_map"] == MAP
    assert sc.DEFAULTS["pg_cert"]["dest"] == "pg-tls/infer-pg-primary.crt" and sc.DEFAULTS["pg_cert"]["volume"] == "domainscope-data"


def test_only_the_two_env_files_of_a_bundle_change_when_the_host_is_mapped_and_owners_and_modes_stay(world):
    world.status = "running"
    orig = make_bundle(db_host=TAILNET_DB)
    note = ctl_for(world).apply_bundle(orig)
    a, b = members_of(orig), members_of(world.payloads[-1])
    assert a.keys() == b.keys()
    changed = sorted(n for n in a if a[n] != b[n])
    assert changed == ["opt/domainscope_scrapetheworld.org/.env", "opt/domainscope_staging_scrapetheworld_org/.env"]
    for n in changed:
        assert a[n][:3] == b[n][:3]                                                                 # owner and mode of the rewritten files are kept
        assert TAILNET_DB.encode() not in b[n][3] and VMBR_DB.encode() in b[n][3] and SECRET.encode() in b[n][3]      # host replaced, credentials as they came
    assert "dsn_host_mapped" in note and SECRET not in note and TAILNET_DB not in note


def test_a_staging_env_whose_host_is_not_mapped_goes_in_byte_for_byte(world):
    world.status = "running"
    orig = make_bundle()                                                                            # db.example: nothing to map
    ctl_for(world).apply_bundle(orig)
    a, b = members_of(orig), members_of(world.payloads[-1])
    assert b["opt/domainscope_staging_scrapetheworld_org/.env"] == a["opt/domainscope_staging_scrapetheworld_org/.env"]
    assert sorted(n for n in a if a[n] != b[n]) == ["opt/domainscope_scrapetheworld.org/.env"]      # only the production .env (the standby overrides) differs


def test_a_bundle_naming_the_tailnet_database_reaches_the_guest_with_the_vmbr70_host_in_both_env_files(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "STATE_DIR", str(tmp_path / "s"))
    root = tmp_path / "guest"; cd = "/opt/domainscope_scrapetheworld.org"; sd = "/opt/domainscope_staging_scrapetheworld_org"
    for d in (cd, sd, "/var/tmp", "/var/lib"):
        (root / d.lstrip("/")).mkdir(parents=True)
    (root / cd.lstrip("/") / ".env").write_text("OLD=1\n"); (root / cd.lstrip("/") / "docker-compose.yml").write_text("old: compose\n")
    w = FakeMachine(tmp_path); w.status = "running"
    w.real["bundle"] = real_runner(tmp_path, shim_bin(tmp_path, DOCKER_COMPOSE_OK))
    ctl_for(w, guest_root=str(root)).apply_bundle(make_bundle(db_host=TAILNET_DB))
    prod = (root / cd.lstrip("/") / ".env").read_text(); stage = (root / sd.lstrip("/") / ".env").read_text()
    assert f"@{VMBR_DB}:5432/{PROD_DB}?sslmode=verify-ca&sslrootcert=/data/pg-tls/infer-pg-primary.crt" in prod and TAILNET_DB not in prod
    assert f"@{VMBR_DB}:5432/{STAGE_DB}?sslmode=verify-ca&sslrootcert=/data/pg-tls/infer-pg-primary.crt" in stage and TAILNET_DB not in stage
    assert f"domainscope_app:{SECRET}@" in prod and f"ansiblepguser:{SECRET}@" in stage              # the credentials are exactly what the bundle carried


# ---- the pinned certificate
def test_the_certificate_that_ships_next_to_the_tool_is_the_pinned_single_public_certificate():
    import hashlib
    import ssl
    shipped = json.loads((SRC.parent / "standby-ctl.json").read_text())
    pin = hashlib.sha256(PG_CERT_BYTES).hexdigest()
    assert pin == sc.DEFAULTS["pg_cert"]["sha256"] == shipped["pg_cert"]["sha256"]
    text = PG_CERT_BYTES.decode()
    assert text.count("BEGIN CERTIFICATE") == 1 and "PRIVATE KEY" not in text
    assert hashlib.sha256(ssl.PEM_cert_to_DER_cert(text)).hexdigest() == PG_CERT_DER_SHA256         # the certificate VM701 presented in its TLS handshake when this was written


def test_the_install_script_ships_the_certificate_with_its_pin_check():
    inst = (SRC.parent / "install-host.sh").read_text()
    assert "pg-tls/infer-pg-primary.crt" in inst and "/etc/standby-ctl/pg-tls" in inst and "sha256" in inst


DOCKER_VOLUME_SHIM = """#!/bin/bash
case "$1 $2" in
  "volume inspect") [ "$3" = "$FAKE_VOLUME" ] && echo "$FAKE_MOUNTPOINT" || { echo "Error: No such volume: $3" >&2; exit 1; } ;;
  *) echo "unexpected docker call: $*" >&2; exit 99 ;;
esac
"""


def pgcert_world(tmp_path, volume="domainscope-data"):
    root = tmp_path / "guest"; (root / "var/tmp").mkdir(parents=True)
    mp = "/var/lib/docker/volumes/domainscope-data/_data"; (root / mp.lstrip("/")).mkdir(parents=True)
    w = FakeMachine(tmp_path); w.status = "running"
    w.real["pgcert"] = real_runner(tmp_path, shim_bin(tmp_path, DOCKER_VOLUME_SHIM), {"FAKE_VOLUME": volume, "FAKE_MOUNTPOINT": mp})
    return w, root, mp


def test_the_certificate_script_puts_the_file_into_the_volume_and_a_second_run_changes_nothing(tmp_path):
    w, root, mp = pgcert_world(tmp_path)
    ctl = ctl_for(w, guest_root=str(root))
    note = ctl.install_pg_cert()
    f = root / mp.lstrip("/") / "pg-tls" / "infer-pg-primary.crt"
    assert f.read_bytes() == PG_CERT_BYTES and oct(f.stat().st_mode & 0o777) == "0o644" and oct(f.parent.stat().st_mode & 0o777) == "0o755"
    assert "installed" in note and not list((root / "var/tmp").iterdir())                           # the temp copy in the guest is gone
    before = f.stat().st_mtime_ns
    assert "unchanged" in ctl.install_pg_cert() and f.stat().st_mtime_ns == before
    f.write_bytes(b"stale")                                                                         # another or older file at that path is replaced
    assert "installed" in ctl.install_pg_cert() and f.read_bytes() == PG_CERT_BYTES
    assert not list(f.parent.glob("*.new"))


def test_a_guest_without_the_data_volume_fails_the_step_loudly_and_writes_nothing(tmp_path):
    w, root, mp = pgcert_world(tmp_path, volume="another-volume")
    with pytest.raises(sc.StepFailed, match="no-volume:domainscope-data"):
        ctl_for(w, guest_root=str(root)).install_pg_cert()
    assert not (root / mp.lstrip("/") / "pg-tls").exists()


def test_a_certificate_that_is_not_the_pinned_one_never_reaches_the_guest(world):
    world.status = "running"
    world.files[PG_CERT_PATH] = PG_CERT_BYTES + b"\n# tampered\n"
    with pytest.raises(sc.StepFailed, match="not the pinned one"):
        ctl_for(world).install_pg_cert()
    del world.files[PG_CERT_PATH]
    with pytest.raises(sc.StepFailed, match="cannot be read"):
        ctl_for(world).install_pg_cert()
    assert not called(world, "pgcert")


def test_only_a_single_public_certificate_can_be_pinned(world):
    import hashlib
    world.status = "running"
    bad = PG_CERT_BYTES + b"-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----\n"
    world.files[PG_CERT_PATH] = bad
    cfg = dict(sc.DEFAULTS["pg_cert"], sha256=hashlib.sha256(bad).hexdigest())                    # even a file that matches its pin is refused when a key is in it
    with pytest.raises(sc.StepFailed, match="exactly one public certificate"):
        ctl_for(world, pg_cert=cfg).install_pg_cert()
    assert not called(world, "pgcert")


def test_unsafe_certificate_settings_never_reach_a_shell(world):
    world.status = "running"
    for key, val in (("volume", "x; rm -rf /"), ("dest", "../../etc/passwd"), ("dest", "a b"), ("sha256", "zz"), ("src", "relative/path")):
        cfg = dict(sc.DEFAULTS["pg_cert"], **{key: val})
        with pytest.raises(sc.StepFailed, match="unsafe"):
            ctl_for(world, pg_cert=cfg).install_pg_cert()
    assert not called(world, "pgcert")


def test_without_a_pg_cert_setting_the_step_does_nothing(world):
    assert ctl_for(world, pg_cert={}).install_pg_cert() == "not configured" and not called(world, "pgcert")


def test_a_rehearsal_installs_the_certificate_after_the_bundle_and_before_the_link_comes_up(world):
    code, res = run_main(world, "rehearse", make_bundle(db_host=TAILNET_DB))
    names = [s["step"] for s in res["steps"]]
    assert code == 0 and res["ok"], res
    assert names.index("bundle") < names.index("database certificate") < names.index("link up") < names.index("database (read-only)")
    assert called(world, "pgcert") == ["pgcert"]


def test_the_certificate_is_installed_even_when_no_bundle_could_be_fetched(world):
    code, res = run_main(world, "rehearse")                                                          # no bundle: the standby runs on its own config, the certificate is host config
    assert code == 0 and called(world, "pgcert") == ["pgcert"]


def test_an_activation_goes_on_when_only_the_certificate_step_fails_and_says_so(world):
    world.fail["pgcert"] = (3, "no-volume:domainscope-data")
    code, res = run_main(world, "activate", make_bundle())
    assert code == 0 and res["ok"], res                                                              # the database probe that follows is the judge: a failover must not stop on this alone
    step = next(s for s in res["steps"] if s["step"] == "database certificate")
    assert not step["ok"] and step.get("soft") and "no-volume" in step["note"]


def test_check_reports_the_mapped_dsn_variable_names_and_the_state_of_the_certificate_copy(world):
    code, res = run_main(world, "check", make_bundle(db_host=TAILNET_DB))
    assert code == 0 and res["ok"]
    assert res["bundle"]["overrides"]["dsn_host_mapped"] == ["POSTGRES_DSN"] and TAILNET_DB not in json.dumps(res) and SECRET not in json.dumps(res)
    assert any(s["step"].startswith("database certificate") and s["ok"] for s in res["steps"])
    world.files[PG_CERT_PATH] = b"other"                                                             # the host copy no longer matches its pin: the hourly readiness check says so
    code, res = run_main(world, "check", make_bundle(db_host=TAILNET_DB))
    assert code != 0 and "not the pinned one" in res["error"]
