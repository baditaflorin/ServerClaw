"""The parity gate (scripts/monitoring_live_parity.py) must pass on a faithful copy and FAIL on every kind of drift it claims to catch."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests"))
_spec = importlib.util.spec_from_file_location(
    "monitoring_live_parity", REPO_ROOT / "scripts" / "monitoring_live_parity.py"
)
parity = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(parity)
H = parity._helpers()


def _live_prometheus() -> dict:
    return parity._norm(H.render_prometheus(use_host_vars=True))


def test_prometheus_self_parity_passes() -> None:
    assert parity.compare_prometheus(yaml.safe_dump(_live_prometheus())) == []


def test_prometheus_removed_and_added_and_changed_jobs_are_reported() -> None:
    live = _live_prometheus()
    jobs = live["scrape_configs"]
    removed = jobs.pop(0)["job_name"]  # live lacks a job the repo renders -> a role run would ADD it
    jobs.append(
        {"job_name": "live_only_job", "static_configs": [{"targets": ["10.0.0.1:9100"]}]}
    )  # live has an extra job -> a role run would REMOVE it
    jobs[0]["scrape_interval"] = "999s"  # a changed job
    problems = parity.compare_prometheus(yaml.safe_dump(live))
    assert any("only in the repo" in p and removed in p for p in problems)
    assert any("only on the live VM" in p and "live_only_job" in p for p in problems)
    assert any("differs" in p and jobs[0]["job_name"] in p for p in problems)


def test_prometheus_alerting_block_drift_is_reported() -> None:
    live = _live_prometheus()
    live["alerting"]["alertmanagers"][0]["static_configs"][0]["targets"].append("203.0.113.9:9093")
    assert any("alerting" in p for p in parity.compare_prometheus(yaml.safe_dump(live)))


def _live_alertmanager_text() -> str:
    host = yaml.safe_load(H.MONITORING_HOST_VARS.read_text())
    ctx = H._context(H.ALERTMANAGER_ROLE / "defaults" / "main.yml", host)
    ctx["alertmanager_runtime_secondary_ntfy_topics"] = {"critical": "t0-c", "warning": "t0-w", "watchdog": "t0-h"}
    return H._environment(REPO_ROOT / "config" / "alertmanager").get_template("alertmanager.yml").render(**ctx)


def test_alertmanager_self_parity_passes_even_though_topics_live_outside_git() -> None:
    assert parity.compare_alertmanager(_live_alertmanager_text(), None) == []


def test_alertmanager_dropped_fanout_and_changed_route_are_reported() -> None:
    cfg = yaml.safe_load(_live_alertmanager_text())
    crit = next(r for r in cfg["receivers"] if r["name"] == "ntfy-critical")
    crit["webhook_configs"].pop()  # live lost the second ntfy webhook
    cfg["route"]["repeat_interval"] = "99h"
    problems = parity.compare_alertmanager(yaml.safe_dump(cfg), None)
    assert any("receiver `ntfy-critical` differs" in p for p in problems)
    assert any("`route` differs" in p for p in problems)


def test_alertmanager_args_drift_is_reported() -> None:
    env = 'ARGS="--config.file=/etc/alertmanager/alertmanager.yml --storage.path=/var/lib/prometheus/alertmanager --web.listen-address=0.0.0.0:9093"'
    problems = parity.compare_alertmanager(_live_alertmanager_text(), env)
    assert any("ARGS differ" in p for p in problems)  # the repo renders the cluster flags, this "live" file lacks them


def test_adopted_rule_files_must_match_byte_for_byte(tmp_path: Path) -> None:
    rules = tmp_path / "rules"
    rules.mkdir()
    shipped = yaml.safe_load(
        (REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/monitoring_vm/defaults/main.yml").read_text()
    )["monitoring_prometheus_adopted_rule_files"]
    for name in shipped:
        shutil.copy(REPO_ROOT / "config" / "prometheus" / "rules" / name, rules / name)
    assert parity.compare_rules(rules) == []
    (rules / shipped[0]).write_text("groups: []\n")
    (rules / shipped[1]).unlink()
    problems = parity.compare_rules(rules)
    assert any("differs" in p and shipped[0] in p for p in problems)
    assert any("missing on the live VM" in p and shipped[1] in p for p in problems)
