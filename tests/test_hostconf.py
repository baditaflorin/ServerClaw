"""hostconf: host-local configuration kept in git (scripts/hostconf.py, config/hostconf).

Why it exists (2026-10-19): the systemd drop-ins that make nginx restart and Postgres survive an OOM kill, the Postgres log_connections setting and
the sysctl file that raises kernel.threads-max on VMs with hot-plugged memory lived on the hosts only. Nobody could review them, a rebuilt VM would
lose them and a hand edit would change them without a trace. The VMs that carry hot-plugged memory had a thread limit of about 7000 (the kernel sizes
it once, at boot, from the ~1 GB it sees then): a container start storm after a reboot hit it and 22 containers came up without a network endpoint.

Pinned here: what the tool may write (a fixed allowlist of paths, not the manifest), that nothing credential-like is accepted, that a drift check never
changes a host, that an apply writes atomically, keeps the previous file, reloads but never restarts, verifies the setting is in effect and rolls back
when it is not, and that the manifest shipped in the repo is valid. The remote script is executed for real against a temporary root with fake
systemctl / sysctl / psql commands, so the apply and rollback paths are exercised, not mocked.
"""
from __future__ import annotations

import base64
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import socket
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "hostconf.py"
spec = importlib.util.spec_from_file_location("hostconf", SCRIPT)
hostconf = importlib.util.module_from_spec(spec)
sys.modules["hostconf"] = hostconf
spec.loader.exec_module(hostconf)

HERE = socket.gethostname()
NGINX = "# keep nginx up after an OOM kill\n[Service]\nRestart=on-failure\nOOMPolicy=continue\n"
THREADS = "# thread limit\nkernel.threads-max = 131072\n"
PGLOG = "# log connections\nlog_connections = 'receipt,authorization'\n"
TAILSCALE = "[Unit]\nAfter=tailscaled.service\nWants=tailscaled.service\n"

FAKE = r'''#!@@PYTHON@@ -S
# a fake systemctl / sysctl / pg_lsclusters / pg_ctlcluster / runuser for the tests: it keeps "what the system has loaded" under $HOSTCONF_ROOT/state
# (-S and no heavy imports: every apply starts a dozen of these)
import os, sys
ROOT = os.environ["HOSTCONF_ROOT"]
STATE = os.path.join(ROOT, "state")
name = os.path.basename(sys.argv[0])
args = sys.argv[1:]
with open(os.path.join(ROOT, "calls.log"), "a") as fh:
    fh.write(name + " " + " ".join(args) + "\n")


def read(p, default=""):
    try:
        return open(p).read()
    except OSError:
        return default


def write(p, v):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(v)


def confs(d):
    try:
        return [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".conf")]
    except OSError:
        return []


def rmtree(d):
    for base, dirs, files in os.walk(d, topdown=False):
        for f in files:
            os.unlink(os.path.join(base, f))
        for x in dirs:
            os.rmdir(os.path.join(base, x))
    if os.path.isdir(d):
        os.rmdir(d)


def copytree(src, dst):
    for base, dirs, files in os.walk(src):
        target = os.path.join(dst, os.path.relpath(base, src))
        os.makedirs(target, exist_ok=True)
        for f in files:
            write(os.path.join(target, f), read(os.path.join(base, f)))


def settings(path):
    out = {}
    for line in read(path).splitlines():
        line = line.strip()
        if line and not line.startswith(("#", ";")) and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip("'\"")
    return out


if name == "systemctl":
    if args[0] == "daemon-reload":
        corrupt = os.environ.get("FAKE_CORRUPT_ON_SECOND_RELOAD")
        if corrupt and sum(1 for l in open(os.path.join(ROOT, "calls.log")) if l.startswith("systemctl daemon-reload")) >= 2:
            write(os.path.join(ROOT, corrupt.lstrip("/")), "something else wrote here\n")  # as if the restored file were changed again
        if os.environ.get("FAKE_FAIL_RELOAD"):
            sys.exit(1)
        if not os.environ.get("FAKE_NOEFFECT"):
            dst = os.path.join(STATE, "loaded")
            rmtree(dst)
            src = os.path.join(ROOT, "etc/systemd/system")
            if os.path.isdir(src):
                copytree(src, dst)
        sys.exit(0)
    if args[0] == "show":
        unit, prop = args[1], args[2].split("=")[1]
        values = []
        for f in confs(os.path.join(STATE, "loaded", unit + ".d")):
            for line in read(f).splitlines():
                if line.startswith(prop + "="):
                    values.append(line.split("=", 1)[1])
        base = read(os.path.join(STATE, "default-" + prop), "")
        if prop in ("After", "Before", "Wants", "Requires"):
            print(" ".join(([base] if base else []) + values))
        else:
            print(values[-1] if values else base)
        sys.exit(0)
elif name == "sysctl":
    if args[0] == "-n":
        v = read(os.path.join(STATE, "sysctl", args[1]), None)
        if v is None:
            sys.exit(1)
        print(v.strip())
    elif args[0] == "-p":
        if os.environ.get("FAKE_SYSCTL_IGNORE"):
            sys.exit(0)
        for k, v in settings(args[1]).items():
            write(os.path.join(STATE, "sysctl", k), v)
    elif args[0] == "-w":
        k, v = args[1].split("=", 1)
        write(os.path.join(STATE, "sysctl", k), v)
    sys.exit(0)
elif name == "pg_lsclusters":
    print("18  main 5432 online postgres /var/lib/postgresql/18/main /var/log/postgresql/postgresql-18-main.log")
    sys.exit(0)
elif name == "pg_ctlcluster":
    version, cluster, action = args[0], args[1], args[2]
    if os.environ.get("FAKE_FAIL_PG"):
        sys.exit(1)
    for f in confs(os.path.join(ROOT, "etc/postgresql", version, cluster, "conf.d")):
        for k, v in settings(f).items():
            write(os.path.join(STATE, "pg", k), v)
    sys.exit(0)
elif name == "pvesh":
    answer = read(os.path.join(STATE, "pvesh.json"), None)
    if answer is None:
        sys.exit(1)
    sys.stdout.write(answer)
    sys.exit(0)
elif name == "qm":
    if args[0] == "list":
        print("      VMID NAME                 STATUS     MEM(MB)    BOOTDISK(GB) PID")
        for line in read(os.path.join(STATE, "qm-list.txt")).splitlines():
            vmid, vmname, status = line.split()
            print("%10s %-20s %-10s %8s %15s %7s" % (vmid, vmname, status, 1024, "32.00", 1234))
        sys.exit(0)
    if args[0] == "config":
        sys.stdout.write(read(os.path.join(STATE, "qm-config-" + args[1] + ".txt"), "name: x\n"))
        sys.exit(0)
elif name == "pct":
    if args[0] == "list":
        print("VMID       Status     Lock         Name")
        for line in read(os.path.join(STATE, "pct-list.txt")).splitlines():
            ctid, status, ctname = line.split()
            print("%-10s %-10s %-12s %s" % (ctid, status, "", ctname))
        sys.exit(0)
elif name == "runuser":
    sql = args[-1]
    if sql.startswith("SHOW "):
        print(read(os.path.join(STATE, "pg", sql[5:]), "").strip())
    else:
        print(read(os.path.join(STATE, "pg-pending"), "").strip())
    sys.exit(0)
sys.exit(2)
'''


@pytest.fixture()
def world(tmp_path, monkeypatch):
    """Two hosts (h1: nginx drop-in + thread limit, h2: a Postgres file), each with its own fake root, and a repo files directory."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for cmd in ("systemctl", "sysctl", "pg_lsclusters", "pg_ctlcluster", "runuser", "qm", "pct", "pvesh"):
        p = bin_dir / cmd
        p.write_text(FAKE.replace("@@PYTHON@@", sys.executable))
        p.chmod(0o755)
    files = tmp_path / "files"
    files.mkdir()
    (files / "nginx.conf").write_text(NGINX)
    (files / "threads.conf").write_text(THREADS)
    (files / "pg.conf").write_text(PGLOG)
    manifest = {
        "version": 1,
        "files": {
            "nginx-restart": {
                "dest": "/etc/systemd/system/nginx.service.d/override.conf", "src": "nginx.conf",
                "purpose": "nginx restarts after it dies and survives an OOM kill",
                "expect": [{"systemd": "nginx.service", "property": "Restart", "value": "on-failure"},
                           {"systemd": "nginx.service", "property": "OOMPolicy", "value": "continue"}],
            },
            "threads": {
                "dest": "/etc/sysctl.d/90-threads.conf", "src": "threads.conf",
                "purpose": "a thread limit that does not depend on the memory seen at boot",
                "expect": [{"sysctl": "kernel.threads-max", "value": "131072"}],
            },
            "pg-log": {
                "dest": "/etc/postgresql/18/main/conf.d/97-log-connections.conf", "src": "pg.conf", "mode": "0640",
                "purpose": "log every connection so a burst of new connections can be traced",
                "expect": [{"pg_setting": "log_connections", "cluster": "18/main", "value": "receipt,authorization"}],
            },
        },
        "hosts": {
            "h1": {"ssh": "h1", "hostname": HERE, "files": ["nginx-restart", "threads"]},
            "h2": {"ssh": "h2", "hostname": HERE, "files": ["pg-log"]},
        },
    }
    manifest_path = tmp_path / "hostconf.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest))
    monkeypatch.setattr(hostconf, "FILES_DIR", files)
    roots = {}
    for h in ("h1", "h2"):
        root = tmp_path / f"root-{h}"
        (root / "state" / "sysctl").mkdir(parents=True)
        (root / "state" / "sysctl" / "kernel.threads-max").write_text("7016\n")
        (root / "state" / "default-Restart").write_text("no\n")
        (root / "state" / "default-OOMPolicy").write_text("stop\n")
        roots[h] = root
    env: dict[str, str] = {}

    calls_seen: list[tuple] = []

    def runner(alias, script, timeout, sudo=True, via=None):
        calls_seen.append((alias, sudo, via))
        key = alias if via is None else f"{alias}#{via}"  # a guest reached through its hypervisor's agent has a root of its own
        p = subprocess.run([sys.executable, "-"], input=script, capture_output=True, text=True,
                           env=dict(os.environ, HOSTCONF_ROOT=str(roots[key]), PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}", **env))
        return p.returncode, p.stdout, p.stderr

    class World:
        pass

    w = World()
    w.tmp, w.files, w.manifest, w.manifest_path, w.roots, w.runner, w.env, w.calls_seen = tmp_path, files, manifest, manifest_path, roots, runner, env, calls_seen
    w.dest = lambda host, d: roots[host] / d.lstrip("/")
    w.calls = lambda host: (roots[host] / "calls.log").read_text().splitlines() if (roots[host] / "calls.log").exists() else []
    w.main = lambda *argv: hostconf.main(["--manifest", str(manifest_path), *argv], runner=runner)
    return w


def load(w):
    return hostconf.load_manifest(w.manifest_path)


# ───────────────────────────── what may be written ─────────────────────────────


@pytest.mark.parametrize("dest,kind", [
    ("/etc/systemd/system/nginx.service.d/override.conf", "systemd_dropin"),
    ("/etc/systemd/system/postgresql@18-main.service.d/20-oom-policy.conf", "systemd_dropin"),
    ("/etc/systemd/system/lv3-tailscale-proxy-gitea.socket.d/10-no-default-deps.conf", "systemd_dropin"),
    ("/etc/systemd/system/sys-subsystem-net-devices-tailscale0.device.d/10-wants-woodpecker-exec-proxy.conf", "systemd_dropin"),  # a device unit: its Wants= starts a socket bound to it when it comes back
    ("/etc/sysctl.d/90-memory-hotplug-threads.conf", "sysctl"),
    ("/etc/postgresql/18/main/conf.d/97-log-connections.conf", "pg_conf_d"),
])
def test_the_paths_the_tool_may_write(dest, kind):
    assert hostconf.kind_of(dest) == kind


@pytest.mark.parametrize("dest", [
    "/etc/passwd", "/etc/sudoers.d/90-x", "/root/.ssh/authorized_keys", "/etc/cron.d/x", "/etc/hosts",
    "/etc/systemd/system/nginx.service", "/etc/systemd/system/nginx.service.d/override.conf.bak-hostconf-20261019T120000Z",
    "/etc/systemd/system/nginx.service.d/../../../shadow.conf", "/etc/systemd/system/nginx.service.d//override.conf",
    "/etc/systemd/system/nginx.d/override.conf", "/etc/systemd/system/a/b.service.d/override.conf",
    "/etc/sysctl.d/threads.conf", "/etc/sysctl.conf", "/etc/sysctl.d/90-x.conf.bak",
    "/etc/postgresql/18/main/postgresql.conf", "/etc/postgresql/18/main/pg_hba.conf", "/etc/postgresql/18/main/conf.d/notnumbered.conf",
    "etc/sysctl.d/90-x.conf", "",
])
def test_everything_else_is_refused(dest):
    assert hostconf.kind_of(dest) is None


def test_the_remote_script_enforces_the_same_allowlist_whatever_the_manifest_says(world):
    """The check is repeated on the host: a spec that names /etc/passwd (a tampered manifest) is refused before any write."""
    host = load(world)["hosts"]["h1"]
    evil = hostconf.host_files(load(world), "h1")[0]
    evil.update(dest="/etc/passwd", kind="sysctl")
    code, out, _ = world.runner("h1", hostconf.build_script("apply", host, [evil]), 60)
    res = json.loads(out.split("HOSTCONF_RESULT ")[1])
    assert code == 1 and "not a path hostconf may write" in res["refused"]
    assert not (world.roots["h1"] / "etc" / "passwd").exists()


# ───────────────────────────── what a file may contain ─────────────────────────────


@pytest.mark.parametrize("text", [
    "[Service]\nPASSWORD=hunter2\n", "[Service]\nEnvironment=API_TOKEN=abc\n", "[Service]\nEnvironment=\"DB_PASSWORD=x\"\n",
    "# token: s3cr3t\n[Service]\nRestart=no\n", "[Service]\nExecStart=/bin/x --api-key=abc123\n", "[Service]\nEnvironment=URL=https://user:pw@host/x\n",
    "# -----BEGIN OPENSSH PRIVATE KEY-----\n[Service]\nRestart=no\n", "[Service]\nEnvironment=TS=tskey-auth-abcdef123456\n",
    "[Service]\nEnvironment=GH=ghp_abcdefghijklmnopqrstuvwxyz0123\n", "[Service]\nPGPASSWORD=x\n",
])
def test_a_file_that_looks_like_it_holds_a_credential_is_refused(text):
    problems = hostconf.content_problems("systemd_dropin", text.encode())
    assert any("credential" in p for p in problems), problems


def test_a_systemd_credential_path_is_not_mistaken_for_a_credential_but_an_inline_one_is():
    ok = "[Service]\nLoadCredential=observer:/etc/aivoicebus/observer-token\nImportCredential=ssh.*\n"
    assert hostconf.content_problems("systemd_dropin", ok.encode()) == []
    for bad in ("[Service]\nSetCredential=observer:hunter2\n", "[Service]\nCredential=x\n", "[Service]\nEnvironment=CREDENTIAL=abc\n"):
        assert any("credential" in p for p in hostconf.content_problems("systemd_dropin", bad.encode())), bad


@pytest.mark.parametrize("kind,text", [
    ("pg_conf_d", "password_encryption = scram-sha-256\nssl = on\n"),
    ("pg_conf_d", "log_connections = 'receipt,authorization'\n"),
    ("systemd_dropin", "[Service]\nRestart=on-failure\nTimeoutStartSec=300\n"),
    ("sysctl", "kernel.threads-max = 131072\nvm.max_map_count=1048576\n"),
])
def test_ordinary_settings_with_credential_like_words_are_not_mistaken_for_one(kind, text):
    assert hostconf.content_problems(kind, text.encode()) == []


@pytest.mark.parametrize("kind,data,needle", [
    ("systemd_dropin", b"[Service]\nRestart=no", "newline"),
    ("systemd_dropin", b"[Service]\r\nRestart=no\r\n", "NUL or CR"),
    ("systemd_dropin", b"# only a comment\n", "no setting"),
    ("systemd_dropin", b"Restart=no\n", "before any [Section]"),
    ("systemd_dropin", b"[Service]\nthis is not a setting\n", "not a Key=Value"),
    ("systemd_dropin", b"[Bogus]\nRestart=no\n", "before any [Section]"),
    ("sysctl", b"kernel.threads-max = 1\nkernel.threads-max = 2\n", "set twice"),
    ("sysctl", b"not a setting\n", "name = value"),
    ("pg_conf_d", b"just words\n", "name = value"),
    ("sysctl", b"\xff\xfe\n", "not UTF-8"),
    pytest.param("sysctl", b"kernel.threads-max = 1\n" + b"# x\n" * 6000, "larger than", id="too-big"),
])
def test_content_shapes_the_target_would_not_parse_are_refused(kind, data, needle):
    problems = hostconf.content_problems(kind, data)
    assert any(needle in p for p in problems), problems


def test_a_systemd_continuation_line_is_part_of_the_previous_setting():
    text = "[Service]\nExecStartPre=/bin/sh -c 'a; \\\n  b; \\\n  c'\n"
    assert hostconf.content_problems("systemd_dropin", text.encode()) == []


# ───────────────────────────── the manifest ─────────────────────────────


def problems(w, mutate):
    m = load(w)
    mutate(m)
    return hostconf.manifest_problems(m, w.files)


def test_the_test_world_is_valid(world):
    assert problems(world, lambda m: None) == []


@pytest.mark.parametrize("label,mutate,needle", [
    ("unknown file id", lambda m: m["hosts"]["h1"]["files"].append("nope"), "unknown file id"),
    ("dest outside the allowlist", lambda m: m["files"]["threads"].update(dest="/etc/hosts"), "not a path this tool may write"),
    ("no purpose", lambda m: m["files"]["threads"].update(purpose="short"), "purpose"),
    ("bad mode", lambda m: m["files"]["threads"].update(mode="0777"), "mode must be one of"),
    ("src missing", lambda m: m["files"]["threads"].update(src="gone.conf"), "does not exist"),
    ("src escapes", lambda m: m["files"]["threads"].update(src="../x"), "relative path"),
    ("no expect", lambda m: m["files"]["threads"].pop("expect"), "at least one setting"),
    ("expect of the wrong kind", lambda m: m["files"]["threads"].update(expect=[{"systemd": "nginx.service", "property": "Restart", "value": "no"}]), "is proven by a sysctl"),
    ("sysctl value differs from the file", lambda m: m["files"]["threads"].update(expect=[{"sysctl": "kernel.threads-max", "value": "7000"}]), "but the expectation is 7000"),
    ("sysctl key not in the file", lambda m: m["files"]["threads"].update(expect=[{"sysctl": "kernel.pid_max", "value": "1"}]), "is not set by the file"),
    ("number not quoted", lambda m: m["files"]["threads"].update(expect=[{"sysctl": "kernel.threads-max", "value": 131072}]), "non-empty string"),
    ("both value and contains", lambda m: m["files"]["nginx-restart"].update(expect=[{"systemd": "nginx.service", "property": "After", "value": "a", "contains": "b"}]), "exactly one of value, contains"),
    ("unit of another drop-in", lambda m: m["files"]["nginx-restart"].update(expect=[{"systemd": "sshd.service", "property": "Restart", "value": "no"}]), "is not the unit of"),
    ("pg cluster mismatch", lambda m: m["files"]["pg-log"].update(expect=[{"pg_setting": "log_connections", "cluster": "17/main", "value": "receipt,authorization"}]), "is not the cluster of"),
    ("pg value differs", lambda m: m["files"]["pg-log"].update(expect=[{"pg_setting": "log_connections", "cluster": "18/main", "value": "on"}]), "but the expectation is on"),
    ("duplicate ssh alias", lambda m: m["hosts"]["h2"].update(ssh="h1"), "already used"),
    ("bad hostname", lambda m: m["hosts"]["h1"].update(hostname="bad host!"), "hostname"),
    ("option-looking ssh alias", lambda m: m["hosts"]["h1"].update(ssh="-oProxyCommand=x"), "ssh must be"),
    ("same dest twice on a host", lambda m: (m["files"].update({"nginx2": dict(m["files"]["nginx-restart"])}), m["hosts"]["h1"]["files"].append("nginx2")), "both write"),
    ("file listed twice", lambda m: m["hosts"]["h1"]["files"].append("threads"), "twice"),
    ("catalog entry nobody uses", lambda m: m["hosts"]["h1"]["files"].remove("threads"), "no host uses it"),
    ("host without files", lambda m: m["hosts"]["h2"].update(files=[]), "no files and the manifest has no baseline"),
    ("unknown key", lambda m: m["files"]["threads"].update(colour="red"), "unknown keys"),
    ("wrong version", lambda m: m.update(version=2), "version must be 1"),
])
def test_manifest_problems(world, label, mutate, needle):
    found = problems(world, mutate)
    assert any(needle in p for p in found), (label, found)


def test_a_file_in_files_that_no_entry_uses_is_a_problem(world):
    (world.files / "orphan.conf").write_text(THREADS)
    assert any("orphan.conf: a file that no catalog entry uses" in p for p in problems(world, lambda m: None))


def test_a_credential_in_a_shipped_file_fails_the_check(world):
    (world.files / "nginx.conf").write_text("[Service]\nEnvironment=API_TOKEN=abc\n")
    assert any("credential" in p for p in problems(world, lambda m: None))


def test_the_manifest_shipped_in_the_repo_is_valid():
    manifest = hostconf.load_manifest()
    assert hostconf.manifest_problems(manifest) == []
    assert hostconf.main(["check"]) == 0


def test_the_thread_limit_file_pins_the_value_that_covers_a_container_start_storm():
    manifest = hostconf.load_manifest()
    f = manifest["files"]["sysctl-hotplug-threads-max"]
    assert hostconf.parse_settings("sysctl", (hostconf.FILES_DIR / f["src"]).read_text()) == {"kernel.threads-max": "131072"}
    assert f["expect"] == [{"sysctl": "kernel.threads-max", "value": "131072"}]
    carrying = [h for h, v in manifest["hosts"].items() if "sysctl-hotplug-threads-max" in v.get("files", [])]
    assert len(carrying) >= 30 and {"infer-runtime", "docker-runtime", "docker-build", "own-pbs", "pdm"} <= set(carrying)  # the floor was 31 before the last of the four 0database guests (VM 102) was retired on 2026-10-21


def test_the_shipped_manifest_pins_the_boot_ordering_around_tailscale():
    """2026-10-13: a tailnet proxy socket that is After=tailscaled.service and Before=sockets.target is an ordering cycle; systemd broke it by deleting start jobs, tailscaled included."""
    manifest = hostconf.load_manifest()
    sockets = {fid: f for fid, f in manifest["files"].items() if fid.startswith("socket-no-default-deps.")}
    assert len(sockets) >= 23
    for fid, f in sockets.items():
        assert f["expect"] == [{"systemd": f["expect"][0]["systemd"], "property": "DefaultDependencies", "value": "no"}], fid
        assert (hostconf.FILES_DIR / f["src"]).read_text().count("DefaultDependencies=no") == 1
    assert {"pve-0mcp", "bastion"} <= {h for h, v in manifest["hosts"].items() if any(i in sockets for i in v.get("files", []))}
    for fid in ("node-exporter-after-tailscale", "node-exporter-wait-for-tailscale", "node-exporter-retry-until-tailnet"):
        assert manifest["files"][fid]["dest"].startswith("/etc/systemd/system/prometheus-node-exporter.service.d/")


def test_a_host_that_binds_the_tailnet_address_waits_for_tailscaled():
    manifest = hostconf.load_manifest()
    after = manifest["files"]["node-exporter-after-tailscale"]
    assert after["expect"] == [{"systemd": "prometheus-node-exporter.service", "property": "After", "contains": "tailscaled.service"}]
    text = (hostconf.FILES_DIR / after["src"]).read_text()
    assert "After=tailscaled.service" in text and "StartLimitIntervalSec=0" in text


def test_the_shipped_manifest_pins_the_gateway_restart_policy_and_the_database_oom_policy():
    manifest = hostconf.load_manifest()
    hosts = manifest["hosts"]
    for host, fid in (("webgateway", "nginx-restart-policy.webgateway"), ("nginx-lv3", "nginx-restart-policy.nginx-lv3"), ("bastion", "nginx-restart-policy.bastion")):
        assert fid in hosts[host]["files"]
        assert {"systemd": "nginx.service", "property": "OOMPolicy", "value": "continue"} in manifest["files"][fid]["expect"]
    for host in ("infer-pg-primary", "postgres-lv3"):
        assert any(f.startswith("postgresql-oom-policy.") for f in hosts[host]["files"])
    # pg-primary (VM 100 on the 0database hypervisor, the DomainScope hot standby) was shut down on 2026-10-21 for the pve01 retirement and left the hosts
    assert "pg-primary" not in hosts and not [f for f in manifest["files"] if f.endswith(".pg-primary")]


def test_the_builder_caps_what_ssh_sessions_can_use_and_never_swaps():
    """2026-10-21: a mutation run started over ssh grew one `go test` to 9.6 GB and put the 0docker hypervisor into swap. The builder's ssh work
    (user-0.slice) is capped; MemoryHigh < MemoryMax so a runaway is throttled before it is killed, and the swap limit is zero."""
    manifest = hostconf.load_manifest()
    assert "user-0-slice-memory.0docker-builder" in manifest["hosts"]["0docker-builder"]["files"]
    f = manifest["files"]["user-0-slice-memory.0docker-builder"]
    assert f["dest"] == "/etc/systemd/system/user-0.slice.d/50-memory.conf"
    lines = [l.strip() for l in (hostconf.FILES_DIR / f["src"]).read_text().splitlines() if l.strip() and not l.lstrip().startswith("#")]
    assert lines[0] == "[Slice]"
    in_file = dict(l.split("=", 1) for l in lines[1:])
    to_bytes = lambda v: int(v[:-1]) * 2**30 if v.endswith("G") else int(v)  # the file says 5G, systemd reports bytes
    want = {"MemoryHigh": 5 * 2**30, "MemoryMax": 6 * 2**30, "MemorySwapMax": 0}
    assert {k: to_bytes(v) for k, v in in_file.items()} == want
    assert {e["property"]: int(e["value"]) for e in f["expect"]} == want
    assert want["MemoryHigh"] < want["MemoryMax"] and want["MemorySwapMax"] == 0


# ───────────────────────────── drift: read only ─────────────────────────────


def tree_state(root: Path):
    return sorted((str(p.relative_to(root)), p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else b"") for p in root.rglob("*") if p.name != "calls.log")


def test_drift_reports_a_missing_file_and_the_setting_that_is_not_in_effect_and_changes_nothing(world, capsys):
    before = tree_state(world.roots["h1"])
    assert world.main("drift", "--host", "h1") == 2
    out = capsys.readouterr().out
    assert "MISSING  /etc/systemd/system/nginx.service.d/override.conf" in out
    assert "NOT IN EFFECT  systemd nginx.service.Restart: live 'no', wanted 'on-failure'" in out
    assert "NOT IN EFFECT  sysctl kernel.threads-max: live '7016', wanted '131072'" in out
    assert tree_state(world.roots["h1"]) == before
    assert not [c for c in world.calls("h1") if c.startswith(("systemctl daemon-reload", "sysctl -p", "sysctl -w"))]


def test_drift_is_clean_after_an_apply_and_names_each_kind_of_difference(world, capsys):
    assert world.main("apply", "--host", "h1", "--yes") == 0
    capsys.readouterr()
    assert world.main("drift", "--host", "h1") == 0
    d = world.dest("h1", "/etc/systemd/system/nginx.service.d/override.conf")
    d.write_text(NGINX + "# edited by hand\n")
    assert world.main("drift", "--host", "h1") == 2
    assert "DIFFERS  /etc/systemd/system/nginx.service.d/override.conf" in capsys.readouterr().out
    d.write_text(NGINX)
    d.chmod(0o600)
    assert world.main("drift", "--host", "h1") == 2
    out = capsys.readouterr().out
    assert "MODE" in out and "live 0600 root:root, wanted 0644 root:root" in out
    d.unlink()
    d.symlink_to("/etc/passwd")
    assert world.main("drift", "--host", "h1") == 2
    assert "SYMLINK" in capsys.readouterr().out


def test_drift_diff_shows_what_differs_and_never_a_credential_found_on_the_host(world, capsys):
    assert world.main("apply", "--host", "h1", "--yes") == 0
    capsys.readouterr()
    d = world.dest("h1", "/etc/systemd/system/nginx.service.d/override.conf")
    d.write_text("[Service]\nRestart=always\n")
    assert world.main("drift", "--host", "h1", "--diff") == 2
    out = capsys.readouterr().out
    assert "-Restart=always" in out and "+Restart=on-failure" in out
    d.write_text("[Service]\nEnvironment=API_TOKEN=hunter2hunter2\n")
    assert world.main("drift", "--host", "h1", "--diff") == 2
    out = capsys.readouterr().out
    assert "SECRETISH" in out and "hunter2" not in out


def test_drift_refuses_the_wrong_machine_and_reports_it_as_not_reachable(world, capsys):
    m = load(world)
    m["hosts"]["h1"]["hostname"] = "some-other-machine"
    world.manifest_path.write_text(yaml.safe_dump(m))
    assert world.main("drift", "--host", "h1") == 3
    assert "wrong host" in capsys.readouterr().out


def test_drift_reports_a_host_that_does_not_answer_and_keeps_going(world, capsys):
    def dead(alias, script, timeout, sudo=True):
        if alias == "h1":
            return 255, "", "ssh: connect to host h1 port 22: Operation timed out"
        return world.runner(alias, script, timeout)

    assert hostconf.main(["--manifest", str(world.manifest_path), "drift", "--all"], runner=dead) == 3
    out = capsys.readouterr().out
    assert "h1 (" in out and "COULD NOT LOOK: ssh: connect to host h1" in out
    assert "h2 (" in out and "MISSING" in out
    assert "1 not reachable" in out


def test_drift_file_narrows_the_check_and_skips_hosts_without_it(world, capsys):
    assert world.main("drift", "--all", "--file", "pg-log") == 2
    out = capsys.readouterr().out
    assert "h2 (" in out and "h1 (" not in out
    assert world.main("drift", "--all", "--file", "nope") == 1


def test_the_drift_metrics_file(world, tmp_path):
    out_dir = tmp_path / "textfile"
    world.main("apply", "--host", "h1", "--yes")
    world.main("drift", "--all", "--textfile-dir", str(out_dir))
    text = (out_dir / "fleet_hostconf.prom").read_text()
    assert 'fleet_hostconf_files_total{machine="h1"} 2' in text
    assert 'fleet_hostconf_drift_files{machine="h1"} 0' in text
    assert 'fleet_hostconf_drift_files{machine="h2"} 2' in text  # the file is missing and the setting is not in effect
    assert 'fleet_hostconf_unreachable{machine="h1"} 0' in text
    assert "fleet_hostconf_last_run_timestamp_seconds " in text
    assert not list(out_dir.glob(".*tmp"))
    assert 'host="' not in text.replace('machine="', "").replace('hypervisor="', "")  # Prometheus would rename a scraped `host` label to `exported_host`


def test_a_host_that_could_not_be_looked_at_has_no_drift_metric_only_the_unreachable_one():
    manifest = {"hosts": {"a": {"files": ["x"]}}}
    text = hostconf.metrics_text(manifest, [{"host": "a", "unreachable": "timeout", "files": [], "expects": []}], now=1)
    assert 'fleet_hostconf_unreachable{machine="a"} 1' in text
    assert "fleet_hostconf_drift_files{" not in text and "fleet_hostconf_below_baseline{" not in text


def test_label_values_are_escaped_the_way_the_text_format_wants():
    assert hostconf._label('a"b\\c\nd') == 'a\\"b\\\\c\\nd'
    manifest = {"hosts": {'we"ird': {"files": []}}}
    text = hostconf.metrics_text(manifest, [{"host": 'we"ird', "files": [], "expects": []}], now=1)
    assert 'fleet_hostconf_drift_files{machine="we\\"ird"} 0' in text


# ───────────────────────────── apply ─────────────────────────────


def test_apply_without_yes_prints_the_plan_and_changes_nothing(world, capsys):
    before = tree_state(world.roots["h1"])
    assert world.main("apply", "--host", "h1") == 0
    out = capsys.readouterr().out
    assert "plan: 1 file(s) would be written" not in out and "plan: 2 file(s) would be written on h1; nothing changed (add --yes)" in out
    assert tree_state(world.roots["h1"]) == before


def test_apply_writes_the_files_reloads_and_verifies_the_settings_are_in_effect(world, capsys):
    assert world.main("apply", "--host", "h1", "--yes") == 0
    out = capsys.readouterr().out
    dropin = world.dest("h1", "/etc/systemd/system/nginx.service.d/override.conf")
    sysctl = world.dest("h1", "/etc/sysctl.d/90-threads.conf")
    assert dropin.read_text() == NGINX and sysctl.read_text() == THREADS
    assert stat.S_IMODE(dropin.stat().st_mode) == 0o644
    assert "apply on h1: applied" in out and "ok: systemd nginx.service.Restart = 'on-failure'" in out and "ok: sysctl kernel.threads-max = '131072'" in out
    calls = world.calls("h1")
    assert [c for c in calls if c == "systemctl daemon-reload"] == ["systemctl daemon-reload"]  # once, however many drop-ins
    assert any(c.startswith("sysctl -p ") and c.endswith("90-threads.conf") for c in calls)
    assert not [c for c in calls if re.search(r"\b(restart|stop|start|kill|reboot)\b", c)]
    assert not list(world.roots["h1"].rglob("*.hostconf-new"))  # the temporary files are gone


def test_apply_keeps_the_previous_file_next_to_the_new_one(world, capsys):
    d = world.dest("h1", "/etc/systemd/system/nginx.service.d/override.conf")
    d.parent.mkdir(parents=True)
    d.write_text("[Service]\nRestart=no\n")
    assert world.main("apply", "--host", "h1", "--yes") == 0
    backups = list(d.parent.glob("override.conf.bak-hostconf-*"))
    assert len(backups) == 1 and backups[0].read_text() == "[Service]\nRestart=no\n"
    assert d.read_text() == NGINX
    assert "previous /etc/systemd/system/nginx.service.d/override.conf kept as /etc/systemd/system/nginx.service.d/override.conf.bak-hostconf-" in capsys.readouterr().out


def test_a_backup_file_is_never_read_as_a_drop_in(world):
    d = world.dest("h1", "/etc/systemd/system/nginx.service.d/override.conf")
    d.parent.mkdir(parents=True)
    d.write_text("[Service]\nRestart=no\n")
    world.main("apply", "--host", "h1", "--yes")
    assert all(p.suffix != ".conf" for p in d.parent.glob("*.bak-hostconf-*"))
    assert hostconf.kind_of("/etc/systemd/system/nginx.service.d/" + next(d.parent.glob("*.bak-hostconf-*")).name) is None


def test_apply_of_something_already_in_place_and_in_effect_does_nothing(world, capsys):
    assert world.main("apply", "--host", "h1", "--yes") == 0
    capsys.readouterr()
    before = tree_state(world.roots["h1"])
    n = len(world.calls("h1"))
    assert world.main("apply", "--host", "h1", "--yes") == 0
    assert tree_state(world.roots["h1"]) == before
    assert not [c for c in world.calls("h1")[n:] if c.startswith(("systemctl daemon-reload", "sysctl -p", "sysctl -w"))]


def test_a_file_written_by_hand_but_never_reloaded_is_reloaded_not_rewritten(world, capsys):
    """The drop-in is already right on disk, systemd has not read it: apply reloads (nothing is written) and the setting comes into effect."""
    d = world.dest("h1", "/etc/systemd/system/nginx.service.d/override.conf")
    d.parent.mkdir(parents=True)
    d.write_text(NGINX)
    world.dest("h1", "/etc/sysctl.d/90-threads.conf").parent.mkdir(parents=True)
    world.dest("h1", "/etc/sysctl.d/90-threads.conf").write_text(THREADS)
    world.dest("h1", "/etc/sysctl.d/90-threads.conf").chmod(0o644)
    d.chmod(0o644)
    mtime = d.stat().st_mtime_ns
    assert world.main("drift", "--host", "h1") == 2  # not in effect
    assert world.main("apply", "--host", "h1", "--yes") == 0
    assert d.stat().st_mtime_ns == mtime and not list(d.parent.glob("*.bak-hostconf-*"))
    assert world.main("drift", "--host", "h1") == 0


def test_apply_rolls_back_when_the_setting_does_not_come_into_effect(world, capsys):
    """systemd does not pick the drop-in up: the old file comes back, the unit state is reloaded again, the exit code says rolled back."""
    d = world.dest("h1", "/etc/systemd/system/nginx.service.d/override.conf")
    d.parent.mkdir(parents=True)
    d.write_text("[Service]\nRestart=no\n")
    world.env["FAKE_NOEFFECT"] = "1"
    assert world.main("apply", "--host", "h1", "--file", "nginx-restart", "--yes") == 5
    out = capsys.readouterr().out
    assert "rolled_back" in out and "a setting is not in effect after the change" in out
    assert d.read_text() == "[Service]\nRestart=no\n"
    assert len([c for c in world.calls("h1") if c == "systemctl daemon-reload"]) == 2  # after the change and after the rollback


def test_a_changed_file_stays_when_another_file_of_the_host_is_not_in_effect_for_a_reason_of_its_own(world, capsys):
    """The thread-limit file is already right on disk but sysctl will not take it; the new nginx drop-in is fine and must not be rolled back for that."""
    t = world.dest("h1", "/etc/sysctl.d/90-threads.conf")
    t.parent.mkdir(parents=True)
    t.write_text(THREADS)
    t.chmod(0o644)
    world.env["FAKE_SYSCTL_IGNORE"] = "1"
    assert world.main("apply", "--host", "h1", "--yes") == 2
    out = capsys.readouterr().out
    assert "not_in_effect" in out and "NOT IN EFFECT: sysctl kernel.threads-max = '7016'" in out and "ok: systemd nginx.service.Restart = 'on-failure'" in out
    assert world.dest("h1", "/etc/systemd/system/nginx.service.d/override.conf").read_text() == NGINX


def test_an_unchanged_file_that_was_never_loaded_is_loaded_in_the_same_run_as_a_changed_one(world, capsys):
    t = world.dest("h1", "/etc/sysctl.d/90-threads.conf")
    t.parent.mkdir(parents=True)
    t.write_text(THREADS)
    t.chmod(0o644)
    assert world.main("apply", "--host", "h1", "--yes") == 0
    assert (world.roots["h1"] / "state/sysctl/kernel.threads-max").read_text().strip() == "131072"
    assert world.dest("h1", "/etc/systemd/system/nginx.service.d/override.conf").read_text() == NGINX
    assert not list(t.parent.glob("*.bak-hostconf-*"))  # it was right: not rewritten


def test_a_rollback_that_cannot_be_verified_says_so_with_its_own_exit_code(world, capsys):
    """Exit 4 is the one that needs a human: the setting is not in effect AND the old file is not what it was."""
    d = world.dest("h1", "/etc/systemd/system/nginx.service.d/override.conf")
    d.parent.mkdir(parents=True)
    d.write_text("[Service]\nRestart=no\n")
    world.env["FAKE_NOEFFECT"] = "1"
    world.env["FAKE_CORRUPT_ON_SECOND_RELOAD"] = "/etc/systemd/system/nginx.service.d/override.conf"
    assert world.main("apply", "--host", "h1", "--file", "nginx-restart", "--yes") == 4
    assert "rollback_unverified" in capsys.readouterr().out


def test_a_rollback_of_a_new_file_removes_it(world, capsys):
    world.env["FAKE_NOEFFECT"] = "1"
    assert world.main("apply", "--host", "h1", "--file", "nginx-restart", "--yes") == 5
    assert not world.dest("h1", "/etc/systemd/system/nginx.service.d/override.conf").exists()


def test_apply_rolls_back_when_the_reload_fails(world, capsys):
    world.env["FAKE_FAIL_RELOAD"] = "1"
    assert world.main("apply", "--host", "h1", "--file", "nginx-restart", "--yes") == 5
    assert "reload failed" in capsys.readouterr().out
    assert not world.dest("h1", "/etc/systemd/system/nginx.service.d/override.conf").exists()


def test_a_sysctl_rollback_puts_the_old_runtime_value_back(world, capsys):
    """sysctl -p is ignored, the setting is not in effect: the file is removed and the runtime limit is the old one again."""
    world.env["FAKE_SYSCTL_IGNORE"] = "1"
    assert world.main("apply", "--host", "h1", "--file", "threads", "--yes") == 5
    assert not world.dest("h1", "/etc/sysctl.d/90-threads.conf").exists()
    assert any(c == "sysctl -w kernel.threads-max=7016" for c in world.calls("h1"))
    assert (world.roots["h1"] / "state/sysctl/kernel.threads-max").read_text().strip() == "7016"


def test_a_sysctl_apply_raises_the_runtime_limit_and_persists_the_file(world, capsys):
    assert world.main("apply", "--host", "h1", "--file", "threads", "--yes") == 0
    assert (world.roots["h1"] / "state/sysctl/kernel.threads-max").read_text().strip() == "131072"
    assert world.dest("h1", "/etc/sysctl.d/90-threads.conf").read_text() == THREADS


def test_a_postgres_file_gets_its_group_mode_and_a_reload_of_its_own_cluster(world, capsys):
    assert world.main("apply", "--host", "h2", "--yes") == 0
    f = world.dest("h2", "/etc/postgresql/18/main/conf.d/97-log-connections.conf")
    assert f.read_text() == PGLOG and stat.S_IMODE(f.stat().st_mode) == 0o640
    assert "pg_ctlcluster 18 main reload" in world.calls("h2")
    assert (world.roots["h2"] / "state/pg/log_connections").read_text() == "receipt,authorization"


def test_a_postgres_setting_that_needs_a_restart_is_reported_and_never_restarted(world, capsys):
    (world.roots["h2"] / "state").mkdir(exist_ok=True)
    (world.roots["h2"] / "state" / "pg-pending").write_text("shared_buffers\nlisten_addresses\n")
    assert world.main("apply", "--host", "h2", "--yes") == 0
    assert "needs a restart to take effect (not done here): shared_buffers, listen_addresses" in capsys.readouterr().out
    assert not [c for c in world.calls("h2") if re.search(r"\b(restart|stop|start|kill|reboot)\b", c)]


def test_a_postgres_reload_that_fails_rolls_back(world, capsys):
    world.env["FAKE_FAIL_PG"] = "1"
    assert world.main("apply", "--host", "h2", "--yes") == 5
    assert not world.dest("h2", "/etc/postgresql/18/main/conf.d/97-log-connections.conf").exists()


def test_a_wrong_mode_or_owner_alone_is_fixed_by_a_rewrite(world, capsys):
    world.main("apply", "--host", "h1", "--yes")
    d = world.dest("h1", "/etc/systemd/system/nginx.service.d/override.conf")
    d.chmod(0o666)
    assert world.main("apply", "--host", "h1", "--yes") == 0
    assert stat.S_IMODE(d.stat().st_mode) == 0o644


def test_apply_refuses_a_symlink_and_a_credential_found_on_the_host(world, capsys):
    d = world.dest("h1", "/etc/systemd/system/nginx.service.d/override.conf")
    d.parent.mkdir(parents=True)
    d.symlink_to("/etc/passwd")
    assert world.main("apply", "--host", "h1", "--file", "nginx-restart", "--yes") == 1
    assert "cannot be replaced safely" in capsys.readouterr().out and d.is_symlink()
    d.unlink()
    d.write_text("[Service]\nEnvironment=API_TOKEN=hunter2hunter2\n")
    assert world.main("apply", "--host", "h1", "--file", "nginx-restart", "--yes") == 1
    assert d.read_text() == "[Service]\nEnvironment=API_TOKEN=hunter2hunter2\n"  # looked at by hand, not overwritten


def test_apply_refuses_the_wrong_machine_before_any_write(world, capsys):
    m = load(world)
    m["hosts"]["h1"]["hostname"] = "some-other-machine"
    world.manifest_path.write_text(yaml.safe_dump(m))
    assert world.main("apply", "--host", "h1", "--yes") == 3
    assert not world.dest("h1", "/etc/sysctl.d/90-threads.conf").exists()


def test_two_applies_at_once_are_refused(world, capsys):
    host = load(world)["hosts"]["h1"]
    lock = world.roots["h1"] / "run" / "lock" / "hostconf.lock"
    lock.parent.mkdir(parents=True)
    with open(lock, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        code, out, _ = world.runner("h1", hostconf.build_script("apply", host, hostconf.host_files(load(world), "h1")), 60)
    assert code == 1 and "another hostconf apply is running" in json.loads(out.split("HOSTCONF_RESULT ")[1])["refused"]
    assert not world.dest("h1", "/etc/sysctl.d/90-threads.conf").exists()


def test_the_host_checks_the_content_it_was_sent(world):
    host = load(world)["hosts"]["h1"]
    f = hostconf.host_files(load(world), "h1")[1]
    tampered = dict(f, b64=base64.b64encode(b"kernel.threads-max = 1\n").decode())
    code, out, _ = world.runner("h1", hostconf.build_script("apply", host, [tampered]), 60)
    assert code == 1 and "integrity" in json.loads(out.split("HOSTCONF_RESULT ")[1])["refused"]
    secret = b"kernel.threads-max = 1\n# password: x\n"
    leaked = dict(f, b64=base64.b64encode(secret).decode(), sha256=hashlib.sha256(secret).hexdigest())
    code, out, _ = world.runner("h1", hostconf.build_script("apply", host, [leaked]), 60)
    assert code == 1 and "credential" in json.loads(out.split("HOSTCONF_RESULT ")[1])["refused"]
    assert not world.dest("h1", "/etc/sysctl.d/90-threads.conf").exists()


def test_an_unknown_owner_or_group_is_refused_before_any_write(world, monkeypatch):
    """Outside the test mode (no HOSTCONF_ROOT) the owner and group must exist on the machine: here they cannot, so nothing may be written."""
    host = load(world)["hosts"]["h1"]
    f = dict(hostconf.host_files(load(world), "h1")[0], group="no-such-group-xyz")
    script = hostconf.build_script("apply", host, [f]).replace('ROOT = os.environ.get("HOSTCONF_ROOT", "")', 'ROOT = ""').replace('real(path):\n    return ROOT + path', 'real(path):\n    return "' + str(world.roots["h1"]) + '" + path')
    p = subprocess.run([sys.executable, "-"], input=script, capture_output=True, text=True, env=dict(os.environ))
    assert p.returncode == 1 and "does not exist here" in json.loads(p.stdout.split("HOSTCONF_RESULT ")[1])["refused"]
    assert not world.dest("h1", "/etc/systemd/system/nginx.service.d/override.conf").exists()


# ───────────────────────────── the fleet-wide baseline ─────────────────────────────


def with_baseline(world, floor="100000", extra_hosts=None):
    """The test world plus a baseline (threads-max >= floor, fixed by the `threads` file) and optionally hosts that carry no file."""
    m = load(world)
    m["baseline"] = [{"sysctl_min": "kernel.threads-max", "value": floor, "fix": "threads"}]
    for name, current in (extra_hosts or {}).items():
        root = world.tmp / f"root-{name}"
        (root / "state" / "sysctl").mkdir(parents=True)
        (root / "state" / "sysctl" / "kernel.threads-max").write_text(f"{current}\n")
        world.roots[name] = root
        m["hosts"][name] = {"ssh": name, "hostname": HERE}
    world.manifest_path.write_text(yaml.safe_dump(m))
    return m


def test_a_host_below_the_baseline_is_reported_with_the_file_that_fixes_it_and_nothing_is_written(world, capsys):
    with_baseline(world, extra_hosts={"h3": 7016})
    before = tree_state(world.roots["h3"])
    assert world.main("drift", "--host", "h3") == 2
    out = capsys.readouterr().out
    assert "BELOW BASELINE  sysctl kernel.threads-max: live '7016', wanted >= 100000; add threads to this host's files in config/hostconf/hostconf.yaml" in out
    assert tree_state(world.roots["h3"]) == before


def test_a_host_exactly_at_the_floor_passes(world, capsys):
    with_baseline(world, floor="131072", extra_hosts={"h3": 131072, "h4": 131071})
    assert world.main("drift", "--host", "h3") == 0
    assert world.main("drift", "--host", "h4") == 2


def test_the_metrics_say_which_machines_are_below_the_floor(world, tmp_path):
    """The scheduled check alerts on this gauge: a VM whose thread limit sits under the floor is one container start storm away from the 2026-10-19 failure."""
    with_baseline(world, floor="131072", extra_hosts={"h3": 7016, "h4": 131072})
    out_dir = tmp_path / "textfile"
    world.main("drift", "--all", "--textfile-dir", str(out_dir))
    text = (out_dir / "fleet_hostconf.prom").read_text()
    assert 'fleet_hostconf_below_baseline{machine="h3"} 1' in text   # no file, under the floor
    assert 'fleet_hostconf_below_baseline{machine="h4"} 0' in text   # exactly at the floor
    assert 'fleet_hostconf_below_baseline{machine="h1"} 1' in text   # the file is listed but not applied yet
    world.main("apply", "--host", "h1", "--yes")
    world.main("drift", "--all", "--textfile-dir", str(out_dir))
    text = (out_dir / "fleet_hostconf.prom").read_text()
    assert 'fleet_hostconf_below_baseline{machine="h1"} 0' in text and 'fleet_hostconf_below_baseline{machine="h3"} 1' in text


def test_a_host_above_the_floor_needs_no_file_and_is_never_lowered(world, capsys):
    """A hypervisor or a big VM with a boot default of 900000 passes: a fixed file of 131072 would lower it, so the floor is checked, not written."""
    with_baseline(world, extra_hosts={"h3": 900000})
    assert world.main("drift", "--host", "h3") == 0
    assert world.main("apply", "--host", "h3", "--yes") == 0
    assert (world.roots["h3"] / "state/sysctl/kernel.threads-max").read_text().strip() == "900000"
    assert not (world.roots["h3"] / "etc").exists()


def test_a_listed_floor_file_that_is_not_yet_applied_says_so_and_apply_fixes_it(world, capsys):
    with_baseline(world)
    assert world.main("drift", "--host", "h1") == 2
    assert "threads is listed for this host but the setting is not in effect" in capsys.readouterr().out
    assert world.main("apply", "--host", "h1", "--yes") == 0
    assert world.main("drift", "--host", "h1") == 0


def test_apply_on_a_host_without_the_fix_changes_nothing_and_exits_with_the_hint(world, capsys):
    with_baseline(world, extra_hosts={"h3": 7016})
    assert world.main("apply", "--host", "h3", "--yes") == 2
    out = capsys.readouterr().out
    assert "BELOW BASELINE" in out and "apply on h3: not_in_effect" in out
    assert (world.roots["h3"] / "state/sysctl/kernel.threads-max").read_text().strip() == "7016"


def test_the_baseline_is_checked_whatever_file_is_asked_for_but_a_file_filter_still_skips_hosts_without_it(world, capsys):
    with_baseline(world, extra_hosts={"h3": 900000})
    assert world.main("drift", "--all", "--file", "pg-log") == 2  # h2 lacks its file; h3 (no files) is not selected
    out = capsys.readouterr().out
    assert "h2 (" in out and "h3 (" not in out
    assert world.main("drift", "--all") == 2
    assert "h3 (" in capsys.readouterr().out


@pytest.mark.parametrize("label,mutate,needle", [
    ("extra keys", lambda m: m["baseline"][0].update(note="x"), "needs exactly sysctl_min, value and fix"),
    ("bad key", lambda m: m["baseline"][0].update(sysctl_min="threads"), "must be a sysctl key"),
    ("number not quoted", lambda m: m["baseline"][0].update(value=131072), "quoted whole number"),
    ("fix unknown", lambda m: m["baseline"][0].update(fix="nope"), "must be the id of a sysctl catalog file"),
    ("fix is not a sysctl file", lambda m: m["baseline"][0].update(fix="nginx-restart"), "must be the id of a sysctl catalog file"),
    ("fix sets a lower value", lambda m: m["baseline"][0].update(value="200000"), "does not meet the floor 200000"),
    ("fix does not set the key", lambda m: m["baseline"][0].update(sysctl_min="vm.swappiness"), "sets vm.swappiness to nothing"),
    ("not a list", lambda m: m.update(baseline={"a": 1}), "baseline must be a list"),
    ("misspelt top-level key", lambda m: m.update(basline=[]), "unknown top-level keys"),
    ("sudo must be a boolean", lambda m: m["hosts"]["h1"].update(sudo="no"), "sudo must be true or false"),
])
def test_baseline_manifest_problems(world, label, mutate, needle):
    def both(m):
        m["baseline"] = [{"sysctl_min": "kernel.threads-max", "value": "100000", "fix": "threads"}]
        mutate(m)

    assert any(needle in p for p in problems(world, both)), label


def test_a_host_with_no_file_is_only_valid_when_there_is_a_baseline(world):
    def no_files(m):
        m["hosts"]["h3"] = {"ssh": "h3", "hostname": "h3"}

    assert any("no files and the manifest has no baseline" in p for p in problems(world, no_files))

    def with_floor(m):
        no_files(m)
        m["baseline"] = [{"sysctl_min": "kernel.threads-max", "value": "100000", "fix": "threads"}]

    assert problems(world, with_floor) == []


def test_the_ssh_runner_logs_in_as_root_without_sudo_when_the_host_says_so(monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, "HOSTCONF_RESULT {}", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    hostconf.ssh_run("pve-0own", "print(1)", 30, False)
    assert seen["argv"][-3:] == ["pve-0own", "python3", "-"] and "sudo" not in seen["argv"]
    hostconf.ssh_run("webgateway", "print(1)", 30, True)
    assert seen["argv"][-5:] == ["webgateway", "sudo", "-n", "python3", "-"]


def test_run_on_host_passes_the_hosts_sudo_setting_to_the_runner(world):
    m = load(world)
    m["hosts"]["h1"]["sudo"] = False
    seen = []

    def runner(alias, script, timeout, sudo=True):
        seen.append((alias, sudo))
        return 0, "HOSTCONF_RESULT " + json.dumps({"files": [], "expects": []}) + "\n", ""

    hostconf.run_on_host(m, "h1", "observe", None, runner)
    hostconf.run_on_host(m, "h2", "observe", None, runner)
    assert seen == [("h1", False), ("h2", True)]


def test_the_shipped_baseline_covers_every_machine_and_never_lowers_one():
    manifest = hostconf.load_manifest()
    assert manifest["baseline"] == [{"sysctl_min": "kernel.threads-max", "value": "131072", "fix": "sysctl-hotplug-threads-max"}]
    hosts = manifest["hosts"]
    assert len(hosts) >= 40  # was 41, 43 and 45 before: the four 0database guests (100 to 103) left on 2026-10-21 and the 0database hypervisor itself (pve01, cancelled) on 2026-10-22
    for hv in ("bastion", "pve-0mcp", "pve-0infer", "pve-0own"):
        assert hv in hosts, f"the hypervisor {hv} must be in the manifest: its VMs are only as safe as the checks that reach them"
        assert "sysctl-hotplug-threads-max" not in hosts[hv].get("files", []), f"{hv} already boots with a limit far above the floor: a fixed file would lower it"
    assert hosts["pve-0own"].get("sudo") is False  # root login, no sudo on that hypervisor


def test_the_guest_cloud_init_template_gives_every_new_guest_the_floor():
    """Guests rendered from the Ansible role's user-data get the thread floor at first boot, like they keep their SSH host keys."""
    template = (Path(__file__).resolve().parents[1] / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "proxmox_guests" / "templates" / "user-data.yml.j2").read_text()
    manifest = hostconf.load_manifest()
    floor = manifest["baseline"][0]["value"]
    assert "\nwrite_files:\n" in template
    assert "  - path: /etc/sysctl.d/90-memory-hotplug-threads.conf\n" in template
    assert f"      kernel.threads-max = {floor}\n" in template
    assert "  - sysctl -p /etc/sysctl.d/90-memory-hotplug-threads.conf\n" in template
    assert hostconf.parse_settings("sysctl", (hostconf.FILES_DIR / manifest["files"]["sysctl-hotplug-threads-max"]["src"]).read_text()) == {"kernel.threads-max": floor}


# ───────────────────────────── the inventory of the hypervisors ─────────────────────────────


def with_inventory(world, qm=("101 h1 running", "102 h2 running"), pct=(), exempt=(), configs=None, extra_hosts=None, pvesh=None):
    """A hypervisor `hv` (a machine to list, checked by a trivial baseline) running the given guests; h1 and h2 are its VMs 101 and 102."""
    m = load(world)
    m["baseline"] = [{"sysctl_min": "kernel.threads-max", "value": "1", "fix": "threads"}]
    m["hosts"]["hv"] = {"ssh": "hv", "hostname": HERE}
    m["hosts"]["h1"]["vm"] = {"hypervisor": "hv", "id": 101}
    m["hosts"]["h2"]["vm"] = {"hypervisor": "hv", "id": 102}
    for name, h in (extra_hosts or {}).items():
        m["hosts"][name] = h
        if "ssh" in h:
            world.roots[name] = world.tmp / f"root-{name}"
            (world.roots[name] / "state" / "sysctl").mkdir(parents=True)
            (world.roots[name] / "state" / "sysctl" / "kernel.threads-max").write_text("7016\n")
        else:
            key = f"{m['hosts'][h['vm']['hypervisor']]['ssh']}#{h['vm']['id']}"
            world.roots[key] = world.tmp / f"root-{key.replace('#', '-')}"
            (world.roots[key] / "state" / "sysctl").mkdir(parents=True)
            (world.roots[key] / "state" / "sysctl" / "kernel.threads-max").write_text("7016\n")
    m["inventory"] = {"hypervisors": ["hv"], "exempt": [{"hypervisor": "hv", "id": i, "why": why} for i, why in exempt]}
    world.manifest_path.write_text(yaml.safe_dump(m))
    root = world.tmp / "root-hv"
    (root / "state" / "sysctl").mkdir(parents=True)
    (root / "state" / "sysctl" / "kernel.threads-max").write_text("7016\n")
    (root / "state" / "qm-list.txt").write_text("\n".join(qm) + "\n")
    (root / "state" / "pct-list.txt").write_text("\n".join(pct) + "\n" if pct else "")
    for vmid, text in (configs or {}).items():
        (root / "state" / f"qm-config-{vmid}.txt").write_text(text)
    if pvesh is not None:
        (root / "state" / "pvesh.json").write_text(pvesh if isinstance(pvesh, str) else json.dumps(pvesh))
    world.roots["hv"] = root
    return m


def test_a_guest_the_manifest_does_not_know_is_flagged_with_how_to_add_it(world, capsys):
    """2026-10-19: three VMs of the 0mcp fleet were missed by a hand-made scan and kept the 7000-thread limit; the inventory notices a machine nobody listed."""
    with_inventory(world, qm=("101 h1 running", "102 h2 running", "103 brand-new-vm running"))
    assert world.main("drift", "--inventory") == 2
    out = capsys.readouterr().out
    assert "inventory hv (" in out and "3 guests, 2 managed, 0 exempt, 0 template(s) skipped, 1 finding(s)" in out
    assert "UNMANAGED  VM 103 brand-new-vm (running): not in hostconf.yaml; add it under hosts with `vm: {hypervisor: hv, id: 103}`" in out
    assert "1 hypervisor(s) listed: 1 finding(s)" in out


def test_exempt_guests_and_templates_are_not_findings(world, capsys):
    with_inventory(world, qm=("101 h1 running", "102 h2 running", "103 spare stopped", "9000 base-template stopped"), configs={9000: "name: base-template\ntemplate: 1\n"},
                   exempt=[(103, "a stopped spare: nothing runs on it, so there is no limit to be hit")])
    assert world.main("drift", "--inventory") == 0
    assert "4 guests, 2 managed, 1 exempt, 1 template(s) skipped" in capsys.readouterr().out


def test_a_container_is_listed_too(world, capsys):
    with_inventory(world, pct=("107 running pve-exporter",))
    assert world.main("drift", "--inventory") == 2
    assert "UNMANAGED  CT 107 pve-exporter (running)" in capsys.readouterr().out


def test_a_host_whose_guest_is_gone_and_an_exemption_that_no_longer_applies_are_flagged(world, capsys):
    with_inventory(world, qm=("101 h1 running",), exempt=[(555, "an old guest that was removed from the hypervisor")])
    assert world.main("drift", "--inventory") == 2
    out = capsys.readouterr().out
    assert "GONE  host h2 is guest 102 of hv, which no longer exists there" in out
    assert "STALE EXEMPTION  hv 555 no longer exists" in out


def test_all_lists_the_inventory_and_a_single_host_does_not(world, capsys):
    with_inventory(world, qm=("101 h1 running", "102 h2 running", "103 extra running"))
    assert world.main("drift", "--host", "h1") == 2  # h1's own file is missing, but no inventory section is printed
    assert "inventory hv" not in capsys.readouterr().out
    assert world.main("drift", "--all") == 2
    assert "inventory hv" in capsys.readouterr().out


def test_a_hypervisor_that_cannot_be_listed_is_not_reachable_not_clean(world, capsys):
    with_inventory(world)

    def dead(alias, script, timeout, sudo=True, via=None):
        return (255, "", "ssh: connect to host hv port 22: Operation timed out") if alias == "hv" else world.runner(alias, script, timeout, sudo, via)

    assert hostconf.main(["--manifest", str(world.manifest_path), "drift", "--inventory"], runner=dead) == 3
    assert "COULD NOT LIST: ssh: connect to host hv" in capsys.readouterr().out


def test_the_inventory_metrics(world, tmp_path):
    with_inventory(world, qm=("101 h1 running", "102 h2 running", "103 extra running"))
    out_dir = tmp_path / "textfile"
    world.main("drift", "--all", "--textfile-dir", str(out_dir))
    text = (out_dir / "fleet_hostconf.prom").read_text()
    assert 'fleet_hostconf_inventory_findings{hypervisor="hv"} 1' in text
    assert 'fleet_hostconf_inventory_unreachable{hypervisor="hv"} 0' in text


def test_a_guest_without_an_ssh_key_is_reached_through_its_hypervisors_agent(world, capsys):
    """VM 103 of the 0database fleet has no operator ssh access: the script goes to `qm guest exec 103 --pass-stdin` on the hypervisor."""
    with_inventory(world, qm=("101 h1 running", "102 h2 running", "103 spire running"),
                   extra_hosts={"g": {"vm": {"hypervisor": "hv", "id": 103}, "hostname": HERE, "files": ["threads"]}})
    world.calls_seen.clear()
    assert world.main("drift", "--host", "g") == 2
    out = capsys.readouterr().out
    assert "g (" in out and "guest agent of hv, vm 103" in out and "MISSING  /etc/sysctl.d/90-threads.conf" in out
    assert ("hv", True, 103) in world.calls_seen
    assert world.main("apply", "--host", "g", "--yes") == 0
    assert (world.roots["hv#103"] / "etc/sysctl.d/90-threads.conf").read_text() == THREADS
    assert world.main("drift", "--host", "g") == 0


def test_the_agent_transport_command_and_its_answer(monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"], seen["input"] = argv, kw["input"]
        return subprocess.CompletedProcess(argv, 0, json.dumps({"exitcode": 0, "exited": 1, "out-data": "HOSTCONF_RESULT {}\n", "err-data": ""}), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert hostconf.ssh_run("0database_bastion", "print(1)", 120, True, 103) == (0, "HOSTCONF_RESULT {}\n", "")
    assert seen["argv"][-14:] == ["0database_bastion", "sudo", "-n", "qm", "guest", "exec", "103", "--pass-stdin", "1", "--timeout", "120", "--", "python3", "-"]
    assert seen["argv"][-2:] == ["python3", "-"] and seen["input"] == "print(1)"
    # a guest command that fails, one that does not finish, and an answer that is not JSON
    assert hostconf._unwrap_guest_exec(0, json.dumps({"exitcode": 1, "exited": 1, "out-data": "", "err-data": "python3: not found"}), "") == (1, "", "python3: not found")
    rc, out, err = hostconf._unwrap_guest_exec(0, json.dumps({"exited": 0}), "")
    assert rc == 124 and "did not finish" in err
    assert hostconf._unwrap_guest_exec(255, "Connection refused", "x") == (255, "Connection refused", "x")


def test_the_inventory_takes_one_pvesh_call_when_it_answers_and_never_runs_qm(world, capsys):
    """On 2026-10-20 `qm list` took 20-60 s on 0own while a vzdump held the host at a load of 34: pvesh reads the state pvestatd already holds."""
    rows = [{"type": "qemu", "vmid": 101, "name": "h1", "status": "running"}, {"type": "qemu", "vmid": 102, "name": "h2", "status": "running"},
            {"type": "qemu", "vmid": 103, "name": "from-pvesh", "status": "running"}, {"type": "lxc", "vmid": 107, "name": "a-container", "status": "running"},
            {"type": "qemu", "vmid": 9000, "name": "base", "status": "stopped", "template": 1}, {"type": "storage", "id": "storage/x/local", "status": "available"}]
    with_inventory(world, qm=("101 h1 running",), pvesh=rows)  # qm list would show something else: the findings prove which source was read
    assert world.main("drift", "--inventory") == 2
    out = capsys.readouterr().out
    assert "UNMANAGED  VM 103 from-pvesh (running)" in out and "UNMANAGED  CT 107 a-container (running)" in out
    assert "5 guests, 2 managed, 0 exempt, 1 template(s) skipped, 2 finding(s)" in out
    assert not [c for c in world.calls("hv") if c.startswith(("qm ", "pct "))]
    assert [c for c in world.calls("hv") if c.startswith("pvesh get /cluster/resources")]


@pytest.mark.parametrize("answer", ["this is not json", "[1, 2, 3]", '{"data": []}'])
def test_a_pvesh_answer_that_cannot_be_read_falls_back_to_qm_and_pct(world, capsys, answer):
    with_inventory(world, qm=("101 h1 running", "102 h2 running", "104 only-in-qm running"), pvesh=answer)
    assert world.main("drift", "--inventory") == 2
    assert "UNMANAGED  VM 104 only-in-qm (running)" in capsys.readouterr().out
    assert [c for c in world.calls("hv") if c.startswith("qm list")]


def test_the_inventory_waits_long_enough_for_a_hypervisor_running_its_backups(world):
    with_inventory(world)
    seen = []

    def spy(alias, script, timeout, sudo=True, via=None):
        seen.append((alias, timeout))
        return world.runner(alias, script, timeout, sudo, via)

    hostconf.main(["--manifest", str(world.manifest_path), "drift", "--inventory"], runner=spy)
    assert seen == [("hv", 900)]


@pytest.mark.parametrize("label,mutate,needle", [
    ("vm without an inventory section", lambda m: (m.pop("inventory"), None)[1], "no `inventory` section"),
    ("vm on a hypervisor that is not listed", lambda m: m["hosts"]["h1"]["vm"].update(hypervisor="elsewhere"), "is not in inventory.hypervisors"),
    ("two hosts on one vmid", lambda m: m["hosts"]["h2"]["vm"].update(id=101), "is already host"),
    ("vm with the wrong shape", lambda m: m["hosts"]["h1"].update(vm={"hypervisor": "hv"}), "vm must be"),
    ("vmid not a number", lambda m: m["hosts"]["h1"]["vm"].update(id="101"), "vm must be"),
    ("hypervisor unknown", lambda m: m["inventory"].update(hypervisors=["hv", "nope"]), "unknown host nope"),
    ("hypervisor listed twice", lambda m: m["inventory"].update(hypervisors=["hv", "hv"]), "once each"),
    ("hypervisor without ssh", lambda m: m["hosts"]["hv"].pop("ssh"), "needs an ssh alias"),
    ("exempt without a reason", lambda m: m["inventory"].update(exempt=[{"hypervisor": "hv", "id": 9, "why": "short"}]), "why must say why"),
    ("exempt that is a managed host", lambda m: m["inventory"].update(exempt=[{"hypervisor": "hv", "id": 101, "why": "this one is managed, so it cannot be exempt"}]), "cannot also be exempt"),
    ("exempt on an unknown hypervisor", lambda m: m["inventory"].update(exempt=[{"hypervisor": "xx", "id": 9, "why": "an exemption on a hypervisor nobody lists"}]), "is not in inventory.hypervisors"),
    ("exempt twice", lambda m: m["inventory"].update(exempt=[{"hypervisor": "hv", "id": 9, "why": "the first of two identical exemptions"}, {"hypervisor": "hv", "id": 9, "why": "the second of two identical exemptions"}]), "exempt twice"),
    ("inventory with other keys", lambda m: m["inventory"].update(colour="red"), "only `hypervisors` and `exempt`"),
    ("a host with neither ssh nor vm", lambda m: m["hosts"].update(lost={"hostname": "lost", "files": ["threads"]}), "needs ssh (an alias) or vm"),
    ("sudo on a host reached through the agent", lambda m: m["hosts"].update(g={"vm": {"hypervisor": "hv", "id": 7}, "hostname": "g", "sudo": False, "files": ["threads"]}), "sudo only applies to an ssh login"),
])
def test_inventory_manifest_problems(world, label, mutate, needle):
    m = with_inventory(world)
    mutate(m)
    assert any(needle in p for p in hostconf.manifest_problems(m, world.files)), label


def test_the_shipped_manifest_knows_every_hypervisor_and_every_guest_it_runs():
    manifest = hostconf.load_manifest()
    inv = manifest["inventory"]
    assert inv["hypervisors"] == ["pve-0mcp", "pve-0infer", "bastion", "pve-0own", "pve-0pipe"]  # pve-0pipe added 2026-10-29 (Hetzner HEL1 build host); pve-0database (pve01, cancelled) left on 2026-10-22: unreachable, nothing to check
    hosts = manifest["hosts"]
    assert hosts["infer-runtime"]["vm"] == {"hypervisor": "pve-0infer", "id": 703}
    assert hosts["docker-runtime"]["vm"] == {"hypervisor": "pve-0mcp", "id": 120}
    assert hosts["0own-build-worker"]["vm"] == {"hypervisor": "pve-0own", "id": 610}
    # the three 0mcp VMs a hand-made scan missed on 2026-10-19, still at the ~7000 limit, and the VM no operator can ssh into
    for name, vmid in (("postgres-apps-lv3", 152), ("postgres-replica-lv3", 151), ("runtime-ai-lv3", 190)):
        assert hosts[name]["vm"] == {"hypervisor": "pve-0mcp", "id": vmid} and "sysctl-hotplug-threads-max" in hosts[name]["files"]
    spire = hosts["infer-spire"]
    assert "ssh" not in spire and spire["vm"] == {"hypervisor": "pve-0infer", "id": 705} and "sysctl-hotplug-threads-max" in spire["files"]
    # the 0database hypervisor (pve01) and its four guests are gone from the manifest: the server was cancelled (2026-10-22), the check cannot reach it and nothing may point at it
    assert "pve-0database" not in hosts and not [e for e in inv["exempt"] if e["hypervisor"] == "pve-0database"]
    assert not [h for h in hosts.values() if (h.get("vm") or {}).get("hypervisor") == "pve-0database"]
    assert all(e["why"].strip() for e in inv["exempt"]) and len(inv["exempt"]) >= 2
    managed = {(h["vm"]["hypervisor"], h["vm"]["id"]) for h in hosts.values() if "vm" in h}
    assert len(managed) >= 36  # 38 before the four 0database guests (100 to 103) were retired on 2026-10-21


# ───────────────────────────── adopt ─────────────────────────────


def test_adopt_copies_the_live_file_byte_for_byte(world, capsys):
    live = "[Service]\r\nRestart=on-failure\r\n".encode()  # not something check would accept: adopt refuses it
    d = world.dest("h1", "/etc/systemd/system/nginx.service.d/override.conf")
    d.parent.mkdir(parents=True)
    d.write_bytes(live)
    (world.files / "nginx.conf").unlink()
    assert world.main("adopt", "--host", "h1", "--file", "nginx-restart") == 1
    assert "not adoptable" in capsys.readouterr().err and not (world.files / "nginx.conf").exists()
    d.write_bytes(b"# \xc3\xa9 as it is on the host\n[Service]\nRestart=on-failure\nOOMPolicy=continue\n")
    assert world.main("adopt", "--host", "h1", "--file", "nginx-restart") == 0
    assert (world.files / "nginx.conf").read_bytes() == d.read_bytes()
    assert "adopted /etc/systemd/system/nginx.service.d/override.conf from h1" in capsys.readouterr().out


def test_adopt_refuses_a_file_with_a_credential_and_a_file_that_is_not_there(world, capsys):
    d = world.dest("h1", "/etc/systemd/system/nginx.service.d/override.conf")
    d.parent.mkdir(parents=True)
    d.write_text("[Service]\nEnvironment=API_TOKEN=hunter2hunter2\n")
    (world.files / "nginx.conf").unlink()
    assert world.main("adopt", "--host", "h1", "--file", "nginx-restart") == 1
    assert "credential" in capsys.readouterr().err and not (world.files / "nginx.conf").exists()
    d.unlink()
    assert world.main("adopt", "--host", "h1", "--file", "nginx-restart") == 1
    assert "does not exist on h1" in capsys.readouterr().err


def test_adopt_needs_one_host_and_one_file_that_the_manifest_lists(world, capsys):
    assert world.main("adopt", "--host", "h1") == 1
    assert world.main("adopt", "--host", "h2", "--file", "threads") == 1
    assert "must be listed in the manifest for host h2 first" in capsys.readouterr().err


# ───────────────────────────── command line ─────────────────────────────


def test_a_host_must_be_named_or_all_used(world, capsys):
    assert world.main("drift") == 1
    assert "name at least one --host" in capsys.readouterr().err
    assert world.main("drift", "--host", "nope") == 1
    assert "unknown host" in capsys.readouterr().err


def test_an_invalid_manifest_stops_every_command_except_check_and_adopt(world, capsys):
    m = load(world)
    m["files"]["threads"]["dest"] = "/etc/hosts"
    world.manifest_path.write_text(yaml.safe_dump(m))
    assert world.main("check") == 1
    assert "PROBLEM threads: dest '/etc/hosts' is not a path this tool may write" in capsys.readouterr().out
    assert world.main("drift", "--all") == 1
    assert "the manifest is not valid" in capsys.readouterr().err
    assert world.main("apply", "--all", "--yes") == 1


def test_the_real_ssh_runner_calls_sudo_python_with_the_script_on_stdin(monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"], seen["input"] = argv, kw["input"]
        return subprocess.CompletedProcess(argv, 0, "HOSTCONF_RESULT {}", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert hostconf.ssh_run("webgateway", "print(1)") == (0, "HOSTCONF_RESULT {}", "")
    assert seen["argv"][:3] == ["ssh", "-o", "BatchMode=yes"] and seen["argv"][-5:] == ["webgateway", "sudo", "-n", "python3", "-"]
    assert seen["input"] == "print(1)"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("ssh", 1)))
    assert hostconf.ssh_run("webgateway", "x")[0] == 255


def test_noise_around_the_result_line_does_not_matter_and_no_result_line_is_unreachable(world):
    m = load(world)
    ok = lambda alias, script, t, sudo=True: (0, "Warning: Permanently added 'x'\nHOSTCONF_RESULT " + json.dumps({"files": [], "expects": []}) + "\nbye\n", "")
    assert hostconf.run_on_host(m, "h1", "observe", None, ok)["files"] == []
    none = lambda alias, script, t, sudo=True: (1, "sudo: a password is required\n", "")
    assert "a password is required" in hostconf.run_on_host(m, "h1", "observe", None, none)["unreachable"]
    bad = lambda alias, script, t, sudo=True: (0, "HOSTCONF_RESULT {not json\n", "")
    assert "unreachable" in hostconf.run_on_host(m, "h1", "observe", None, bad)


def test_the_script_is_the_only_thing_sent_and_carries_no_repo_secret_free_content_beyond_the_files(world):
    host = load(world)["hosts"]["h1"]
    script = hostconf.build_script("observe", host, hostconf.host_files(load(world), "h1"))
    spec_b64 = script.split('base64.b64decode("')[1].split('")')[0]
    spec_json = json.loads(base64.b64decode(spec_b64))
    assert spec_json["hostname"] == HERE and spec_json["mode"] == "observe"
    assert {f["dest"] for f in spec_json["files"]} == {"/etc/systemd/system/nginx.service.d/override.conf", "/etc/sysctl.d/90-threads.conf"}
    assert "@@SPEC@@" not in script
    compile(script, "<remote>", "exec")


def test_the_check_and_the_tests_run_in_ci():
    ci = (Path(__file__).resolve().parents[1] / ".woodpecker.yml").read_text()
    assert "tests/test_hostconf.py" in ci and "scripts/hostconf.py check" in ci
