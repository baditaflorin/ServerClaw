"""Step 3d of docker-build-gc.sh on the 0mcp build VM (VM 130): fleet-job-caches-trim.sh and go-fleet-job's own program, vendored as fleet-job-caches.sh.

Everything runs against a fake docker and temporary directories that stand in for the volumes: no real docker, no real volume, and never the real
docker-build-gc.sh (it deletes under /var/tmp and /tmp). The tests that run the vendored program itself need GNU find in the program's worker; they are
skipped where it is missing (macOS) and run on the Linux build host.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import time
from pathlib import Path

import pytest

DIR = Path(__file__).resolve().parents[1] / "config" / "0mcp" / "docker-build-lv3"
BIN = DIR / "files" / "usr" / "local" / "bin"
PROGRAM = BIN / "fleet-job-caches.sh"
WRAPPER = BIN / "fleet-job-caches-trim.sh"
GC = BIN / "docker-build-gc.sh"
README = DIR / "README.md"
HOUR = 3600
MIB = 1 << 20
GIB = 1 << 30
GO_README = "This directory holds cached build artifacts from the Go build system.\n"


def _gnu_find() -> bool:
    r = subprocess.run(["find", ".", "-maxdepth", "0", "-printf", "", "-newermt", "@0"], capture_output=True)
    return r.returncode == 0


needs_gnu_find = pytest.mark.skipif(
    not _gnu_find(), reason="the program's worker needs GNU find (-printf, -newermt): run on the Linux build host"
)

# docker as the program uses it: volumes are directories of $FAKE_ROOT, $FAKE_BUSY lists the volumes with a running container and $FAKE_STOPPED the ones with
# only a stopped one; `docker run` runs the worker script that the program hands it, locally, on the directory of the mounted volume. The images on the host are
# the lines of $FAKE_IMAGES (`docker pull` adds one, $FAKE_PULL_FAIL makes it fail, $FAKE_INSPECT_RC is the status of `docker image inspect`).
FAKE_DOCKER = r"""#!/bin/sh
printf '%s\n' "$*" >> "${FAKE_LOG:?}"
case "$1" in
volume)
  case "$2" in
  ls) ls -1 "${FAKE_ROOT:?}"; exit 0 ;;
  inspect)
    if [ -d "${FAKE_ROOT:?}/$3" ]; then echo '[]'; exit 0; fi
    echo "Error response from daemon: get $3: no such volume" >&2; exit 1 ;;
  rm)
    case $3 in '' | */* | . | ..) exit 1 ;; esac
    rm -rf "${FAKE_ROOT:?}/$3"; exit 0 ;;
  esac ;;
ps)
  vol=; st=0
  for a in "$@"; do case $a in volume=*) vol=${a#volume=} ;; status=*) st=1 ;; esac; done
  if [ "$st" = 1 ]; then
    case " $FAKE_BUSY " in *" $vol "*) echo cafe0001 ;; esac
  else
    case " $FAKE_BUSY $FAKE_STOPPED " in *" $vol "*) echo cafe0001 ;; esac
  fi
  exit 0 ;;
image)
  [ "$2" = inspect ] || exit 1
  [ -z "${FAKE_INSPECT_RC:-}" ] || exit "$FAKE_INSPECT_RC"
  if grep -qxF "$3" "${FAKE_IMAGES:?}" 2>/dev/null; then exit 0; fi
  echo "Error response from daemon: No such image: $3" >&2; exit 1 ;;
pull)
  [ -z "${FAKE_PULL_FAIL:-}" ] || { echo "Error response from daemon: pull access denied for $3" >&2; exit 1; }
  shift
  [ "$1" = -q ] && shift
  printf '%s\n' "$1" >> "${FAKE_IMAGES:?}"
  echo "sha256:0123456789abcdef"; exit 0 ;;
info)
  printf '%s\n' "${FAKE_ROOT:?}"; exit 0 ;;
run)
  shift
  vol=
  while [ $# -gt 0 ]; do
    case $1 in
    --rm) shift ;;
    --pull | --network | --user | --cpus | --memory | --pids-limit | --label | --entrypoint) shift 2 ;;
    -v) vol=${2%%:*}; suffix=${2#*:/v}; shift 2 ;;
    *) break ;;
    esac
  done
  shift # the image
  shift # -c
  worker=$1; shift
  shift # worker ($0 of the script)
  shift # /v
  printf 'mount %s%s\n' "$vol" "$suffix" >> "$FAKE_LOG"
  exec sh -c "$worker" worker "${FAKE_ROOT:?}/$vol" "$@" ;;
esac
echo "fake docker: not simulated: $*" >&2
exit 125
"""

# what a program that is not under test prints: the report of go-fleet-job's fleet-job-caches/1, here with nothing in it
EMPTY_REPORT = """fleet-job-caches/1
mode=prune
max_age=2592000
max_bytes=21474836480
min_keep=3600
busy_keep=43200
host_time=1
--summary--
volumes=0
docker=ok
"""

FAKE_PROGRAM = """#!/bin/sh
printf '%s\\n' "$@" > "$FAKE_ARGS"
cat "$FAKE_REPORT"
exit "${FAKE_STATUS:-0}"
"""


class World:
    """A fake docker on the PATH, an empty volumes directory, and a place for the calls docker gets."""

    def __init__(self, tmp_path: Path):
        self.tmp = tmp_path
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        self.root = tmp_path / "volumes"
        self.root.mkdir()
        self.log = tmp_path / "docker.log"
        (self.bin / "docker").write_text(FAKE_DOCKER)
        (self.bin / "docker").chmod(0o755)
        self.args_file = tmp_path / "program.args"
        self.report_file = tmp_path / "report.txt"
        self.report_file.write_text(EMPTY_REPORT)
        self.fake_program = tmp_path / "fake-program.sh"
        self.fake_program.write_text(FAKE_PROGRAM)
        self.fake_program.chmod(0o755)
        self.images_file = tmp_path / "images.txt"
        self.images_file.write_text("golang:1.27\ngolang:1.26\n")
        self.prom_dir = (
            tmp_path / "prom"
        )  # not there until a test makes it: the real node_exporter directory is never touched

    def run(self, env: dict | None = None, program: Path | None = None, status: int = 0):
        e = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("CACHE_TRIM_") and k not in ("DRY_RUN", "FLEET_JOB_CACHES_SH")
        }
        e.update(
            PATH=f"{self.bin}:{os.environ['PATH']}",
            FAKE_ROOT=str(self.root),
            FAKE_LOG=str(self.log),
            FAKE_BUSY="",
            FAKE_STOPPED="",
            FAKE_IMAGES=str(self.images_file),
            FAKE_PULL_FAIL="",
            FAKE_INSPECT_RC="",
            CACHE_TRIM_PROM_DIR=str(self.prom_dir),
            FAKE_ARGS=str(self.args_file),
            FAKE_REPORT=str(self.report_file),
            FAKE_STATUS=str(status),
            FLEET_JOB_CACHES_SH=str(program or self.fake_program),
        )
        e.update(env or {})
        return subprocess.run(["bash", str(WRAPPER)], capture_output=True, text=True, env=e, timeout=180)

    def report(self, text: str) -> None:
        self.report_file.write_text(text)

    def program_args(self) -> list[str] | None:
        return self.args_file.read_text().split("\n")[:-1] if self.args_file.exists() else None

    def calls(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def removed(self) -> list[str]:
        return [c.split()[-1] for c in self.calls() if c.startswith("volume rm ")]

    def mounts(self) -> list[str]:
        return [c[len("mount ") :] for c in self.calls() if c.startswith("mount ")]

    def volume(self, name: str, readme: str | None = GO_README) -> Path:
        v = self.root / name
        v.mkdir(parents=True, exist_ok=True)
        if readme is not None:
            (v / "README").write_text(readme)
        return v

    def set_images(self, *names: str) -> None:
        self.images_file.write_text("".join(f"{n}\n" for n in names))

    def images(self) -> list[str]:
        return self.images_file.read_text().split()

    def pulls(self) -> list[str]:
        return [c for c in self.calls() if c.startswith("pull ")]


def entry(vol: Path, n: int, age_hours: float, mib: int = 400) -> Path:
    """One cache file of mib MiB (sparse: the size find reports, no disk used) that was last used age_hours ago."""
    d = vol / f"{n % 16:02x}"
    d.mkdir(exist_ok=True)
    f = d / f"{n:04x}-a"
    with open(f, "wb") as fh:
        fh.truncate(mib * MIB)
    t = time.time() - age_hours * HOUR
    os.utime(f, (t, t))
    return f


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


# ---- the wrapper, with a program that only records what it was asked -------------------------------------------------------------------------------


def test_by_default_it_asks_for_a_prune_with_a_20_gib_cap_a_12_hour_floor_and_30_days_before_a_whole_volume(world):
    r = world.run()
    assert r.returncode == 0, r.stdout + r.stderr
    # MODE MAX_AGE MAX_BYTES MIN_KEEP IMAGE NAME BUSY_KEEP, the order of go-fleet-job's caches.sh
    assert world.program_args() == ["prune", str(30 * 86400), str(20 * GIB), "3600", "golang:1.27", "", str(12 * 3600)]
    assert (
        "0 volumes" in r.stdout
        and "cap 20 GiB, 12 h floor while in use, whole volumes only after 30 d idle" in r.stdout
    )
    assert world.removed() == []


def test_a_dry_run_asks_for_a_plan_and_says_so(world):
    r = world.run({"DRY_RUN": "1"})
    assert r.returncode == 0, r.stdout
    assert world.program_args()[0] == "plan"
    assert "DRY RUN" in r.stdout


def test_every_setting_can_be_changed_and_one_volume_can_be_named(world):
    env = {
        "CACHE_TRIM_MAX_GIB": "7",
        "CACHE_TRIM_BUSY_HOURS": "6",
        "CACHE_TRIM_UNUSED_DAYS": "9",
        "CACHE_TRIM_VOLUME": "gucapi-gocache",
        "CACHE_TRIM_IMAGE": "golang:1.26",
    }
    r = world.run(env)
    assert r.returncode == 0, r.stdout
    assert world.program_args() == [
        "prune",
        str(9 * 86400),
        str(7 * GIB),
        "3600",
        "golang:1.26",
        "gucapi-gocache",
        str(6 * 3600),
    ]


@pytest.mark.parametrize(
    "setting",
    [
        {"CACHE_TRIM_MAX_GIB": "0"},
        {"CACHE_TRIM_MAX_GIB": "abc"},
        {"CACHE_TRIM_MAX_GIB": "1.5"},
        {"CACHE_TRIM_MAX_GIB": "-3"},
        {"CACHE_TRIM_MAX_GIB": "07"},
        {"CACHE_TRIM_BUSY_HOURS": "5"},
        {"CACHE_TRIM_BUSY_HOURS": "0"},
        {"CACHE_TRIM_BUSY_HOURS": "twelve"},
        {"CACHE_TRIM_UNUSED_DAYS": "3"},
        {"CACHE_TRIM_UNUSED_DAYS": "0"},
        {"CACHE_TRIM_UNUSED_DAYS": "thirty"},
        {"DRY_RUN": "yes"},
        {"DRY_RUN": "true"},
        {"DRY_RUN": "2"},
        {"CACHE_TRIM_VOLUME": "a/b"},
        {"CACHE_TRIM_VOLUME": "-x"},
        {"CACHE_TRIM_VOLUME": "a b"},
        {"CACHE_TRIM_VOLUME": ".hidden"},
        {"CACHE_TRIM_IMAGE": "-x"},
        {"CACHE_TRIM_IMAGE": "golang:1.27 -x"},
        {"CACHE_TRIM_IMAGE": "golang:1.27 img;true"},
        {"CACHE_TRIM_IMAGE": "img;true"},
        {"CACHE_TRIM_IMAGE": "   "},
        {"CACHE_TRIM_IMAGE": "a b c d e f g"},
        {"CACHE_TRIM_PULL": "yes"},
        {"CACHE_TRIM_PULL": "2"},
        {"CACHE_TRIM_MIN_FREE_GIB": "abc"},
        {"CACHE_TRIM_MIN_FREE_GIB": "-1"},
    ],
)
def test_a_wrong_setting_is_refused_before_anything_runs(world, setting):
    """A typo must never turn a dry run into a live one, a floor below what a build can hold, or the step into a remover of whole volumes."""
    r = world.run(setting)
    assert r.returncode == 2, (setting, r.stdout)
    assert "fleet-job-caches-trim:" in r.stdout
    assert world.program_args() is None and world.calls() == [], "nothing may run before the settings are accepted"


def test_the_busy_floor_and_the_unused_days_have_the_smallest_values_the_design_allows(world):
    ok = world.run({"CACHE_TRIM_BUSY_HOURS": "6", "CACHE_TRIM_UNUSED_DAYS": "4", "CACHE_TRIM_MAX_GIB": "1"})
    assert ok.returncode == 0, ok.stdout
    assert world.program_args()[2] == str(1 * GIB)


def test_without_the_program_it_is_skipped_loudly_and_asks_docker_nothing(world):
    r = world.run(program=world.tmp / "not-there.sh")
    assert r.returncode == 3 and "WARNING: SKIPPED" in r.stdout and "not installed" in r.stdout
    assert world.calls() == []
    plain = world.tmp / "plain.sh"
    plain.write_text(FAKE_PROGRAM)
    plain.chmod(0o644)
    r = world.run(program=plain)
    assert r.returncode == 3 and "WARNING: SKIPPED" in r.stdout and world.program_args() is None


def test_the_first_listed_image_that_is_on_the_host_is_the_one_used(world):
    world.run()
    assert world.program_args()[4] == "golang:1.27" and world.pulls() == []
    world.set_images("golang:1.26")
    r = world.run()
    assert r.returncode == 0, r.stdout
    assert world.program_args()[4] == "golang:1.26" and world.pulls() == [], (
        "golang:1.27 is gone: the next one in the list is used"
    )
    world.set_images("golang:1.26", "golang:1.28")
    world.run({"CACHE_TRIM_IMAGE": "golang:1.28 golang:1.26"})
    assert world.program_args()[4] == "golang:1.28", "the order of the list decides, not the order on the host"


def test_when_no_listed_image_is_on_the_host_the_first_is_pulled_and_used_and_the_next_run_finds_it(world):
    world.set_images()
    r = world.run({"CACHE_TRIM_MIN_FREE_GIB": "1"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert world.pulls() == ["pull -q golang:1.27"], world.calls()
    assert world.program_args()[4] == "golang:1.27"
    assert "NOTICE: none of golang:1.27 golang:1.26 was on this host: pulled golang:1.27" in r.stdout
    again = world.run({"CACHE_TRIM_MIN_FREE_GIB": "1"})
    assert again.returncode == 0 and world.pulls() == ["pull -q golang:1.27"], (
        "the second run finds the image and does not pull"
    )


def test_a_dry_run_never_pulls_and_says_what_a_live_run_would_do(world):
    world.set_images()
    r = world.run({"DRY_RUN": "1", "CACHE_TRIM_MIN_FREE_GIB": "1"})
    assert r.returncode == 3 and "WARNING: SKIPPED" in r.stdout and "a live run would pull golang:1.27" in r.stdout
    assert world.pulls() == [] and world.program_args() is None and world.images() == []


def test_with_the_pull_turned_off_a_missing_image_is_a_loud_skip(world):
    world.set_images()
    r = world.run({"CACHE_TRIM_PULL": "0"})
    assert r.returncode == 3 and "WARNING: SKIPPED" in r.stdout and "CACHE_TRIM_PULL=0" in r.stdout
    assert world.pulls() == [] and world.program_args() is None


def test_a_pull_that_fails_is_a_loud_skip_and_nothing_runs(world):
    world.set_images()
    r = world.run({"FAKE_PULL_FAIL": "1", "CACHE_TRIM_MIN_FREE_GIB": "1"})
    assert r.returncode == 3 and "WARNING: SKIPPED" in r.stdout
    assert (
        "pulling golang:1.27 failed (status 1: Error response from daemon: pull access denied for golang:1.27)"
        in r.stdout
    )
    assert world.program_args() is None


def test_a_pull_needs_room_where_docker_keeps_its_images(world):
    """The GC exists because the disk fills: a pull of a gigabyte is not made when there is no room for it."""
    world.set_images()
    r = world.run({"CACHE_TRIM_MIN_FREE_GIB": "999999"})
    assert r.returncode == 3 and "WARNING: SKIPPED" in r.stdout and "under CACHE_TRIM_MIN_FREE_GIB=999999" in r.stdout
    assert world.pulls() == [] and world.program_args() is None
    off = world.run({"CACHE_TRIM_MIN_FREE_GIB": "0"})
    assert off.returncode == 0 and world.pulls() == ["pull -q golang:1.27"], "0 turns the check off"


def test_a_docker_that_does_not_answer_is_a_loud_skip_and_not_a_pull(world):
    r = world.run({"FAKE_INSPECT_RC": "124"})
    assert r.returncode == 3 and "WARNING: SKIPPED: docker did not answer within 60 s" in r.stdout
    assert world.pulls() == [] and world.program_args() is None


def test_a_program_that_fails_or_gives_no_complete_report_is_reported_as_failed(world):
    r = world.run(status=3)
    assert r.returncode == 1 and "WARNING: FAILED" in r.stdout and "status 3" in r.stdout
    world.report("this is not a report\nvolume=oops\n")
    r = world.run()
    assert r.returncode == 1 and "WARNING: FAILED" in r.stdout
    world.report(EMPTY_REPORT.replace("--summary--\nvolumes=0\ndocker=ok\n", ""))
    r = world.run()
    assert r.returncode == 1 and "WARNING: FAILED" in r.stdout and "complete" in r.stdout


BUSY_VOLUME = """volume=fleet-job-cache-hot-gocache
state=busy
containers=2
kind=go-build
roots=.
files=1000
bytes=30064771072
last_write=1
cache_files=900
cache_bytes=28000000000
trim_files=300
trim_bytes=10737418240
cut_age=43200
cap_unmet=yes
removed_files=300
removed_bytes=10737418240
result=trimmed
"""
IDLE_VOLUME = """volume=fleet-job-cache-npm
state=idle
containers=0
kind=other
files=3
bytes=1048576
last_write=1
result=nothing
"""
FAILED_VOLUME = """volume=fleet-job-cache-broken
state=idle
containers=0
kind=unknown
error=docker could not remove the volume: boom
result=failed
"""
SKIPPED_VOLUME = """volume=fleet-job-cache-gomod
state=busy
containers=1
kind=other
bytes=2097152
result=skipped
"""


def report(*blocks: str, docker: str = "ok", volumes: int | None = None, mode: str = "prune") -> str:
    head = EMPTY_REPORT.split("--summary--")[0].replace("mode=prune", f"mode={mode}")
    n = len(blocks) if volumes is None else volumes
    return head + "".join(blocks) + f"--summary--\nvolumes={n}\ndocker={docker}\n"


def test_it_prints_a_line_for_each_volume_that_changed_failed_or_is_still_over_the_cap_and_one_line_of_totals(world):
    world.report(report(BUSY_VOLUME, IDLE_VOLUME, FAILED_VOLUME, SKIPPED_VOLUME))
    r = world.run()
    lines = r.stdout.splitlines()
    assert (
        "fleet-job-caches-trim: hot-gocache state=busy kind=go-build size=28672MiB result=trimmed freed=10240MiB files=300 cap_unmet=yes"
        in lines
    )
    assert (
        "fleet-job-caches-trim: WARNING: broken state=idle kind=unknown size=0MiB result=failed error=docker could not remove the volume: boom"
        in lines
    )
    assert not any(" npm " in line or "gomod" in line for line in lines), "volumes with nothing done are not listed"
    assert lines[-1] == (
        "fleet-job-caches-trim: 4 volumes: trimmed 1, removed 0 (10240 MiB freed), left alone 1, nothing to take 1, failed 1"
        " (cap 20 GiB, 12 h floor while in use, whole volumes only after 30 d idle)"
    )
    assert r.returncode == 1, "a failed volume makes the status 1 (docker-build-gc.sh ignores it)"


def test_a_dry_run_lists_every_volume_with_what_it_would_do(world):
    plan_trim = BUSY_VOLUME.replace("removed_files=300\nremoved_bytes=10737418240\nresult=trimmed\n", "action=trim\n")
    plan_keep = IDLE_VOLUME.replace("result=nothing\n", "action=keep\n")
    plan_skip = SKIPPED_VOLUME.replace("result=skipped\n", "action=skip\n")
    plan_remove = "volume=fleet-job-cache-ancient\nstate=idle\ncontainers=0\nkind=go-build\nbytes=104857600\nlast_write=1\naction=remove\n"
    world.report(report(plan_trim, plan_keep, plan_skip, plan_remove, mode="plan"))
    r = world.run({"DRY_RUN": "1"})
    out = r.stdout
    assert r.returncode == 0, out
    assert (
        "hot-gocache state=busy kind=go-build size=28672MiB action=trim would_free=10240MiB files=300 files_older_than=12h cap_unmet=yes"
        in out
    )
    assert "npm state=idle kind=other size=1MiB action=keep" in out
    assert "gomod state=busy kind=other size=2MiB action=skip" in out
    assert "ancient state=idle kind=go-build size=100MiB action=remove would_free=100MiB" in out
    assert "DRY RUN, nothing was changed: 4 volumes, would trim 1 and remove 1 (10340 MiB), 1 left alone" in out


def test_a_docker_that_did_not_answer_is_said_loudly_and_a_report_with_missing_blocks_is_refused(world):
    world.report(report(IDLE_VOLUME, docker="down"))
    r = world.run()
    assert r.returncode == 1 and "WARNING: docker did not answer (docker=down)" in r.stdout
    world.report(report(IDLE_VOLUME, volumes=2))
    r = world.run()
    assert r.returncode == 1 and "WARNING: the report is incomplete: 1 volume blocks for volumes=2" in r.stdout


# ---- the textfile metric ---------------------------------------------------------------------------------------------------------------------


def prom(world: World) -> Path:
    world.prom_dir.mkdir(exist_ok=True)
    return world.prom_dir / "fleet_job_caches_trim.prom"


def metric(path: Path, name: str) -> float:
    for line in path.read_text().splitlines():
        if line.startswith(name + " "):
            return float(line.split()[1])
    raise AssertionError(f"{name} is not in {path}")


def test_a_full_live_run_writes_the_textfile_metric_like_the_other_maintenance_jobs(world):
    f = prom(world)
    world.report(report(BUSY_VOLUME, IDLE_VOLUME))
    before = time.time()
    r = world.run()
    assert r.returncode == 0, r.stdout
    assert metric(f, "fleet_job_caches_trim_last_result") == 0
    assert metric(f, "fleet_job_caches_trim_freed_bytes") == 10737418240
    assert metric(f, "fleet_job_caches_trim_volumes_over_cap") == 1
    assert before - 2 <= metric(f, "fleet_job_caches_trim_last_run_timestamp_seconds") <= time.time() + 2
    text = f.read_text()
    assert text.count("# HELP ") == 4 and text.count("# TYPE ") == 4 and text.count(" gauge") == 4
    assert oct(f.stat().st_mode & 0o777) == "0o644"
    assert [p.name for p in world.prom_dir.iterdir()] == ["fleet_job_caches_trim.prom"], (
        "no temporary file is left behind"
    )


def test_a_skipped_or_failed_run_is_in_the_metric_too(world):
    f = prom(world)
    skipped = world.run(program=world.tmp / "not-there.sh")
    assert skipped.returncode == 3
    assert metric(f, "fleet_job_caches_trim_last_result") == 2 and metric(f, "fleet_job_caches_trim_freed_bytes") == 0
    world.report(report(BUSY_VOLUME, FAILED_VOLUME))
    failed = world.run()
    assert failed.returncode == 1
    assert (
        metric(f, "fleet_job_caches_trim_last_result") == 1
        and metric(f, "fleet_job_caches_trim_freed_bytes") == 10737418240
    )
    world.report(EMPTY_REPORT)
    assert world.run().returncode == 0
    assert metric(f, "fleet_job_caches_trim_last_result") == 0


def test_a_dry_run_or_one_volume_never_overwrites_the_report_of_the_full_run(world):
    f = prom(world)
    world.report(report(IDLE_VOLUME))
    assert world.run().returncode == 0
    stamp = f.read_text()
    world.report(report(BUSY_VOLUME))
    assert world.run({"DRY_RUN": "1"}).returncode == 0
    assert world.run({"CACHE_TRIM_VOLUME": "hot-gocache"}).returncode == 0
    assert f.read_text() == stamp


def test_a_metric_directory_that_is_not_there_is_no_error(world):
    world.report(report(IDLE_VOLUME))
    r = world.run({"CACHE_TRIM_PROM_DIR": str(world.tmp / "no" / "such" / "dir")})
    assert r.returncode == 0 and not (world.tmp / "no").exists()


# ---- the wrapper with go-fleet-job's real program, on directories that stand in for the volumes ---------------------------------------------------


def go_cache(world: World, name: str, ages_hours, mib: int = 400) -> list[Path]:
    v = world.volume(name)
    return [entry(v, i, age, mib) for i, age in enumerate(ages_hours)]


@needs_gnu_find
def test_a_go_build_cache_over_the_cap_loses_its_oldest_files_down_to_the_cap_and_nothing_else_is_touched(world):
    files = go_cache(
        world, "fleet-job-cache-a-gocache", [50, 40, 30, 20, 10, 5, 2]
    )  # 7 x 400 MiB against a cap of 1 GiB
    npm = world.volume("fleet-job-cache-npm", readme="npm cache\n")
    old_npm = entry(
        npm, 0, 24 * 20, 50
    )  # not a Go build cache: counted, never touched (20 days old: under the 30 days of the backstop)
    outside = go_cache(
        world, "gucapi-gocache", [90, 80, 70, 60, 50]
    )  # a Go cache over the cap, but not called fleet-job-cache-*
    lookalike = go_cache(world, "claude-gocache", [90, 80])
    r = world.run({"CACHE_TRIM_MAX_GIB": "1"}, program=PROGRAM)
    assert r.returncode == 0, r.stdout + r.stderr
    assert [f.exists() for f in files] == [False, False, False, False, False, True, True], (
        "the five oldest go, the two youngest stay"
    )
    assert (world.root / "fleet-job-cache-a-gocache" / "README").read_text() == GO_README
    assert all(f.exists() for f in outside + lookalike) and old_npm.exists(), (
        "only fleet-job-cache-* volumes, only Go build caches"
    )
    assert all(m.startswith("fleet-job-cache-") for m in world.mounts()), world.mounts()
    assert world.removed() == []
    assert "a-gocache state=idle kind=go-build" in r.stdout and "result=trimmed freed=2000MiB files=5" in r.stdout
    assert "2 volumes: trimmed 1, removed 0 (2000 MiB freed)" in r.stdout


@needs_gnu_find
def test_while_a_job_uses_the_volume_nothing_used_within_12_hours_goes_even_when_the_cap_is_not_met(world):
    files = go_cache(world, "fleet-job-cache-hot-gocache", [60, 30, 14, 8, 3, 1.5])  # 2400 MiB against a cap of 1 GiB
    r = world.run({"CACHE_TRIM_MAX_GIB": "1", "FAKE_BUSY": "fleet-job-cache-hot-gocache"}, program=PROGRAM)
    assert r.returncode == 0, r.stdout + r.stderr
    assert [f.exists() for f in files] == [False, False, False, True, True, True], (
        "only what was not used for 12 hours or more"
    )
    assert (
        "hot-gocache state=busy kind=go-build" in r.stdout
        and "result=trimmed freed=1200MiB files=3 cap_unmet=yes" in r.stdout
    )
    assert (world.root / "fleet-job-cache-hot-gocache").is_dir() and world.removed() == []


@needs_gnu_find
def test_the_floor_is_the_busy_hours_setting(world):
    files = go_cache(world, "fleet-job-cache-hot-gocache", [30, 20, 9, 7, 5, 3])
    r = world.run(
        {"CACHE_TRIM_MAX_GIB": "1", "CACHE_TRIM_BUSY_HOURS": "6", "FAKE_BUSY": "fleet-job-cache-hot-gocache"},
        program=PROGRAM,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert [f.exists() for f in files] == [False, False, False, False, True, True], (
        "with a 6 hour floor the 9 and 7 hour old files may go"
    )


@needs_gnu_find
def test_a_dry_run_changes_nothing_and_mounts_every_volume_read_only(world):
    files = go_cache(world, "fleet-job-cache-a-gocache", [50, 40, 30, 20, 10, 5, 2])
    hot = go_cache(world, "fleet-job-cache-hot-gocache", [60, 30, 14, 8, 3, 1.5])
    before = sorted(str(p.relative_to(world.root)) for p in world.root.rglob("*"))
    r = world.run(
        {"DRY_RUN": "1", "CACHE_TRIM_MAX_GIB": "1", "FAKE_BUSY": "fleet-job-cache-hot-gocache"}, program=PROGRAM
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert sorted(str(p.relative_to(world.root)) for p in world.root.rglob("*")) == before
    assert all(f.exists() for f in files + hot)
    assert world.mounts() and all(m.endswith(":ro") for m in world.mounts()), world.mounts()
    assert world.removed() == []
    assert "a-gocache state=idle kind=go-build size=2800MiB action=trim would_free=2000MiB" in r.stdout
    assert "hot-gocache state=busy kind=go-build size=2400MiB action=trim would_free=1200MiB" in r.stdout
    assert "DRY RUN, nothing was changed: 2 volumes, would trim 2 and remove 0 (3200 MiB)" in r.stdout


@needs_gnu_find
def test_a_cache_that_is_under_the_cap_is_left_as_it_is_however_old_its_files_are_until_30_days(world):
    """Whole volumes stay with idle-cache-volumes-trim.sh (3 idle days): this step has 30 days, and an age cut of 30 days inside."""
    young = go_cache(
        world, "fleet-job-cache-recent", [240, 241, 242], mib=100
    )  # 10 days old, 300 MiB, nothing wrote to it since
    r = world.run({"CACHE_TRIM_MAX_GIB": "1"}, program=PROGRAM)
    assert r.returncode == 0, r.stdout + r.stderr
    assert all(f.exists() for f in young) and world.removed() == []
    assert "1 volumes: trimmed 0, removed 0 (0 MiB freed), left alone 0, nothing to take 1" in r.stdout


@needs_gnu_find
def test_only_a_volume_nothing_wrote_to_for_30_days_and_no_container_refers_to_is_removed_whole_a_backstop_to_the_3_day_rule(
    world,
):
    """The program has no switch against removing a volume, so the number is ten times the 3-day rule: this pins what it does and when."""
    ancient = go_cache(world, "fleet-job-cache-ancient", [960, 961], mib=100)  # 40 days
    recent = go_cache(world, "fleet-job-cache-recent", [240], mib=100)  # 10 days
    attached = go_cache(
        world, "fleet-job-cache-stopped", [960], mib=100
    )  # 40 days, but a stopped container still refers to it
    r = world.run({"FAKE_STOPPED": "fleet-job-cache-stopped"}, program=PROGRAM)
    assert r.returncode == 0, r.stdout + r.stderr
    assert world.removed() == ["fleet-job-cache-ancient"]
    assert not any(f.exists() for f in ancient), (
        "nothing wrote to it for 30 days and nothing refers to it: the volume goes whole"
    )
    assert all(f.exists() for f in recent), "10 days idle is far under the backstop and the cache is under the cap"
    stopped = world.root / "fleet-job-cache-stopped"
    assert stopped.is_dir() and not attached[0].exists(), (
        "a stopped container still refers to it: docker would refuse, so the 30 day cut trims it inside instead"
    )
    assert "ancient state=idle kind=go-build size=200MiB result=removed" in r.stdout
    again = go_cache(world, "fleet-job-cache-ancient", [960, 961], mib=100)
    r = world.run({"CACHE_TRIM_UNUSED_DAYS": "45"}, program=PROGRAM)
    assert all(f.exists() for f in again) and world.removed() == ["fleet-job-cache-ancient"], (
        "with 45 days the same volume stays"
    )


@needs_gnu_find
def test_a_volume_that_docker_lost_since_it_was_listed_is_never_mounted(world):
    """A container that mounts a name docker does not have makes docker create it, empty (2026-10-31: three removed volumes came back)."""
    world.volume("fleet-job-cache-here")
    (world.bin / "docker").write_text(
        FAKE_DOCKER.replace('ls) ls -1 "${FAKE_ROOT:?}"', 'ls) echo fleet-job-cache-gone; ls -1 "${FAKE_ROOT:?}"')
    )
    r = world.run(program=PROGRAM)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (
        "fleet-job-cache-gone" not in "\n".join(world.mounts()) and not (world.root / "fleet-job-cache-gone").exists()
    )
    assert any(c == "volume inspect fleet-job-cache-gone" for c in world.calls())


# ---- the vendored program is go-fleet-job's, byte for byte, and the host's GC calls the step ------------------------------------------------------


def pin() -> tuple[str, str, str]:
    m = re.search(
        r"go-fleet-job tag (v\d+\.\d+\.\d+), commit ([0-9a-f]{40}), file pkg/remote/caches\.sh, sha256 ([0-9a-f]{64})",
        README.read_text(),
    )
    assert m, "the README names the tag, the commit and the sha256 the vendored program is pinned to"
    return m.group(1), m.group(2), m.group(3)


def test_the_vendored_program_is_the_pinned_upstream_file_and_the_manifest_agrees():
    tag, commit, sha = pin()
    data = PROGRAM.read_bytes()
    assert hashlib.sha256(data).hexdigest() == sha, (
        f"fleet-job-caches.sh is not go-fleet-job {tag} ({commit[:8]}) pkg/remote/caches.sh: update it as the README says"
    )
    manifest = {
        p.strip(): d for d, p in (line.split(None, 1) for line in (DIR / "files.sha256").read_text().splitlines())
    }
    assert manifest["usr/local/bin/fleet-job-caches.sh"] == sha
    assert (
        data.startswith(b"#!/bin/sh\n")
        and b"usage: caches.sh MODE MAX_AGE MAX_BYTES MIN_KEEP IMAGE [NAME [BUSY_KEEP]]" in data
    )
    assert os.access(PROGRAM, os.X_OK) and os.access(WRAPPER, os.X_OK)


def test_the_vendored_program_removes_nothing_but_cache_files_and_one_named_volume():
    """An audit that a re-vendored version has to pass again: files only through find -delete, volumes only through `docker volume rm "$v"`."""
    text = PROGRAM.read_text()
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert code.count("volume rm") == 1 and 'volume rm "$v"' in code
    assert code.count("-delete") == 1
    for banned in (
        "docker rm",
        "system prune",
        "volume prune",
        "image prune",
        "container prune",
        "rm -rf",
        "rm -r ",
        "rmdir",
        "unlink",
    ):
        assert banned not in code, banned
    assert "--pull never" in code and "--network none" in code and "--label fleet-job.gc=caches" in code


def test_the_gc_calls_the_step_right_after_the_whole_volume_step_with_a_timeout_and_only_when_it_is_installed():
    lines = [line.strip() for line in GC.read_text().splitlines()]
    i3c = lines.index(
        "[ -x /usr/local/bin/idle-cache-volumes-trim.sh ] && timeout 1800 /usr/local/bin/idle-cache-volumes-trim.sh 2>&1 | tail -8"
    )
    assert (
        lines[i3c + 1]
        == "[ -x /usr/local/bin/fleet-job-caches-trim.sh ] && timeout 1800 /usr/local/bin/fleet-job-caches-trim.sh 2>&1 | tail -12"
    )
    text = GC.read_text()
    assert "DRY_RUN" not in text and "CACHE_TRIM_" not in text, (
        "every setting has its default in the step itself, none is passed by the GC"
    )
    assert "3d. the Go build cache INSIDE each fleet-job-cache-* volume" in text


def test_the_readme_names_the_two_new_files_the_pin_the_name_gap_and_the_staged_apply_plan():
    readme = README.read_text()
    for needle in (
        "fleet-job-caches-trim.sh",
        "fleet-job-caches.sh",
        "docker-build-gc.sh",
        "chmod -x /usr/local/bin/fleet-job-caches-trim.sh",
        "DRY_RUN=1",
        "CACHE_TRIM_PULL",
        "CACHE_TRIM_MIN_FREE_GIB",
        "fleet_job_caches_trim",
        "WARNING",
        "cbe8c83345a41eac",
        "docker image prune -a",
    ):
        assert needle in readme, needle
    pin()
