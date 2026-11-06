"""Bounded SSH reads and schema/freshness checks, with no network or credentials."""
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("drive_figures", ROOT / "scripts/domainscope-drive-figures.py")
figures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(figures)

FAKE_SSH = r'''#!/usr/bin/env python3
import json, os, sys, time
with open(os.environ["SSH_ARGS"], "w") as f: json.dump(sys.argv[1:], f)
mode = os.environ["SSH_MODE"]
if mode == "error": sys.exit(7)
if mode == "hang": time.sleep(60)
if mode == "large":
    try:
        while True: os.write(1, b"x" * 65536)
    except BrokenPipeError: sys.exit(0)
os.write(1, b'{"report":true}')
'''


def report():
    return {"generated_at": "2026-11-06T08:17:00Z", "catalogue": {
        "available": True, "figures": [
            {"key": "domains_catalogued", "value": 200, "as_of": "2026-11-03"},
            {"key": "embedded", "value": 100, "as_of": "2026-11-03"},
        ]}}


class CurrentFigures(unittest.TestCase):
    now = dt.datetime(2026, 11, 6, 12, tzinfo=dt.timezone.utc)

    def check(self, obj):
        return figures.validate(json.dumps(obj).encode(), now=self.now)

    def test_valid_live_aggregate(self):
        self.assertEqual(self.check(report()).hour, 8)

    def test_go_rfc3339_nanoseconds_work_with_python_39(self):
        for fraction in ("1", "12", "1234", "121286145"):
            obj = report()
            obj["generated_at"] = "2026-11-06T08:17:00.%sZ" % fraction
            self.assertEqual(self.check(obj).microsecond, int(fraction.ljust(6, "0")[:6]))

    def test_stale_future_unavailable_and_inconsistent_inputs_are_rejected(self):
        for kind in ("stale", "future", "unavailable", "missing", "count", "date", "boolean", "duplicate", "old_asof", "future_asof"):
            with self.subTest(kind=kind):
                obj = report()
                if kind == "stale": obj["generated_at"] = "2026-10-26T06:45:13Z"
                if kind == "future": obj["generated_at"] = "2026-11-07T08:17:00Z"
                if kind == "unavailable": obj["catalogue"]["available"] = False
                fs = obj["catalogue"]["figures"]
                if kind == "missing": fs.pop()
                if kind == "count": fs[1]["value"] = 201
                if kind == "date": fs[1]["as_of"] = "2026-11-04"
                if kind == "boolean": fs[1]["value"] = True
                if kind == "duplicate": fs.append(fs[1])
                if kind in ("old_asof", "future_asof"):
                    for fig in fs:
                        fig["as_of"] = "2026-10-26" if kind == "old_asof" else "2026-11-07"
                with self.assertRaises(ValueError): self.check(obj)

    def test_malformed_and_oversized_json_are_rejected(self):
        for raw in (b"", b"not json", b"[]", b" " * (figures.MAX_BYTES + 1)):
            with self.assertRaises(ValueError): figures.validate(raw, self.now)

    def fetch(self, mode, timeout=2):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ssh = root / "ssh"
            ssh.write_text(FAKE_SSH)
            ssh.chmod(0o755)
            args = root / "args.json"
            with patch.dict(os.environ, {"PATH": str(root) + os.pathsep + os.environ["PATH"],
                                         "SSH_ARGS": str(args), "SSH_MODE": mode}):
                data = figures.fetch("report-host.example.com", timeout=timeout)
            return data, json.loads(args.read_text())

    def test_ssh_uses_only_fixed_read_command(self):
        data, args = self.fetch("ok")
        self.assertEqual(data, b'{"report":true}')
        self.assertEqual(args[-2:], ["report-host.example.com", figures.REMOTE_READ])
        self.assertIn("BatchMode=yes", args)
        self.assertIn("StrictHostKeyChecking=yes", args)

    def test_ssh_failure_is_not_treated_as_a_report(self):
        with self.assertRaisesRegex(ValueError, "exit 7"): self.fetch("error")

    def test_ssh_stream_is_capped_locally(self):
        with self.assertRaisesRegex(ValueError, "1 MiB"): self.fetch("large")

    def test_hung_ssh_is_killed_by_deadline(self):
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, "timed out"): self.fetch("hang", timeout=0.1)
        self.assertLess(time.monotonic() - started, 3)


if __name__ == "__main__":
    unittest.main()
