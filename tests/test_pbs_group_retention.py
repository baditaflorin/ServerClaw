"""pbs-group-retention (config/0infer/tier0-pbs2/pbs-group-retention): per-group retention on PBS #2.

PBS prune jobs select by namespace only; this tool shortens the retention of two named groups, so what matters is that it can never delete more than it was told to: never one of the newest
keep_last snapshots, never a protected one, never from a group whose feed looks broken, never on the strength of a datastore answer that disagrees with its own arithmetic. The datastore API is
replaced by a fake that implements PBS's real per-group prune semantics (keep-last N, protected snapshots survive, dry run changes nothing); the real command line is pinned separately with a shim.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "config" / "0infer" / "tier0-pbs2" / "pbs-group-retention"
loader = importlib.machinery.SourceFileLoader("pgr", str(SRC))
spec = importlib.util.spec_from_loader("pgr", loader)
pgr = importlib.util.module_from_spec(spec)
sys.modules["pgr"] = pgr
loader.exec_module(pgr)

NOW = 1_792_300_000.0
H = 3600


class FakeApi:
    """The slice of the PBS datastore API the tool uses, with PBS's prune semantics."""

    def __init__(self, groups: dict):
        self.groups = {k: [dict(s) for s in v] for k, v in groups.items()}      # (ns, type, id) -> [{"backup-time", "protected"}]
        self.calls = []
        self.fail_prune = False
        self.dry_lies = None                                                      # callable(entries) -> entries, to simulate a datastore that disagrees with the arithmetic
        self.prune_lies = False                                                   # a real prune that deletes too much

    def snapshots(self, ns, typ, bid):
        self.calls.append(("snapshots", ns, typ, bid))
        return [dict(s) for s in self.groups.get((ns, typ, bid), [])]

    def prune(self, ns, typ, bid, keep_last, dry_run):
        self.calls.append(("prune", ns, typ, bid, keep_last, dry_run))
        if self.fail_prune and not dry_run:
            raise pgr.Failure("lock held by a running sync")
        snaps = sorted(self.groups.get((ns, typ, bid), []), key=lambda s: s["backup-time"])
        newest = {s["backup-time"] for s in snaps[-keep_last:]}
        entries = [{"backup-id": bid, "backup-time": s["backup-time"], "backup-type": typ, "keep": s["backup-time"] in newest or bool(s.get("protected")), "ns": ns, "protected": bool(s.get("protected"))} for s in snaps]
        if dry_run:
            return self.dry_lies(entries) if self.dry_lies else entries
        gone = {e["backup-time"] for e in entries if not e["keep"]}
        if self.prune_lies:
            gone |= {snaps[-1]["backup-time"]}
        self.groups[(ns, typ, bid)] = [s for s in snaps if s["backup-time"] not in gone]
        return entries


def snaps(n, newest_age_h=3.0, step_h=24, protected=()):
    times = [int(NOW - newest_age_h * H - i * step_h * H) for i in range(n)][::-1]
    return [{"backup-time": t, "protected": t in protected} for t in times]


GROUPS = [{"ns": "0docker", "type": "vm", "id": "100", "keep_last": 2}, {"ns": "0database", "type": "vm", "id": "100", "keep_last": 2}]


def cfg_file(tmp_path, groups=GROUPS, **extra):
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({"store": "tier0", "groups": groups, **extra}))
    return str(p)


def run(tmp_path, api, *args, groups=GROUPS, **extra):
    log = []
    monkey_prom = tmp_path / "prom" / "x.prom"
    pgr.PROM = str(monkey_prom)
    rc = pgr.main(["--config", cfg_file(tmp_path, groups, **extra), *args], api=api, now=NOW, log=log.append)
    return rc, log


def world(over=None):
    g = {("0docker", "vm", "100"): snaps(5), ("0database", "vm", "100"): snaps(4)}
    g.update(over or {})
    return FakeApi(g)


# ---- what it does -----------------------------------------------------------------------------------------------------------------
def test_the_default_is_a_dry_run_that_changes_nothing_and_writes_no_metrics(tmp_path):
    api = world()
    rc, log = run(tmp_path, api)
    assert rc == 0 and all(c[5] for c in api.calls if c[0] == "prune")             # only dry-run prune calls
    assert len(api.groups[("0docker", "vm", "100")]) == 5 and len(api.groups[("0database", "vm", "100")]) == 4
    assert any("would delete 3 oldest" in l for l in log) and any("would delete 2 oldest" in l for l in log)
    assert not (tmp_path / "prom" / "x.prom").exists()


def test_apply_prunes_each_group_to_its_newest_two_and_exports_metrics(tmp_path):
    api = world()
    before = {k: [s["backup-time"] for s in v] for k, v in api.groups.items()}
    rc, log = run(tmp_path, api, "--apply")
    assert rc == 0
    for k, v in api.groups.items():
        assert [s["backup-time"] for s in v] == before[k][-2:]                      # exactly the newest two, in order
    m = (tmp_path / "prom" / "x.prom").read_text()
    assert 'pbs_group_retention_group_ok{group="0docker:vm/100"} 1' in m and 'pbs_group_retention_deleted_snapshots{group="0docker:vm/100"} 3' in m
    assert 'pbs_group_retention_snapshots{group="0database:vm/100"} 2' in m and "pbs_group_retention_last_success_timestamp_seconds 1792300000" in m


def test_a_second_run_changes_nothing(tmp_path):
    api = world()
    run(tmp_path, api, "--apply")
    api.calls.clear()
    rc, log = run(tmp_path, api, "--apply")
    assert rc == 0 and not any(c[0] == "prune" for c in api.calls)                  # nothing beyond keep_last: no prune call at all
    assert any("nothing to do" in l for l in log)


def test_only_the_configured_groups_are_ever_touched(tmp_path):
    api = world({("0docker", "vm", "101"): snaps(5), ("0own", "vm", "630"): snaps(4)})
    run(tmp_path, api, "--apply")
    assert len(api.groups[("0docker", "vm", "101")]) == 5 and len(api.groups[("0own", "vm", "630")]) == 4
    assert {(c[1], c[2], c[3]) for c in api.calls} == {("0docker", "vm", "100"), ("0database", "vm", "100")}


def test_a_protected_snapshot_survives_and_the_group_is_still_ok(tmp_path):
    s = snaps(5)
    s[0]["protected"] = True                                                       # the oldest is protected (a deliberate keep)
    api = world({("0docker", "vm", "100"): s})
    rc, log = run(tmp_path, api, "--apply")
    assert rc == 0
    left = [x["backup-time"] for x in api.groups[("0docker", "vm", "100")]]
    assert s[0]["backup-time"] in left and set(x["backup-time"] for x in s[-2:]) <= set(left) and len(left) == 3


def test_the_root_namespace_is_addressed_without_an_ns_argument():
    calls = []
    class P:
        returncode = 0; stdout = "[]"; stderr = ""
    orig = pgr.subprocess.run
    pgr.subprocess.run = lambda argv, **k: (calls.append(argv), P())[1]
    try:
        pgr.Api("tier0").snapshots("", "vm", "100")
        pgr.Api("tier0").prune("0docker", "vm", "100", 2, True)
    finally:
        pgr.subprocess.run = orig
    assert calls[0] == ["proxmox-backup-debug", "api", "get", "/admin/datastore/tier0/snapshots", "--backup-type", "vm", "--backup-id", "100", "--output-format", "json"]       # root namespace: no --ns
    assert calls[1] == ["proxmox-backup-debug", "api", "create", "/admin/datastore/tier0/prune", "--ns", "0docker", "--backup-type", "vm", "--backup-id", "100",
                        "--keep-last", "2", "--dry-run", "true", "--output-format", "json"]


# ---- the guards ---------------------------------------------------------------------------------------------------------------------
def test_keep_last_below_two_is_a_config_error_and_nothing_runs(tmp_path):
    api = world()
    for bad in (1, 0, -3, "2", None):
        rc, _ = run(tmp_path, api, "--apply", groups=[{"ns": "0docker", "type": "vm", "id": "100", "keep_last": bad}])
        assert rc == 3
    assert api.calls == []


def test_unsafe_or_incomplete_config_values_are_refused(tmp_path):
    api = world()
    for bad in ({"ns": "0docker; rm -rf /", "type": "vm", "id": "100", "keep_last": 2}, {"ns": "0docker", "type": "disk", "id": "100", "keep_last": 2},
                {"ns": "0docker", "type": "vm", "id": "", "keep_last": 2}, {"ns": "0docker", "type": "vm", "keep_last": 2}, {"ns": "a b", "type": "vm", "id": "1", "keep_last": 2}):
        rc, _ = run(tmp_path, api, "--apply", groups=[bad])
        assert rc == 3, bad
    assert api.calls == []
    assert pgr.main(["--config", str(tmp_path / "missing.json")], api=api, now=NOW, log=lambda s: None) == 3


def test_a_group_with_no_more_than_keep_last_snapshots_is_left_alone(tmp_path):
    api = world({("0docker", "vm", "100"): snaps(2), ("0database", "vm", "100"): snaps(1)})
    rc, log = run(tmp_path, api, "--apply")
    assert rc == 0 and not any(c[0] == "prune" for c in api.calls)


def test_a_stale_group_is_not_pruned_and_the_run_reports_failure(tmp_path):
    api = world({("0docker", "vm", "100"): snaps(5, newest_age_h=100)})          # the feed is broken: the newest snapshot is 4 days old
    rc, log = run(tmp_path, api, "--apply")
    assert rc == 2 and len(api.groups[("0docker", "vm", "100")]) == 5
    assert any("sync that feeds this group looks broken" in l for l in log)
    assert len(api.groups[("0database", "vm", "100")]) == 2                        # the healthy group was still pruned
    assert 'pbs_group_retention_group_ok{group="0docker:vm/100"} 0' in (tmp_path / "prom" / "x.prom").read_text()


def test_a_frozen_group_is_pruned_to_keep_last_even_though_its_newest_snapshot_is_old(tmp_path):
    """2026-10-21: 0docker vm/100 has no new snapshot because its job is paused on purpose; the age guard failed the whole run every morning (PbsGroupRetentionFailed)."""
    groups = [dict(GROUPS[0], frozen=True), GROUPS[1]]
    api = world({("0docker", "vm", "100"): snaps(5, newest_age_h=100)})
    rc, log = run(tmp_path, api, "--apply", groups=groups)
    assert rc == 0 and len(api.groups[("0docker", "vm", "100")]) == 2 and len(api.groups[("0database", "vm", "100")]) == 2
    assert 'pbs_group_retention_group_ok{group="0docker:vm/100"} 1' in (tmp_path / "prom" / "x.prom").read_text()
    # frozen is a flag for the age guard only: it never lowers keep_last and `false` behaves like absent
    api2 = world({("0docker", "vm", "100"): snaps(5, newest_age_h=100)})
    rc2, _ = run(tmp_path, api2, "--apply", groups=[dict(GROUPS[0], frozen=False), GROUPS[1]])
    assert rc2 == 2 and len(api2.groups[("0docker", "vm", "100")]) == 5


def test_frozen_must_be_true_or_false(tmp_path):
    with pytest.raises(ValueError, match="frozen"):
        pgr.load_config(cfg_file(tmp_path, [dict(GROUPS[0], frozen="yes")]))


def test_a_datastore_dry_run_that_would_delete_a_newest_snapshot_is_refused_and_nothing_is_deleted(tmp_path):
    api = world()
    def lie(entries):
        entries[-1]["keep"] = False; return entries                                 # "delete the newest too"
    api.dry_lies = lie
    rc, log = run(tmp_path, api, "--apply")
    assert rc == 2 and not any(c[0] == "prune" and not c[5] for c in api.calls)
    assert len(api.groups[("0docker", "vm", "100")]) == 5
    assert any("must stay" in l for l in log)


def test_a_dry_run_that_marks_everything_but_the_oldest_for_deletion_is_refused(tmp_path):
    api = world()
    def lie(entries):
        for e in entries[1:]: e["keep"] = False
        return entries
    api.dry_lies = lie                                                              # keeps the OLDEST and deletes the newest ones: the opposite of keep-last
    rc, log = run(tmp_path, api, "--apply")
    assert rc == 2 and not any(c[0] == "prune" and not c[5] for c in api.calls)


def test_a_dry_run_listing_other_snapshots_than_the_group_has_is_refused(tmp_path):
    api = world()
    api.dry_lies = lambda entries: entries[:-1]                                     # a snapshot missing from the dry run: the two views disagree
    rc, log = run(tmp_path, api, "--apply")
    assert rc == 2 and not any(c[0] == "prune" and not c[5] for c in api.calls) and any("does not list the same snapshots" in l for l in log)


def test_a_real_prune_that_removed_a_newest_snapshot_is_reported_loudly(tmp_path):
    api = world()
    api.prune_lies = True
    rc, log = run(tmp_path, api, "--apply")
    assert rc == 2 and any("AFTER the prune a snapshot that must stay is missing" in l for l in log)


def test_a_prune_that_fails_is_one_failed_group_not_a_crash_and_the_other_group_still_runs(tmp_path):
    api = world()
    api.fail_prune = True
    rc, log = run(tmp_path, api, "--apply")
    assert rc == 2 and sum(1 for l in log if l.startswith("FAIL")) == 2 and any("lock held" in l for l in log)
    api.fail_prune = False
    rc, log = run(tmp_path, api, "--apply")
    assert rc == 0                                                                  # tomorrow's run succeeds on its own


def test_the_previous_success_timestamp_survives_a_failed_run_so_the_staleness_alert_measures_from_it(tmp_path):
    api = world()
    run(tmp_path, api, "--apply")
    api2 = world({("0docker", "vm", "100"): snaps(5, newest_age_h=100)})
    pgr.PROM = str(tmp_path / "prom" / "x.prom")
    pgr.main(["--config", cfg_file(tmp_path), "--apply"], api=api2, now=NOW + 86400, log=lambda s: None)
    m = (tmp_path / "prom" / "x.prom").read_text()
    assert f"pbs_group_retention_last_run_timestamp_seconds {int(NOW + 86400)}" in m and f"pbs_group_retention_last_success_timestamp_seconds {int(NOW)}" in m


# ---- the shipped config ---------------------------------------------------------------------------------------------------------------
def test_the_shipped_config_is_valid_and_names_exactly_the_two_big_groups():
    cfg = pgr.load_config(str(SRC.parent / "pbs-group-retention.json"))
    assert [pgr.label(g) for g in cfg["groups"]] == ["0docker:vm/100", "0database:vm/100"] and all(g["keep_last"] == 2 for g in cfg["groups"])
    assert all(g["frozen"] is True for g in cfg["groups"]), "both VM jobs are off (0docker vm/100 paused, 0database retired): the age guard would fail every run"
    assert cfg["store"] == "tier0"


def test_the_timer_runs_after_the_store_wide_prune_and_before_garbage_collection():
    t = (SRC.parent / "pbs-group-retention.timer").read_text()
    assert "07:05:00 UTC" in t                                                      # prune-tier0 is 07:00, GC 07:30 (docs/runbooks/tier0-infer-site.md)
    s = (SRC.parent / "pbs-group-retention.service").read_text()
    assert "ExecStart=/usr/local/sbin/pbs-group-retention --apply" in s
