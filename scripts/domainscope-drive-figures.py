#!/usr/bin/env python3
"""Read and validate the current data-room aggregate without accessing credentials.

Only a fixed file in the existing cron container is read. Git supplies the
reviewed refresh tool and document manifest, not a periodically committed report.
"""
import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time

MAX_BYTES = 1024 * 1024
READ_TIMEOUT = 30
MAX_AGE = dt.timedelta(days=8)
REMOTE_READ = "docker exec domainscope-cron cat /data/metrics/data-room/latest.json"


def fetch(host, timeout=READ_TIMEOUT, max_bytes=MAX_BYTES):
    if not host or host.startswith("-") or any(c.isspace() for c in host):
        raise ValueError("configure DSDRIVE_FIGURES_HOST as an SSH target")
    command = ["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
               "-o", "StrictHostKeyChecking=yes",
               "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2",
               "--", host, REMOTE_READ]
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    deadline = time.monotonic() + timeout
    data = bytearray()
    try:
        with selectors.DefaultSelector() as ready:
            ready.register(proc.stdout, selectors.EVENT_READ)
            while True:
                left = deadline - time.monotonic()
                if left <= 0 or not ready.select(left):
                    raise ValueError("current figures SSH read timed out")
                chunk = os.read(proc.stdout.fileno(), min(65536, max_bytes - len(data) + 1))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > max_bytes:
                    raise ValueError("current figures exceed the 1 MiB limit")
        try:
            rc = proc.wait(timeout=max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise ValueError("current figures SSH read timed out")
        if rc:
            raise ValueError("current figures SSH read failed (exit %d)" % rc)
        return bytes(data)
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
        proc.stdout.close()


def validate(raw, now=None):
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("current figures are empty or exceed the 1 MiB limit")
    now = now or dt.datetime.now(dt.timezone.utc)
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError("current figures must be a JSON object")
    stamp = obj.get("generated_at", "")
    # Go writes RFC3339Nano; Python 3.9 accepts only three or six fractional
    # digits. Normalize the fraction before parsing, retaining microseconds.
    match = re.fullmatch(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?(Z|[+-]\d\d:\d\d)", stamp)
    if not match:
        raise ValueError("current figures generated_at must use RFC3339 with a timezone")
    whole, fraction, zone = match.groups()
    normalized = whole + ("." + fraction.ljust(6, "0")[:6] if fraction else "")
    generated = dt.datetime.fromisoformat(normalized + ("+00:00" if zone == "Z" else zone))
    if generated.tzinfo is None:
        raise ValueError("current figures generated_at must include a timezone")
    if now - generated > MAX_AGE:
        raise ValueError("current figures are older than the 8-day limit")
    if generated - now > dt.timedelta(minutes=5):
        raise ValueError("current figures generated_at is in the future")
    catalogue = obj.get("catalogue", {})
    if not isinstance(catalogue, dict) or catalogue.get("available") is not True:
        raise ValueError("current figures catalogue is not available")
    figures = {}
    for fig in catalogue.get("figures", []):
        if not isinstance(fig, dict):
            raise ValueError("current catalogue figures must be objects")
        key = fig.get("key")
        if key not in ("domains_catalogued", "embedded"):
            continue
        value = fig.get("value")
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0 or int(value) != value:
            raise ValueError("current %s figure must be a positive whole number" % key)
        if key in figures:
            raise ValueError("current figures contain a duplicate %s" % key)
        day = dt.date.fromisoformat(fig.get("as_of", "")[:10])
        figures[key] = (value, day)
    if len(figures) != 2:
        raise ValueError("current figures need domains_catalogued and embedded")
    catalogued, embedded = figures["domains_catalogued"], figures["embedded"]
    if embedded[0] > catalogued[0] or embedded[1] != catalogued[1]:
        raise ValueError("current catalogue figures have inconsistent counts or dates")
    if catalogued[1] > now.date() or now.date() - catalogued[1] > MAX_AGE:
        raise ValueError("current catalogue as_of date is in the future or older than 8 days")
    return generated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="")
    parser.add_argument("--input-file", default="", help="explicit local aggregate for an offline check")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    tmp = None
    try:
        if args.input_file:
            with open(args.input_file, "rb") as source:
                raw = source.read(MAX_BYTES + 1)
        else:
            raw = fetch(args.host)
        generated = validate(raw)
        destination = Path(args.out)
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".figures-", delete=False) as output:
            tmp = Path(output.name)
            output.write(raw)
        os.replace(str(tmp), str(destination))
        tmp = None
        print("current figures validated (generated %s)" % generated.isoformat())
        return 0
    except (OSError, ValueError, TypeError, AttributeError, OverflowError) as error:
        print("current figures unavailable: %s" % error, file=sys.stderr)
        return 3
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
