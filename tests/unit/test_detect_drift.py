"""Unit tests for scripts/detect_drift.py — ADR 0485.

Tests the pure helpers only (no subprocess invocations).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from detect_drift import (
    HostRecap,
    is_drift,
    parse_play_recap,
    summarise_recap,
)


# ---------------------------------------------------------------------------
# parse_play_recap
# ---------------------------------------------------------------------------


class TestParsePlayRecap:
    def _sample_recap(self) -> str:
        return (
            "PLAY RECAP *****\n"
            "10.10.10.92 : ok=23 changed=0 unreachable=0 failed=0 skipped=5 rescued=0 ignored=0\n"
            "10.10.10.20 : ok=11 changed=2 unreachable=0 failed=0 skipped=1 rescued=0 ignored=0\n"
        )

    def test_parses_multiple_hosts(self):
        hosts = parse_play_recap(self._sample_recap())
        assert len(hosts) == 2

    def test_parses_changed_count(self):
        hosts = parse_play_recap(self._sample_recap())
        host_map = {h.host: h for h in hosts}
        assert host_map["10.10.10.92"].changed == 0
        assert host_map["10.10.10.20"].changed == 2

    def test_parses_ok_count(self):
        hosts = parse_play_recap(self._sample_recap())
        host_map = {h.host: h for h in hosts}
        assert host_map["10.10.10.92"].ok == 23

    def test_parses_failed_count(self):
        text = "host1 : ok=5 changed=0 unreachable=0 failed=1 skipped=0 rescued=0 ignored=0\n"
        hosts = parse_play_recap(text)
        assert hosts[0].failed == 1

    def test_parses_unreachable(self):
        text = "host1 : ok=0 changed=0 unreachable=1 failed=0 skipped=0 rescued=0 ignored=0\n"
        hosts = parse_play_recap(text)
        assert hosts[0].unreachable == 1

    def test_localhost_alias(self):
        text = "localhost : ok=3 changed=1 unreachable=0 failed=0 skipped=0 rescued=0 ignored=0\n"
        hosts = parse_play_recap(text)
        assert len(hosts) == 1
        assert hosts[0].host == "localhost"

    def test_empty_output(self):
        assert parse_play_recap("") == []

    def test_ignores_non_recap_lines(self):
        text = (
            "TASK [some role : do something] ***\n"
            "ok: [10.0.0.1]\n"
            "PLAY RECAP ***\n"
            "10.0.0.1 : ok=5 changed=0 unreachable=0 failed=0 skipped=0 rescued=0 ignored=0\n"
        )
        hosts = parse_play_recap(text)
        assert len(hosts) == 1


# ---------------------------------------------------------------------------
# summarise_recap
# ---------------------------------------------------------------------------


class TestSummariseRecap:
    def test_sums_across_hosts(self):
        hosts = [
            HostRecap("a", ok=10, changed=1, unreachable=0, failed=0),
            HostRecap("b", ok=5, changed=2, unreachable=1, failed=0),
            HostRecap("c", ok=3, changed=0, unreachable=0, failed=1),
        ]
        changed, unreachable, failed = summarise_recap(hosts)
        assert changed == 3
        assert unreachable == 1
        assert failed == 1

    def test_all_clean(self):
        hosts = [
            HostRecap("a", ok=5, changed=0, unreachable=0, failed=0),
            HostRecap("b", ok=3, changed=0, unreachable=0, failed=0),
        ]
        changed, unreachable, failed = summarise_recap(hosts)
        assert changed == 0 and unreachable == 0 and failed == 0

    def test_empty_list(self):
        assert summarise_recap([]) == (0, 0, 0)


# ---------------------------------------------------------------------------
# is_drift
# ---------------------------------------------------------------------------


class TestIsDrift:
    def test_no_drift_when_all_zero(self):
        hosts = [HostRecap("a", ok=10, changed=0, unreachable=0, failed=0)]
        assert is_drift(hosts) is False

    def test_drift_when_changed_nonzero(self):
        hosts = [HostRecap("a", ok=10, changed=1, unreachable=0, failed=0)]
        assert is_drift(hosts) is True

    def test_drift_when_unreachable_nonzero(self):
        hosts = [HostRecap("a", ok=0, changed=0, unreachable=1, failed=0)]
        assert is_drift(hosts) is True

    def test_drift_when_failed_nonzero(self):
        hosts = [HostRecap("a", ok=0, changed=0, unreachable=0, failed=1)]
        assert is_drift(hosts) is True

    def test_no_drift_with_empty_list(self):
        assert is_drift([]) is False

    def test_drift_with_multiple_hosts_mixed(self):
        hosts = [
            HostRecap("a", ok=5, changed=0, unreachable=0, failed=0),
            HostRecap("b", ok=5, changed=3, unreachable=0, failed=0),
        ]
        assert is_drift(hosts) is True
