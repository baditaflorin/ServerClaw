"""The stopgap swapfile of the 0mcp hypervisor (pve-0mcp), config/0mcp/hypervisor-swap, added by hand on 2026-11-01 22:03Z.

Pinned here: the installer against a fake host (every verb, every guard, the order of the mutating calls, what it must not touch); the fstab rewrite as a pure function;
the README, the installer and the read-only capture agree; hostconf still has no swap or fstab kind (this is why the install-script pattern is used); and a mutation sweep that
breaks each guard of the installer on purpose to prove the tests above would notice.

The installer is sourced, its variables are pointed into a temporary directory and `main` is called; its tools (stat, blkid, fallocate, mkswap, swapon, swapoff, findmnt, df, id,
hostname, systemctl) are stubs on PATH that keep their state in files and log every mutating call. Nothing here touches a real swap area or a real /etc/fstab.
"""

from __future__ import annotations

import atexit
import functools
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
D = REPO / "config/0mcp/hypervisor-swap"
SCRIPT = D / "install-host.sh"
README = D / "README.md"
SNAPSHOT = D / "live-state-20261101.txt"
RULES = REPO / "config/prometheus/rules/fleet-hypervisor-memory.yml"
WORKSTREAM = REPO / "workstreams/active/ws-20261101-hypervisor-swap-stopgap.yaml"

spec = importlib.util.spec_from_file_location("hostconf_hypervisor_swap", REPO / "scripts/hostconf.py")
hostconf = importlib.util.module_from_spec(spec)
sys.modules["hostconf_hypervisor_swap"] = hostconf
spec.loader.exec_module(hostconf)

BASH = shutil.which("bash") or "/bin/bash"
HOST = "debian-base-template"
GiB = 2**30
PATH_ = "/swapfile-0mcp-stopgap"
LINE = "/swapfile-0mcp-stopgap none swap sw,nofail 0 0"
LIVE_UUID = "c6e053ea-ed3a-4826-b2b7-b8f262f791a1"
SIZE = 65536  # the installer's SIZE_BYTES inside the tests: the logic does not need a 32 GiB file
MIN_FREE = 1000
NEED = SIZE + MIN_FREE
MUTATING = ("fallocate", "mkswap", "swapon", "swapoff", "systemctl")


def snapshot_block(title: str) -> str:
    """The lines under `$ <title>...` in the read-only capture, up to the next blank line."""
    lines = SNAPSHOT.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"$ {title}"))
    out = []
    for line in lines[start + 1 :]:
        if not line.strip():
            break
        out.append(line)
    return "\n".join(out) + "\n"


FSTAB_LIVE = snapshot_block("cat /etc/fstab")
MD0 = "/dev/md0                                partition\t4189180\t3882812\t-1\n"
SWAPS_HEADER = "Filename\t\t\t\tType\t\tSize\t\tUsed\t\tPriority\n"

# ───────────────────────────── the fake host ─────────────────────────────

STUB = r"""
import os
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(os.environ["FAKE_ROOT"])
STATE = ROOT / "state"
name = os.path.basename(sys.argv[0])
args = sys.argv[1:]


def get(key, default=""):
    p = STATE / key
    return p.read_text().strip() if p.exists() else default


def log(extra=""):
    with (ROOT / "calls.log").open("a") as f:
        f.write((name + " " + " ".join(args) + extra).strip() + "\n")


def failing():
    return name in get("fail").split(",")


def signature(path):
    try:
        head = open(path, "rb").read(256).decode("latin1")
    except OSError:
        return None
    m = re.match(r"SWAPFAKE label=(\S*) uuid=(\S+)\n", head)
    if m:
        return {"TYPE": "swap", "LABEL": m.group(1), "UUID": m.group(2)}
    if head.startswith("OTHERFS"):
        return {"TYPE": "ext4"}
    return None


def swaps():
    p = ROOT / "proc_swaps"
    return p.read_text().splitlines(keepends=True)


if name == "id":
    print(get("uid", "0"))
elif name == "hostname":
    print(get("hostname"))
elif name == "df":
    print("      Avail")
    print(get("avail"))
elif name == "stat":
    fmt, path = args[1], args[2]
    st = os.stat(path)
    print({"%s": str(st.st_size), "%a": format(st.st_mode & 0o777, "o"), "%U:%G": get("owner", "root:root")}[fmt])
elif name == "blkid":
    sig = signature(args[-1])
    if not sig:
        sys.exit(2)
    print("DEVNAME=" + args[-1])
    for key in ("LABEL", "UUID", "TYPE"):
        if key in sig:
            print(key + "=" + sig[key])
elif name == "fallocate":
    log()
    if os.path.exists(args[2]):
        sys.exit(1)
    fd = os.open(args[2], os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)  # the umask decides the mode, as for the real tool
    if failing():
        os.close(fd)  # a partial file stays behind, as after ENOSPC
        sys.exit(1)
    os.ftruncate(fd, int(args[1]))
    os.close(fd)
elif name == "mkswap":
    log(" mode=" + format(os.stat(args[2]).st_mode & 0o777, "o"))
    if failing():
        sys.exit(1)
    with open(args[2], "r+b") as f:
        f.write(("SWAPFAKE label=%s uuid=%s\n" % (args[1], uuid.uuid4())).encode())
    print("Setting up swapspace version 1")
elif name == "swapon":
    log(" exists=" + str(os.path.exists(args[0])))
    if failing() or any(line.split()[0] == args[0] for line in swaps()[1:]):
        sys.exit(255)
    with (ROOT / "proc_swaps").open("a") as f:
        f.write("%s\tfile\t%d\t0\t-1\n" % (args[0], os.stat(args[0]).st_size // 1024 - 4))
elif name == "swapoff":
    log()
    rest = [line for line in swaps() if line.split()[0] != args[0]]
    if failing() or len(rest) == len(swaps()):
        sys.exit(255)
    (ROOT / "proc_swaps").write_text("".join(rest))
elif name == "systemctl":
    log()
elif name == "findmnt":
    if "-T" in args:
        print(get("fstype", "ext4"))
        sys.exit(0)
    tab = args[args.index("--tab-file") + 1] if "--tab-file" in args else str(ROOT / "fstab")
    columns = args[args.index("-o") + 1].split(",")
    wanted = args[args.index("-S") + 1]
    for line in open(tab):
        f = line.split()
        if len(f) >= 4 and not line.lstrip().startswith("#") and f[0] == wanted:
            rec = {"SOURCE": f[0], "TARGET": f[1], "FSTYPE": f[2], "OPTIONS": f[3]}
            wrong = get("findmnt_candidate_wrong" if "--tab-file" in args else "findmnt_readback_wrong")
            if wrong:
                rec["OPTIONS"] = wrong
            print(" ".join(rec[c] for c in columns))
            sys.exit(0)
    sys.exit(1)
else:
    sys.exit("no stub for " + name)
"""

STUBS = ("id", "hostname", "df", "stat", "blkid", "fallocate", "mkswap", "swapon", "swapoff", "findmnt", "systemctl")


@functools.lru_cache(maxsize=None)
def stub_bin() -> Path:
    """One directory of stubs for the whole run (every Host keeps its own state under FAKE_ROOT): a new executable costs a scan on some machines."""
    d = Path(tempfile.mkdtemp(prefix="hypervisor-swap-stubs-"))
    atexit.register(shutil.rmtree, d, ignore_errors=True)
    for tool in STUBS:
        stub = d / tool
        stub.write_text(f"#!{sys.executable}\n{STUB}")
        stub.chmod(0o755)
    return d


OVERRIDES = """
SWAPFILE="$FAKE_ROOT/swapfile"; SIZE_BYTES=%d; MIN_FREE_BYTES=%d; FSTAB="$FAKE_ROOT/fstab"
PROC_SWAPS="$FAKE_ROOT/proc_swaps"; PROC_MEMINFO="$FAKE_ROOT/meminfo"; PVE_NODES="$FAKE_ROOT/pve_nodes"
LINE="$SWAPFILE none swap $FSTAB_OPTIONS 0 0"
%s
main "$@"
"""


class Host:
    """A fake pve-0mcp as read on 2026-11-01: the installer's variables point into `root`, the swapfile is as wanted and active, fstab has no line for it."""

    def __init__(self, root: Path, script: Path = SCRIPT, *, swapfile: bool = True, active: bool = True):
        self.root, self.script = root, script
        self.file = root / "swapfile"
        self.fstab = root / "fstab"
        self.proc_swaps = root / "proc_swaps"
        self.meminfo = root / "meminfo"
        self.extra = ""
        (root / "state").mkdir(parents=True)
        (root / "pve_nodes" / HOST).mkdir(parents=True)
        for key, value in (("hostname", HOST), ("uid", "0"), ("fstype", "ext4"), ("avail", str(10**12))):
            self.set(key, value)
        self.fstab.write_text(FSTAB_LIVE)
        self.proc_swaps.write_text(SWAPS_HEADER + MD0)
        self.set_available(8 * GiB)
        if swapfile:
            self.make_swapfile()
        if swapfile and active:
            self.activate()

    def set(self, key: str, value: str) -> None:
        (self.root / "state" / key).write_text(value)

    def set_available(self, n: int) -> None:
        self.meminfo.write_text(f"MemTotal:       131805900 kB\nMemAvailable:   {n // 1024} kB\n")

    def make_swapfile(
        self, *, label: str = "stopgap", size: int = SIZE, mode: int = 0o600, header: str | None = None
    ) -> None:
        head = header if header is not None else f"SWAPFAKE label={label} uuid={LIVE_UUID}\n"
        self.file.write_bytes(head.encode().ljust(size, b"\0"))
        self.file.chmod(mode)

    def activate(self, used_kib: int = 0) -> None:
        with self.proc_swaps.open("a") as f:
            f.write(f"{self.file}\tfile\t{SIZE // 1024 - 4}\t{used_kib}\t-1\n")

    def persist_line(self) -> None:
        self.fstab.write_text(FSTAB_LIVE + f"{self.file} none swap sw,nofail 0 0\n")

    def run(self, *args: str) -> subprocess.CompletedProcess:
        env = {
            "PATH": f"{stub_bin()}{os.pathsep}{os.environ['PATH']}",
            "FAKE_ROOT": str(self.root),
            "LC_ALL": "C",
            "HOME": str(self.root),
        }
        return subprocess.run(
            [
                BASH,
                "-c",
                f'source "$1"; shift; {OVERRIDES % (SIZE, MIN_FREE, self.extra)}',
                "_",
                str(self.script),
                *args,
            ],
            capture_output=True,
            text=True,
            env=env,
        )

    def calls(self) -> list[str]:
        log = self.root / "calls.log"
        return log.read_text().splitlines() if log.exists() else []

    def mutations(self) -> list[str]:
        return [c for c in self.calls() if c.split()[0] in MUTATING]

    def backups(self) -> list[Path]:
        return sorted(self.root.glob("fstab.bak-swap-*"))

    def leftovers(self) -> list[Path]:
        return sorted(p for p in self.root.iterdir() if ".new-" in p.name)

    def fstab_text(self) -> str:
        return self.fstab.read_text()

    def swaps(self) -> str:
        return self.proc_swaps.read_text()


@pytest.fixture
def live(tmp_path):
    return Host(tmp_path)


@pytest.fixture
def empty(tmp_path):
    """A rebuilt host: no file, not swap."""
    return Host(tmp_path, swapfile=False)


def untouched(h: Host, before_fstab: str = FSTAB_LIVE) -> None:
    """A refused run changed nothing: no mutating call, fstab as before, no backup, no temporary file."""
    assert h.mutations() == []
    assert h.fstab_text() == before_fstab and h.backups() == [] and h.leftovers() == []


# ───────────────────────────── the script itself ─────────────────────────────


def shell(code: str, text: str | None = None) -> subprocess.CompletedProcess:
    """bash -c `code` with the installer sourced ($1): only the functions and variables exist, the installer does not run."""
    return subprocess.run(
        [BASH, "-c", f'source "$1" && {code}', "_", str(SCRIPT)], input=text, capture_output=True, text=True
    )


def installer_var(name: str) -> str:
    p = shell(f'printf %s "${{{name}}}"')
    assert p.returncode == 0, p.stderr
    return p.stdout


def rewrite(fn: str, text: str) -> str:
    p = shell(fn, text)
    assert p.returncode == 0, p.stderr
    return p.stdout


def test_the_installer_is_valid_shell_executable_and_has_every_verb():
    subprocess.run([BASH, "-n", str(SCRIPT)], check=True)
    assert os.access(SCRIPT, os.X_OK), "the other installers of config/0mcp and config/0infer are executable"
    text = SCRIPT.read_text()
    for verb in ("check", "--apply", "--persist", "--remove", "--help"):
        assert verb in text, verb
    assert "swapoff -a" not in "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def test_sourcing_the_installer_runs_nothing(tmp_path):
    """The tests rely on this: an empty PATH would make `id`, `hostname` and `date` fail at once if main ran."""
    p = subprocess.run(
        [BASH, "-c", 'source "$1" && echo defined', "_", str(SCRIPT)],
        capture_output=True,
        text=True,
        env={"PATH": str(tmp_path)},
    )
    assert p.returncode == 0 and p.stdout == "defined\n", p.stderr


def test_streamed_through_ssh_the_installer_runs():
    """`ssh host 'bash -s -- check' < install-host.sh` has no BASH_SOURCE: main must still run (--help is the one verb that needs neither root nor the host)."""
    p = subprocess.run([BASH, "-s", "--", "--help"], input=SCRIPT.read_text(), capture_output=True, text=True)
    assert p.returncode == 0 and "usage: install-host.sh" in p.stdout and "--persist" in p.stdout, p.stderr


def test_executed_on_this_machine_it_refuses(tmp_path):
    """Not root, or not pve-0mcp: exit 1 and a message, whichever of the two guards stops it first."""
    p = subprocess.run([BASH, str(SCRIPT), "check"], capture_output=True, text=True)
    assert p.returncode == 1 and "install-host.sh:" in p.stderr, (p.stdout, p.stderr)


@pytest.mark.parametrize("args", [("--nope",), ("check", "--remove"), ("--apply", "--persist")])
def test_unknown_verbs_and_two_verbs_are_refused_with_the_usage(live, args):
    p = live.run(*args)
    assert p.returncode == 1 and "usage: install-host.sh" in p.stderr
    untouched(live)


# ───────────────────────────── constants, README, capture ─────────────────────────────


def test_the_constants_and_the_readme_agree():
    assert installer_var("SWAPFILE") == PATH_
    assert installer_var("SIZE") == "32G" and int(installer_var("SIZE_BYTES")) == 32 * GiB == 34359738368
    assert installer_var("LABEL") == "stopgap"
    assert int(installer_var("MIN_FREE_BYTES")) == 200 * 10**9
    assert installer_var("FSTYPE_WANTED") == "ext4" and installer_var("HOST_WANTED") == HOST
    assert installer_var("LINE") == LINE
    text = README.read_text()
    assert f"`{LINE}`" in text, "the README must quote the installer's fstab line"
    for needle in (
        PATH_,
        "34,359,738,368",
        "32 GiB",
        "mkswap -L stopgap",
        LIVE_UUID,
        HOST,
        "/dev/md2",
        "ext4",
        "priority -1",
        "2026-11-01",
        "22:03Z",
        "at least 200 GB free after the 32 GiB file",
        "234 GB",
        "half of MemAvailable",
        "`--apply`",
        "`--persist`",
        "`--remove`",
        "fstab.bak-swap-",
        "swapoff /swapfile-0mcp-stopgap && rm /swapfile-0mcp-stopgap",
        "PR 653",
        "Not here, on purpose",
        "When to remove it",
    ):
        assert needle in text, needle


def test_the_exit_codes_in_the_readme_are_the_installers():
    text = README.read_text()
    for row in ("| 0 |", "| 1 |", "| 2 |", "| 3 |"):
        assert row in text, row
    script = SCRIPT.read_text()
    assert (
        "Exit codes: 0 everything as wanted" in script
        and "2 check: usable now but not persisted" in script
        and "3 check: not as wanted" in script
    )


def test_the_capture_agrees_with_the_installer_and_the_readme():
    snap = SNAPSHOT.read_text()
    assert f"600 root:root {32 * GiB} {PATH_}" in snap
    assert f"UUID={LIVE_UUID}" in snap and "LABEL=stopgap" in snap and "TYPE=swap" in snap
    assert f"{PATH_} file      {32 * GiB - 4096}" in snap, "the swap area is one page smaller than the file"
    assert "/dev/md2 ext4 /" in snap and "624423714816" in snap
    swaps = snapshot_block("cat /proc/swaps")
    prios = [line.split()[-1] for line in swaps.splitlines()[1:]]
    assert prios == ["-1", "-1"], "both areas at the auto priority -1, as the README says"
    assert PATH_ not in FSTAB_LIVE, "the capture is of a host where the swapfile is not in fstab"
    assert re.search(r"^UUID=00273bec-\S+ none swap sw 0 0$", FSTAB_LIVE, re.M), (
        "the md0 swap line is the only swap line"
    )
    assert len([line for line in FSTAB_LIVE.splitlines() if " swap " in line]) == 1
    assert (
        "swapfile\\x2d0mcp\\x2dstopgap.swap" in snap
        and README.read_text().count("swapfile\\x2d0mcp\\x2dstopgap.swap") == 1
    )
    check_out = snapshot_block("ssh operator-bastion 'bash -s -- check'")
    assert "file       ok       32 GiB (34359738368 bytes), mode 600, root:root" in check_out
    assert "active     ok" in check_out and "fstab      absent" in check_out
    assert check_out.rstrip().endswith("exit=2"), "the installer's own check of the live host: usable, not persisted"
    text = README.read_text()
    assert (
        "1.88 TB" in text
        and "624 GB free" in text
        and "37,743,608 kB" in text
        and "7,992,408 kB" in text
        and "329 extents" in text
    )


def test_the_readmes_alert_table_matches_the_rules_in_this_repo():
    rules = {r["alert"]: r for g in yaml.safe_load(RULES.read_text())["groups"] for r in g["rules"]}
    low, crit, swap = (
        rules[n]
        for n in (
            "FleetHypervisorMemAvailableLow",
            "FleetHypervisorMemAvailableCritical",
            "FleetHypervisorSwapExhausted",
        )
    )
    assert "< 0.05" in low["expr"] and low["for"] == "10m" and low["labels"]["severity"] == "warning"
    assert "< 0.03" in crit["expr"] and crit["for"] == "5m" and crit["labels"]["severity"] == "critical"
    assert "< 0.10" in swap["expr"] and swap["for"] == "15m" and swap["labels"]["severity"] == "warning"
    text = README.read_text()
    for name in rules:
        assert name in text, name
    assert (
        "ProxmoxHostMemoryExhausted" in text
        and "ProxmoxHostMemoryHeadroomLow" in text
        and "go-fleet-metrics-hub" in text
    )
    assert "32.4 GiB" in text, "90 % of 36 GiB: what FleetHypervisorSwapExhausted needs now"


def test_hostconf_has_no_swap_or_fstab_kind_and_the_installers_host_is_the_manifests():
    """This is why the install-script pattern is used. If hostconf ever manages fstab or a swapfile, move this there and delete this test."""
    assert set(hostconf.KIND_PATTERNS) == {"systemd_dropin", "sysctl", "pg_conf_d"}
    for dest in ("/etc/fstab", PATH_, "/etc/fstab.d/swap.conf"):
        assert hostconf.kind_of(dest) is None, dest
    manifest = hostconf.load_manifest()
    assert manifest["hosts"]["pve-0mcp"]["hostname"] == installer_var("HOST_WANTED") == HOST
    assert sum(1 for h in manifest["hosts"].values() if h.get("hostname") == HOST) == 1, (
        "the hostname guard names exactly one machine"
    )
    text = README.read_text()
    assert "KIND_PATTERNS" in text and "Why not hostconf" in text


def test_the_workstream_owns_exactly_these_files():
    shard = yaml.safe_load(WORKSTREAM.read_text())
    owned = {p for s in shard["ownership_manifest"]["owned_surfaces"] for p in s["paths"]}
    for p in (README, SCRIPT, SNAPSHOT, Path(__file__)):
        assert str(p.relative_to(REPO)) in owned, p
    assert shard["live_applied"] is True and shard["adr"] == "0494"


def test_no_workstation_path_and_no_secret_in_the_committed_files():
    """AGENTS.md, public repo mode: no absolute workstation paths; the capture holds filesystem UUIDs only."""
    for f in (SCRIPT, README, SNAPSHOT, WORKSTREAM, REPO / "docs/workstreams/ws-20261101-hypervisor-swap-stopgap.md"):
        text = f.read_text()
        assert not re.search(r"/Users/|/home/[a-z]|fleet_agent_primitives", text), f
        assert not re.search(r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*\S{12,}", text), f
        assert not re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", text), f


# ───────────────────────────── the fstab rewrite (a pure function of its input) ─────────────────────────────

HEAD = "# /etc/fstab\nUUID=abcd / ext4 defaults 0 1\nUUID=0027 none swap sw 0 0\n"

CASES = {
    "no line yet": (HEAD, HEAD + LINE + "\n"),
    "the line is already there": (HEAD + LINE + "\n", HEAD + LINE + "\n"),
    "another option set": (HEAD + f"{PATH_} none swap sw 0 0\n", HEAD + LINE + "\n"),
    "a priority is replaced": (HEAD + f"{PATH_} none swap sw,pri=5,nofail 0 0\n", HEAD + LINE + "\n"),
    "a second line is dropped": (HEAD + LINE + "\n" + f"{PATH_} none swap sw 0 0\n", HEAD + LINE + "\n"),
    "a commented line is not the line": (HEAD + f"#{LINE}\n# {LINE}\n", HEAD + f"#{LINE}\n# {LINE}\n" + LINE + "\n"),
    "another file with the same prefix is not touched": (
        HEAD + f"{PATH_}2 none swap sw 0 0\n",
        HEAD + f"{PATH_}2 none swap sw 0 0\n" + LINE + "\n",
    ),
    "a mount of the same path is not the swap line": (
        HEAD + f"{PATH_} /mnt ext4 defaults 0 0\n",
        HEAD + f"{PATH_} /mnt ext4 defaults 0 0\n" + LINE + "\n",
    ),
}


@pytest.mark.parametrize("name", CASES)
def test_the_fstab_rewrite(name):
    before, after = CASES[name]
    once = rewrite("fstab_with_swap", before)
    assert once == after
    assert rewrite("fstab_with_swap", once) == once, "a second run must change nothing"


def test_a_line_that_already_says_it_is_kept_byte_for_byte():
    odd = HEAD + f"{PATH_}\tnone\tswap\tsw,nofail\t0\t0\n"
    assert rewrite("fstab_with_swap", odd) == odd
    short = HEAD + f"{PATH_} none swap sw,nofail\n"
    assert rewrite("fstab_with_swap", short) == short


@pytest.mark.parametrize("name", CASES)
def test_the_undo_removes_only_the_swapfile_line(name):
    _, after = CASES[name]
    expected = "".join(
        line for line in after.splitlines(keepends=True) if not re.match(rf"{re.escape(PATH_)}\s+\S+\s+swap\s", line)
    )
    assert rewrite("fstab_without_swap", after) == expected
    assert "UUID=0027 none swap sw 0 0" in rewrite("fstab_without_swap", after), "the md0 swap line is never touched"


def test_add_then_undo_gives_the_original_file_back_and_the_live_fstab_keeps_its_other_lines():
    assert rewrite("fstab_without_swap", rewrite("fstab_with_swap", HEAD)) == HEAD
    added = rewrite("fstab_with_swap", FSTAB_LIVE)
    assert added == FSTAB_LIVE + LINE + "\n"
    assert rewrite("fstab_without_swap", added) == FSTAB_LIVE


# ───────────────────────────── check (read-only) ─────────────────────────────


def test_check_on_the_live_host_is_usable_but_not_persisted(live):
    p = live.run("check")
    assert p.returncode == 2, (p.stdout, p.stderr)
    assert (
        "file       ok" in p.stdout
        and f"uuid {LIVE_UUID}" in p.stdout
        and "mode 600, root:root" in p.stdout
        and "label stopgap" in p.stdout
    )
    assert "active     ok" in p.stdout and "fstab      absent" in p.stdout
    untouched(live)


def test_check_is_the_default_verb(live):
    p = live.run()
    assert p.returncode == 2 and "fstab      absent" in p.stdout
    untouched(live)


def test_check_is_zero_when_everything_is_as_wanted(live):
    live.persist_line()
    p = live.run("check")
    assert p.returncode == 0 and "fstab      ok" in p.stdout, (p.stdout, p.stderr)
    untouched(live, live.fstab_text())


def test_check_after_a_reboot_says_not_active(live):
    live.proc_swaps.write_text(SWAPS_HEADER + MD0)
    live.persist_line()
    p = live.run("check")
    assert p.returncode == 3 and "active     MISSING" in p.stdout and "install-host.sh --apply" in p.stdout
    untouched(live, live.fstab_text())


def test_check_on_a_rebuilt_host_says_missing(empty):
    p = empty.run("check")
    assert p.returncode == 3 and "file       MISSING" in p.stdout
    untouched(empty)


@pytest.mark.parametrize("what", ["size", "mode", "label", "signature"])
def test_check_names_a_file_that_is_not_as_wanted(live, what):
    if what == "size":
        live.make_swapfile(size=SIZE * 2)
    elif what == "mode":
        live.file.chmod(0o644)
    elif what == "label":
        live.make_swapfile(label="other")
    else:
        live.make_swapfile(header="OTHERFS\n")
    p = live.run("check")
    assert p.returncode == 3 and "file       WRONG" in p.stdout
    untouched(live)


# ───────────────────────────── apply and persist on the live host ─────────────────────────────


def test_apply_on_the_live_host_changes_nothing(live):
    p = live.run("--apply")
    assert p.returncode == 0 and "already as wanted" in p.stdout and "already active" in p.stdout, (p.stdout, p.stderr)
    untouched(live)


def test_persist_on_the_live_host_only_adds_the_fstab_line(live):
    """The case the owner's yes is for: the file and the swap area are as wanted, so the run touches /etc/fstab and reloads the units, nothing else."""
    p = live.run("--persist")
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert live.fstab_text() == FSTAB_LIVE + f"{live.file} none swap sw,nofail 0 0\n"
    assert live.mutations() == ["systemctl daemon-reload"], "no fallocate, no mkswap, no swapon, no swapoff"
    assert [b.read_text() for b in live.backups()] == [FSTAB_LIVE], "the backup is the exact file from before"
    assert live.leftovers() == []
    assert (live.fstab.stat().st_mode & 0o777) == (live.backups()[0].stat().st_mode & 0o777)
    assert live.run("check").returncode == 0


def test_a_second_persist_changes_nothing_and_makes_no_backup(live):
    assert live.run("--persist").returncode == 0
    after, backups, calls = live.fstab_text(), live.backups(), live.calls()
    p = live.run("--persist")
    assert p.returncode == 0 and "already as wanted" in p.stdout
    assert live.fstab_text() == after and live.backups() == backups and live.calls() == calls


def test_the_free_space_guard_does_not_apply_to_a_file_that_already_exists(live):
    """624 GB free today; with 1 byte free the existing 32 GiB file is still fine to persist: it is already allocated."""
    live.set("avail", "1")
    p = live.run("--persist")
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert live.mutations() == ["systemctl daemon-reload"]


def test_a_persist_whose_candidate_does_not_read_back_changes_nothing(live):
    live.set("findmnt_candidate_wrong", "bogus")
    p = live.run("--persist")
    assert p.returncode == 1 and "reads back as 'bogus'" in p.stderr and "was not changed" in p.stderr
    untouched(live)


def test_a_persist_whose_result_does_not_read_back_puts_the_backup_back(live):
    live.set("findmnt_readback_wrong", "bogus")
    p = live.run("--persist")
    assert p.returncode == 1 and "the backup is back in place" in p.stderr
    assert live.fstab_text() == FSTAB_LIVE
    assert [b.read_text() for b in live.backups()] == [FSTAB_LIVE]
    assert live.mutations() == ["systemctl daemon-reload", "systemctl daemon-reload"], (
        "reloaded after the change and again after the restore"
    )


# ───────────────────────────── creating the file on a rebuilt host, and the states in between ─────────────────────────────


def test_apply_creates_formats_and_enables_in_that_order_and_leaves_fstab_alone(empty):
    p = empty.run("--apply")
    assert p.returncode == 0, (p.stdout, p.stderr)
    fallocate, mkswap, swapon = empty.mutations()
    tmp = empty.file.with_name(empty.file.name + ".new-")
    assert fallocate.startswith(f"fallocate -l {SIZE} {tmp}") and ".new-" in fallocate
    assert mkswap.startswith("mkswap -L stopgap ") and ".new-" in mkswap and mkswap.endswith("mode=600"), (
        "formatted under a temporary name, already mode 600"
    )
    assert swapon == f"swapon {empty.file} exists=True", "the final name exists before swapon"
    assert empty.file.stat().st_size == SIZE and (empty.file.stat().st_mode & 0o777) == 0o600
    assert f"{empty.file}\tfile" in empty.swaps()
    assert empty.fstab_text() == FSTAB_LIVE and empty.backups() == [] and empty.leftovers() == []
    assert empty.run("check").returncode == 2


def test_persist_on_a_rebuilt_host_does_everything(empty):
    p = empty.run("--persist")
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert [m.split()[0] for m in empty.mutations()] == ["fallocate", "mkswap", "swapon", "systemctl"]
    assert empty.fstab_text() == FSTAB_LIVE + f"{empty.file} none swap sw,nofail 0 0\n"
    assert empty.run("check").returncode == 0


def test_after_a_reboot_apply_only_runs_swapon(live):
    live.proc_swaps.write_text(SWAPS_HEADER + MD0)
    p = live.run("--apply")
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert live.mutations() == [f"swapon {live.file} exists=True"], "the file is not recreated and not formatted again"
    assert f"{live.file}\tfile" in live.swaps()


def test_a_file_cut_off_between_fallocate_and_mkswap_is_completed(live):
    live.proc_swaps.write_text(SWAPS_HEADER + MD0)
    live.make_swapfile(header="", mode=0o644)
    p = live.run("--apply")
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert [m.split()[0] for m in live.mutations()] == ["mkswap", "swapon"]
    assert live.mutations()[0] == f"mkswap -L stopgap {live.file} mode=600"
    assert (live.file.stat().st_mode & 0o777) == 0o600


def test_a_stopgap_file_at_another_mode_gets_mode_600_and_nothing_else(live):
    live.proc_swaps.write_text(SWAPS_HEADER + MD0)
    live.file.chmod(0o644)
    p = live.run("--apply")
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert (live.file.stat().st_mode & 0o777) == 0o600
    assert [m.split()[0] for m in live.mutations()] == ["swapon"]


def test_creation_leaves_no_temporary_file_when_fallocate_fails(empty):
    empty.set("fail", "fallocate")
    p = empty.run("--apply")
    assert p.returncode != 0
    assert not empty.file.exists() and empty.leftovers() == []


# ───────────────────────────── what it refuses ─────────────────────────────


def refused(h: Host, *args: str, message: str) -> None:
    p = h.run(*args)
    assert p.returncode == 1 and message in p.stderr, (p.returncode, p.stdout, p.stderr)


@pytest.mark.parametrize("verb", ["check", "--apply", "--persist", "--remove"])
def test_every_verb_refuses_any_other_machine(live, verb):
    live.set("hostname", "infer-pg-primary")
    refused(live, verb, message="not debian-base-template")
    untouched(live)


@pytest.mark.parametrize("verb", ["check", "--apply", "--persist", "--remove"])
def test_every_verb_refuses_without_root(live, verb):
    live.set("uid", "1000")
    refused(live, verb, message="run as root")
    untouched(live)


def test_it_refuses_a_machine_that_is_not_a_proxmox_node(live):
    shutil.rmtree(live.root / "pve_nodes" / HOST)
    refused(live, "--apply", message="not a Proxmox node")
    untouched(live)


def test_it_refuses_when_a_tool_is_missing(live):
    live.extra = 'TOOLS="$TOOLS no-such-tool-for-the-test"'
    refused(live, "--apply", message="no-such-tool-for-the-test is not installed")
    untouched(live)


def test_creation_needs_the_file_plus_200_gb_free_and_exactly_enough_is_enough(empty):
    empty.set("avail", str(NEED - 1))
    refused(empty, "--apply", message="would leave less than")
    assert not empty.file.exists() and empty.mutations() == []
    empty.set("avail", str(SIZE))
    refused(empty, "--apply", message="would leave less than")
    empty.set("avail", str(NEED))
    assert empty.run("--apply").returncode == 0
    assert empty.file.exists()


def test_creation_refuses_a_filesystem_that_is_not_ext4(empty):
    for fstype in ("xfs", "btrfs", "zfs", "tmpfs"):
        empty.set("fstype", fstype)
        refused(empty, "--apply", message=f"is {fstype}, not ext4")
        assert empty.mutations() == [] and not empty.file.exists()


def test_creation_refuses_a_leftover_temporary_name(empty):
    (empty.root / "swapfile.new-20260101T000000Z").write_bytes(b"x")
    empty.extra = "date() { echo 20260101T000000Z; }"  # the same timestamp as the leftover
    refused(empty, "--apply", message="exists (a run that was cut off?)")
    assert empty.mutations() == []
    assert (empty.root / "swapfile.new-20260101T000000Z").read_bytes() == b"x", (
        "a leftover that is not ours is not removed by the cleanup"
    )


def test_a_file_that_is_not_ours_is_never_touched(live):
    live.proc_swaps.write_text(SWAPS_HEADER + MD0)
    cases = {
        "another size": dict(size=SIZE * 2),
        "another signature": dict(header="OTHERFS\n"),
        "another label": dict(label="other"),
    }
    for name, kw in cases.items():
        live.make_swapfile(**kw)
        before = live.file.read_bytes()
        p = live.run("--apply")
        assert p.returncode == 1 and "install-host.sh:" in p.stderr, (name, p.stdout, p.stderr)
        assert live.mutations() == [] and live.file.read_bytes() == before, name


def test_a_symlink_or_a_directory_at_the_path_is_refused(live, tmp_path):
    live.proc_swaps.write_text(SWAPS_HEADER + MD0)
    target = tmp_path / "elsewhere"
    target.write_bytes(b"x" * SIZE)
    live.file.unlink()
    live.file.symlink_to(target)
    refused(live, "--apply", message="not a regular file")
    assert live.mutations() == []
    live.file.unlink()
    live.file.mkdir()
    refused(live, "--apply", message="not a regular file")
    assert live.mutations() == []
    refused(live, "--remove", message="not a regular file")


def test_a_file_in_use_that_is_not_as_wanted_is_not_touched(live):
    live.file.chmod(0o644)
    refused(live, "--apply", message="is in use and is not as wanted")
    assert live.mutations() == [] and (live.file.stat().st_mode & 0o777) == 0o644


# ───────────────────────────── remove ─────────────────────────────


def test_remove_swapoffs_drops_the_line_and_deletes_the_file_and_leaves_md0_alone(live):
    live.persist_line()
    p = live.run("--remove")
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert live.mutations() == [f"swapoff {live.file}", "systemctl daemon-reload"], (
        "this one file only: never swapoff -a"
    )
    assert not live.file.exists()
    assert live.fstab_text() == FSTAB_LIVE and [b.read_text() for b in live.backups()] == [
        FSTAB_LIVE + f"{live.file} none swap sw,nofail 0 0\n"
    ]
    assert "/dev/md0" in live.swaps() and str(live.file) not in live.swaps()
    assert "4 GiB /dev/md0 swap is untouched" in p.stdout


def test_remove_without_a_persisted_line_does_not_touch_fstab(live):
    p = live.run("--remove")
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert live.mutations() == [f"swapoff {live.file}"]
    assert not live.file.exists() and live.fstab_text() == FSTAB_LIVE and live.backups() == []


def test_remove_twice_is_the_same_as_once(live):
    assert live.run("--remove").returncode == 0
    calls = live.calls()
    p = live.run("--remove")
    assert p.returncode == 0 and "already absent" in p.stdout and live.calls() == calls


def test_remove_after_a_reboot_needs_no_swapoff(live):
    live.proc_swaps.write_text(SWAPS_HEADER + MD0)
    p = live.run("--remove")
    assert p.returncode == 0 and live.mutations() == [] and not live.file.exists()


def test_remove_refuses_while_more_than_half_of_memavailable_is_swapped_out(live):
    live.set_available(8 * GiB)
    live.proc_swaps.write_text(SWAPS_HEADER + MD0)
    live.activate(used_kib=4 * 1024 * 1024 + 1)
    refused(live, "--remove", message="refusing: swapoff has to move")
    assert live.mutations() == [] and live.file.exists() and live.fstab_text() == FSTAB_LIVE


def test_remove_at_exactly_half_of_memavailable_is_allowed(live):
    live.proc_swaps.write_text(SWAPS_HEADER + MD0)
    live.activate(used_kib=4 * 1024 * 1024)
    assert live.run("--remove").returncode == 0
    assert not live.file.exists()


def test_a_failed_swapoff_leaves_the_line_and_the_file(live):
    live.persist_line()
    live.set("fail", "swapoff")
    refused(live, "--remove", message="swapoff")
    assert (
        live.file.exists()
        and live.fstab_text() == FSTAB_LIVE + f"{live.file} none swap sw,nofail 0 0\n"
        and live.backups() == []
    )
    assert str(live.file) in live.swaps()


@pytest.mark.parametrize("kw", [dict(label="other"), dict(header="OTHERFS\n"), dict(header="")])
def test_remove_never_deletes_a_file_that_is_not_the_stopgap(live, kw):
    live.proc_swaps.write_text(SWAPS_HEADER + MD0)
    live.make_swapfile(**kw)
    before = live.file.read_bytes()
    refused(live, "--remove", message="not ours")
    assert live.mutations() == [] and live.file.read_bytes() == before


def test_remove_cleans_a_fstab_line_whose_file_is_gone(empty):
    empty.persist_line()
    p = empty.run("--remove")
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert empty.fstab_text() == FSTAB_LIVE and empty.mutations() == ["systemctl daemon-reload"]


# ───────────────────────────── the mutation sweep ─────────────────────────────
# Each entry breaks one guard of the installer (the text is replaced exactly once; a replacement that no longer matches fails the test, so the sweep cannot go stale)
# and a scenario says whether the guard held. The scenario must hold on the real installer and fail on the mutant: otherwise the guard is not tested.


def mutant(tmp_path: Path, replacements: list[tuple[str, str]]) -> Path:
    text = SCRIPT.read_text()
    for old, new in replacements:
        assert text.count(old) == 1, f"the mutation anchor is not unique any more: {old!r} ({text.count(old)})"
        text = text.replace(old, new)
    path = tmp_path / "mutant.sh"
    path.write_text(text)
    return path


def sc_other_machine(h: Host) -> bool:
    h.set("hostname", "infer-pg-primary")
    p = h.run("--apply")
    return p.returncode == 1 and "not Debian-trixie" in p.stderr and h.mutations() == []


def sc_not_root(h: Host) -> bool:
    h.set("uid", "1000")
    p = h.run("--apply")
    return p.returncode == 1 and "run as root" in p.stderr and h.mutations() == []


def sc_not_a_node(h: Host) -> bool:
    shutil.rmtree(h.root / "pve_nodes" / HOST)
    p = h.run("--apply")
    return p.returncode == 1 and "not a Proxmox node" in p.stderr and h.mutations() == []


def sc_xfs(h: Host) -> bool:
    h.file.unlink()
    h.proc_swaps.write_text(SWAPS_HEADER + MD0)
    h.set("fstype", "xfs")
    p = h.run("--apply")
    return p.returncode == 1 and h.mutations() == []


def sc_not_enough_space(h: Host) -> bool:
    h.file.unlink()
    h.proc_swaps.write_text(SWAPS_HEADER + MD0)
    h.set("avail", str(NEED - 1))
    p = h.run("--apply")
    return p.returncode == 1 and h.mutations() == [] and not h.file.exists()


def sc_exactly_enough_space(h: Host) -> bool:
    h.file.unlink()
    h.proc_swaps.write_text(SWAPS_HEADER + MD0)
    h.set("avail", str(NEED))
    return h.run("--apply").returncode == 0 and h.file.exists()


def sc_space_for_the_file_only(h: Host) -> bool:
    h.file.unlink()
    h.proc_swaps.write_text(SWAPS_HEADER + MD0)
    h.set("avail", str(SIZE + 1))
    p = h.run("--apply")
    return p.returncode == 1 and h.mutations() == []


def sc_wrong_size(h: Host) -> bool:
    h.proc_swaps.write_text(SWAPS_HEADER + MD0)
    h.make_swapfile(size=SIZE * 2, header="")
    p = h.run("--apply")
    return p.returncode == 1 and "not ours to resize" in p.stderr and h.mutations() == []


def sc_other_signature(h: Host) -> bool:
    h.proc_swaps.write_text(SWAPS_HEADER + MD0)
    h.make_swapfile(header="OTHERFS\n")
    p = h.run("--apply")
    return p.returncode == 1 and "not ours; nothing was changed" in p.stderr and h.mutations() == []


def sc_symlink(h: Host) -> bool:
    h.proc_swaps.write_text(SWAPS_HEADER + MD0)
    target = h.root / "elsewhere"
    target.write_bytes(b"x" * SIZE)
    h.file.unlink()
    h.file.symlink_to(target)
    p = h.run("--apply")
    return p.returncode == 1 and "not a regular file: not touching it" in p.stderr and h.mutations() == []


def sc_in_use_and_wrong(h: Host) -> bool:
    h.file.chmod(0o644)
    p = h.run("--apply")
    return p.returncode == 1 and "is in use" in p.stderr and (h.file.stat().st_mode & 0o777) == 0o644


def sc_leftover(h: Host) -> bool:
    h.file.unlink()
    h.proc_swaps.write_text(SWAPS_HEADER + MD0)
    (h.root / "swapfile.new-20260101T000000Z").write_bytes(b"x")
    h.extra = "date() { echo 20260101T000000Z; }"
    p = h.run("--apply")
    return p.returncode == 1 and h.mutations() == [] and (h.root / "swapfile.new-20260101T000000Z").exists()


def sc_mode_at_formatting(h: Host) -> bool:
    h.file.unlink()
    h.proc_swaps.write_text(SWAPS_HEADER + MD0)
    p = h.run("--apply")
    return p.returncode == 0 and any(m.startswith("mkswap") and m.endswith("mode=600") for m in h.mutations())


def sc_remove_not_ours(h: Host) -> bool:
    h.proc_swaps.write_text(SWAPS_HEADER + MD0)
    h.make_swapfile(label="other")
    p = h.run("--remove")
    return p.returncode == 1 and h.file.exists() and h.mutations() == []


def sc_remove_too_much_swapped(h: Host) -> bool:
    h.proc_swaps.write_text(SWAPS_HEADER + MD0)
    h.activate(used_kib=5 * 1024 * 1024)
    p = h.run("--remove")
    return p.returncode == 1 and h.mutations() == [] and h.file.exists()


def sc_swapoff_fails(h: Host) -> bool:
    h.persist_line()
    h.set("fail", "swapoff")
    p = h.run("--remove")
    return p.returncode == 1 and h.file.exists() and str(h.file) in h.fstab_text()


def sc_candidate_wrong(h: Host) -> bool:
    h.set("findmnt_candidate_wrong", "bogus")
    p = h.run("--persist")
    return p.returncode == 1 and h.fstab_text() == FSTAB_LIVE and h.backups() == []


def sc_readback_wrong_restores(h: Host) -> bool:
    h.set("findmnt_readback_wrong", "bogus")
    p = h.run("--persist")
    return p.returncode == 1 and h.fstab_text() == FSTAB_LIVE


def sc_backup_first(h: Host) -> bool:
    p = h.run("--persist")
    return p.returncode == 0 and [b.read_text() for b in h.backups()] == [FSTAB_LIVE]


def sc_idempotent_persist(h: Host) -> bool:
    h.persist_line()
    p = h.run("--persist")
    return p.returncode == 0 and h.backups() == [] and h.mutations() == []


def sc_apply_leaves_fstab(h: Host) -> bool:
    h.file.unlink()
    h.proc_swaps.write_text(SWAPS_HEADER + MD0)
    p = h.run("--apply")
    return p.returncode == 0 and h.fstab_text() == FSTAB_LIVE and h.backups() == []


MUTATIONS = {
    "host name guard": (
        [('[ "$host" = "$HOST_WANTED" ] || die "this is', '[ "$host" = "$HOST_WANTED" ] || echo "this is')],
        sc_other_machine,
    ),
    "root guard": (
        [('[ "$(id -u)" = 0 ] || die "run as root"', '[ "$(id -u)" = 0 ] || echo "run as root"')],
        sc_not_root,
    ),
    "proxmox node guard": ([('[ -d "$PVE_NODES/$host" ] || die', '[ -d "$PVE_NODES/$host" ] || echo')], sc_not_a_node),
    "ext4 guard": ([('[ "$fstype" = "$FSTYPE_WANTED" ] || die', '[ "$fstype" = "$FSTYPE_WANTED" ] || echo')], sc_xfs),
    "free space guard": ([('[ "$free" -ge "$need" ] || die', '[ "$free" -ge "$need" ] || echo')], sc_not_enough_space),
    "free space guard, off by one": ([('[ "$free" -ge "$need" ]', '[ "$free" -gt "$need" ]')], sc_exactly_enough_space),
    "free space guard counts the file": (
        [("need=$((SIZE_BYTES + MIN_FREE_BYTES))", "need=$((MIN_FREE_BYTES))")],
        sc_space_for_the_file_only,
    ),
    "size guard of a file that is there": (
        [('[ "$F_SIZE" = "$SIZE_BYTES" ] || die "$SWAPFILE is', '[ "$F_SIZE" = "$SIZE_BYTES" ] || echo "$SWAPFILE is')],
        sc_wrong_size,
    ),
    "signature guard of a file that is there": (
        [('  else\n    die "$SWAPFILE has type', '  else\n    echo "$SWAPFILE has type')],
        sc_other_signature,
    ),
    "regular file guard": (
        [
            (
                '[ ! -L "$SWAPFILE" ] || die "$SWAPFILE is not a regular file: not touching it"',
                '[ ! -L "$SWAPFILE" ] || echo "$SWAPFILE is not a regular file: not touching it"',
            )
        ],
        sc_symlink,
    ),
    "in-use guard": (
        [('[ "$ACTIVE" = 0 ] || die "$SWAPFILE is in use', '[ "$ACTIVE" = 0 ] || echo "$SWAPFILE is in use')],
        sc_in_use_and_wrong,
    ),
    "leftover temporary name": ([('  [ ! -e "$cand" ] || die', '  [ ! -e "$cand" ] || echo')], sc_leftover),
    "mode 600 before formatting": (
        [("(umask 077 && fallocate", "(fallocate"), ('  chmod 600 "$tmp"\n', '  true "$tmp"\n')],
        sc_mode_at_formatting,
    ),
    "remove: not ours": (
        [
            (
                '[ "$F_LABEL" = "$LABEL" ] || die "$SWAPFILE has type',
                '[ "$F_LABEL" = "$LABEL" ] || echo "$SWAPFILE has type',
            )
        ],
        sc_remove_not_ours,
    ),
    "remove: half of MemAvailable": (
        [('[ $((used * 2)) -le "$avail" ] || die', '[ $((used * 2)) -le "$avail" ] || echo')],
        sc_remove_too_much_swapped,
    ),
    "remove: swapoff must succeed first": (
        [('swapoff "$SWAPFILE" || die', 'swapoff "$SWAPFILE" || echo')],
        sc_swapoff_fails,
    ),
    "fstab candidate is read back first": (
        [('[ "$opts" = "$want" ] || die "the candidate', '[ "$opts" = "$want" ] || echo "the candidate')],
        sc_candidate_wrong,
    ),
    "fstab result is read back and the backup restored": (
        [('    cp -p "$FSTAB.bak-swap-$TS" "$FSTAB"\n', '    true "$FSTAB.bak-swap-$TS" "$FSTAB"\n')],
        sc_readback_wrong_restores,
    ),
    "fstab backup before the change": (
        [('  cp -p "$FSTAB" "$FSTAB.bak-swap-$TS"\n', '  true "$FSTAB" "$FSTAB.bak-swap-$TS"\n')],
        sc_backup_first,
    ),
    "fstab untouched when the line is there": (
        [('  if cmp -s "$FSTAB" "$new"; then', "  if false; then")],
        sc_idempotent_persist,
    ),
    "--apply does not persist": ([("--apply) cmd_apply ;;", "--apply) cmd_persist ;;")], sc_apply_leaves_fstab),
}


@pytest.mark.parametrize("name", MUTATIONS)
def test_each_guard_is_tested_the_installer_passes_its_scenario_and_the_mutant_does_not(name, tmp_path):
    replacements, scenario = MUTATIONS[name]
    assert scenario(Host(tmp_path / "real")), f"the real installer fails the scenario of '{name}'"
    assert not scenario(Host(tmp_path / "mutant", mutant(tmp_path, replacements))), (
        f"no test notices when '{name}' is broken"
    )
