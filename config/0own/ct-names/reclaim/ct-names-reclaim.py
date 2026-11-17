#!/usr/bin/env python3
"""One conservative, resumable ext4 block-group trim per systemd timer tick."""

import fcntl
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

MOUNT = "/srv/ct-names"
STATE_DIR = Path("/var/lib/ct-names-reclaim")
METRIC = Path("/var/lib/prometheus/node-exporter/textfile/ct_names_reclaim.prom")
PSI = Path("/proc/pressure/io")
GROUP_BYTES = 128 * 1024 * 1024


def run(*cmd, timeout=10):
    return subprocess.check_output(cmd, text=True, timeout=timeout).strip()


def atomic(path, value, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(value)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
        dfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def pressure(text):
    m = re.search(r"^some\s+avg10=([\d.]+)", text, re.MULTILINE)
    if not m:
        raise ValueError("host I/O pressure unavailable")
    return float(m.group(1))


def reader_ready(text):
    vals = dict(re.findall(r'^ct_names_reader_paused\{reason="([a-z_]+)"\}\s+([0-9.]+)$', text, re.MULTILINE))
    expected = {"disk", "host_memory", "io", "load", "memory"}
    rate = re.search(r"^ct_names_entries_per_second\s+([0-9.eE+-]+)$", text, re.MULTILINE)
    return (
        expected == set(vals) and all(float(v) == 0 for v in vals.values()) and bool(rate) and float(rate.group(1)) > 0
    )


def identity():
    source = run("findmnt", "-n", "-o", "SOURCE", "--mountpoint", MOUNT)
    if run("findmnt", "-n", "-o", "FSTYPE", "--mountpoint", MOUNT) != "ext4":
        raise ValueError("CT filesystem is not ext4")
    if run("blkid", "-s", "LABEL", "-o", "value", source) != "ctnames":
        raise ValueError("CT filesystem label mismatch")
    if run("lsblk", "-n", "-d", "-o", "SERIAL", source) != "CTNAMES0":
        raise ValueError("CT disk serial mismatch")
    uuid = run("blkid", "-s", "UUID", "-o", "value", source)
    size = int(run("blockdev", "--getsize64", source))
    info = run("tune2fs", "-l", source)
    block = int(re.search(r"^Block size:\s*(\d+)$", info, re.M).group(1))
    per_group = int(re.search(r"^Blocks per group:\s*(\d+)$", info, re.M).group(1))
    blocks = int(re.search(r"^Block count:\s*(\d+)$", info, re.M).group(1))
    if block * per_group != GROUP_BYTES or blocks * block != size or size % GROUP_BYTES:
        raise ValueError("unexpected filesystem geometry; refusing to trim")
    line = [
        line
        for line in Path("/etc/fstab").read_text().splitlines()
        if not line.lstrip().startswith("#") and len(line.split()) >= 4 and line.split()[1] == MOUNT
    ]
    if len(line) != 1 or line[0].split()[0] != "UUID=" + uuid or "X-fstrim.notrim" not in line[0].split()[3].split(","):
        raise ValueError("CT disk is not excluded from weekly trim")
    return uuid, size


def reader_metrics():
    ports = json.loads(run("docker", "inspect", "go-ct-names", "--format", "{{json .NetworkSettings.Ports}}"))
    bindings = ports["18336/tcp"]
    if len(bindings) != 1 or bindings[0]["HostPort"] != "18336":
        raise ValueError("unexpected reader binding")
    host = bindings[0]["HostIp"]
    if not re.fullmatch(r"100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}", host):
        raise ValueError("reader binding is not the expected tailnet address")
    with build_opener(ProxyHandler({})).open(f"http://{host}:18336/metrics", timeout=5) as response:
        return response.read(1024 * 1024).decode()


def trim_group(offset, lock_fd):
    # Pass the lock into fstrim: even if systemd kills this parent while the
    # kernel has the child in uninterruptible I/O, another tick cannot overlap.
    proc = subprocess.Popen(
        ["fstrim", "-o", str(offset), "-l", str(GROUP_BYTES), MOUNT],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        pass_fds=(lock_fd,),
    )
    start = time.monotonic()
    stop_reason = None
    while proc.poll() is None:
        try:
            if time.monotonic() - start > 15:
                stop_reason = "trim exceeded 15 seconds"
            elif pressure(PSI.read_text()) >= 40:
                stop_reason = "I/O pressure crossed the trim safety threshold"
        except (OSError, ValueError):
            stop_reason = "I/O pressure became unavailable"
        if stop_reason:
            proc.kill()
            # This may wait for uninterruptible kernel I/O; the child retains
            # the inherited lock and stale metrics alert if it does not exit.
            proc.wait()
            raise RuntimeError(stop_reason)
        time.sleep(0.5)
    if proc.returncode:
        raise RuntimeError(f"fstrim failed with status {proc.returncode}")
    return round(time.monotonic() - start, 3)


def metrics(s):
    keys = ("started", "last_progress", "offset", "size", "cycles", "blocked", "error", "duration")
    atomic(METRIC, "".join(f"ct_names_reclaim_{key} {s.get(key, 0)}\n" for key in keys), mode=0o644)


def main():
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE_DIR / "lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        uuid, size = identity()
        path = STATE_DIR / "state.json"
        if path.exists():
            s = json.loads(path.read_text())
            if (
                s.get("uuid") != uuid
                or s.get("size") != size
                or not isinstance(s.get("offset"), int)
                or not 0 <= s["offset"] < size
                or s["offset"] % GROUP_BYTES
            ):
                raise ValueError("checkpoint does not match CT disk; refusing to reset it")
        else:
            s = {"uuid": uuid, "size": size, "offset": 0, "cycles": 0, "last_progress": int(time.time())}
            atomic(path, json.dumps(s) + "\n")
        s.update(started=int(time.time()), blocked=0, error=0)
        metrics(s)  # A stuck syscall leaves a stale start timestamp for monitoring.
        try:
            if pressure(PSI.read_text()) >= 10 or not reader_ready(reader_metrics()):
                s["blocked"] = 1
                metrics(s)
                return
            s["duration"] = trim_group(s["offset"], lock.fileno())
            s["offset"] += GROUP_BYTES
            if s["offset"] >= size:
                s["offset"] = 0
                s["cycles"] = int(s.get("cycles", 0)) + 1
            s["last_progress"] = int(time.time())
            atomic(path, json.dumps(s) + "\n")
            metrics(s)
        except Exception:
            s["error"] = 1
            metrics(s)
            raise


if __name__ == "__main__":
    main()
