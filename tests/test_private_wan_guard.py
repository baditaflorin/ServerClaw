"""Exercise TC guard health against kernel-style JSON without changing host networking."""

import json
import os
import subprocess
from pathlib import Path

GUARD = Path(__file__).resolve().parents[1] / "config/private-wan-guard/wan-guard-tc.sh"
PREFIXES = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "169.254.0.0/16"]


def check(tmp_path: Path, rules: list[dict]) -> subprocess.CompletedProcess[str]:
    (tmp_path / "ip").write_text("#!/bin/sh\nexit 0\n")
    (tmp_path / "tc").write_text("#!/bin/sh\nprintf '%s\\n' \"$TC_FIXTURE\"\n")
    for binary in ("ip", "tc"):
        (tmp_path / binary).chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    env["TC_FIXTURE"] = json.dumps(rules)
    return subprocess.run([str(GUARD), "verify", "testwan"], env=env, text=True, capture_output=True, check=False)


def good_rules() -> list[dict]:
    return [
        {
            "protocol": "ip",
            "pref": 49000,
            "kind": "flower",
            "chain": 0,
            "options": {
                "handle": i,
                "keys": {"dst_ip": prefix},
                "skip_hw": True,
                "actions": [{"kind": "gact", "control_action": {"type": "drop"}}],
            },
        }
        for i, prefix in enumerate(PREFIXES, 1)
    ]


def test_guard_accepts_all_software_ipv4_drops(tmp_path: Path) -> None:
    assert check(tmp_path, good_rules()).returncode == 0


def test_guard_rejects_missing_or_non_ip_or_hardware_only_rule(tmp_path: Path) -> None:
    rules = good_rules()
    rules.pop()
    assert check(tmp_path, rules).returncode != 0
    rules = good_rules()
    rules[0]["protocol"] = "ipv6"
    assert check(tmp_path, rules).returncode != 0
    rules = good_rules()
    rules[0]["options"]["skip_hw"] = False
    assert check(tmp_path, rules).returncode != 0


def test_guard_rejects_earlier_classifier(tmp_path: Path) -> None:
    rules = good_rules() + [{"protocol": "ip", "pref": 10, "kind": "flower", "chain": 0}]
    result = check(tmp_path, rules)
    assert result.returncode != 0
    assert "higher-priority" in result.stderr
