#!/usr/bin/env python3
"""Parity gate for the monitoring roles: does what the repo renders equal what runs on the monitoring VM?

Run it BEFORE any `monitoring_vm` / `alertmanager_runtime` role run. Exit 0 = a run would change nothing material in the checked files;
exit 1 = a run would overwrite live-only changes (the differences are printed).

    # 1. copy the live files into a directory (read-only; needs sudo on the VM):
    mkdir -p /tmp/live/rules
    ssh monitoring 'sudo cat /etc/prometheus/prometheus.yml'      > /tmp/live/prometheus.yml
    ssh monitoring 'sudo cat /etc/alertmanager/alertmanager.yml'  > /tmp/live/alertmanager.yml
    ssh monitoring 'sudo cat /etc/default/prometheus-alertmanager' > /tmp/live/prometheus-alertmanager
    ssh monitoring 'cd /etc/prometheus/rules && sudo tar c *.yml' | tar x -C /tmp/live/rules
    # 2. compare
    python3 scripts/monitoring_live_parity.py --live-dir /tmp/live

Checked: every scrape job and the alerting/global/rule_files blocks of prometheus.yml; the Alertmanager config (route, receivers, inhibit rules);
the Alertmanager ARGS file; and every adopted rule file byte-for-byte. Two inputs legitimately live outside git and are therefore taken from the
live file itself instead of the repo: the primary ntfy base URL (service topology) and the secondary ntfy topic names (anonymously readable, never committed).
Generated artifacts (https_tls_alerts.yml / https_tls_targets.yml, produced at live-apply time) and the hand-managed file_sd/public-critical-targets.yml are not checked.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import jinja2
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def _helpers():
    """Reuse the production-render helpers of the codification tests (same stubs, same filters)."""
    spec = importlib.util.spec_from_file_location(
        "codification", REPO_ROOT / "tests" / "test_monitoring_prometheus_codification.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(REPO_ROOT / "tests"))
    spec.loader.exec_module(module)
    return module


def _norm(obj: Any) -> Any:
    return json.loads(json.dumps(obj))


def compare_prometheus(live_text: str) -> list[str]:
    h = _helpers()
    repo, live = _norm(h.render_prometheus(use_host_vars=True)), yaml.safe_load(live_text)
    problems = [
        f"prometheus.yml block `{k}` differs"
        for k in ("global", "alerting", "rule_files", "remote_write")
        if repo.get(k) != live.get(k)
    ]
    rj = {j["job_name"]: j for j in repo.get("scrape_configs", [])}
    lj = {j["job_name"]: j for j in live.get("scrape_configs", [])}
    problems += [f"scrape job only on the live VM (a role run would remove it): {n}" for n in sorted(set(lj) - set(rj))]
    problems += [f"scrape job only in the repo (a role run would add it): {n}" for n in sorted(set(rj) - set(lj))]
    problems += [f"scrape job `{n}` differs" for n in sorted(set(rj) & set(lj)) if rj[n] != lj[n]]
    return problems


def _alertmanager_context(h, live_cfg: dict) -> dict:
    host = yaml.safe_load(h.MONITORING_HOST_VARS.read_text())
    ctx = h._context(h.ALERTMANAGER_ROLE / "defaults" / "main.yml", host)
    urls = [
        w["url"] for r in live_cfg["receivers"] if r["name"].startswith("ntfy-") for w in r.get("webhook_configs", [])
    ]
    primary = urls[0]  # the primary ntfy webhook is always the first one of a receiver
    ctx["alertmanager_runtime_ntfy_base_url"] = re.match(r"(https?://[^/]+)", primary).group(1)
    secondary = {}
    base2 = str(ctx.get("alertmanager_runtime_secondary_ntfy_base_url", ""))
    for r in live_cfg["receivers"]:
        for w in r.get("webhook_configs", []):
            if base2 and w["url"].startswith(base2 + "/"):
                secondary[r["name"].split("-", 1)[1]] = w["url"][len(base2) + 1 :].split("?", 1)[0]
    if base2:  # the inventory says the secondary ntfy must exist: a live receiver without it must show up as a difference, not be rendered away
        for r in live_cfg["receivers"]:
            if r["name"].startswith("ntfy-"):
                secondary.setdefault(r["name"].split("-", 1)[1], "MISSING-ON-LIVE")
    ctx["alertmanager_runtime_secondary_ntfy_topics"] = secondary
    ctx.setdefault("alertmanager_runtime_config_file", "/etc/alertmanager/alertmanager.yml")
    ctx.setdefault("alertmanager_runtime_data_dir", "/var/lib/prometheus/alertmanager")
    return ctx


def compare_alertmanager(live_text: str, live_env: str | None) -> list[str]:
    h = _helpers()
    live = yaml.safe_load(live_text)
    ctx = _alertmanager_context(h, live)
    repo = _norm(
        yaml.safe_load(
            h._environment(REPO_ROOT / "config" / "alertmanager").get_template("alertmanager.yml").render(**ctx)
        )
    )
    problems = [
        f"alertmanager.yml `{k}` differs"
        for k in sorted(set(repo) | set(live))
        if k != "receivers" and repo.get(k) != live.get(k)
    ]
    rr = {r["name"]: r for r in repo["receivers"]}
    lr = {r["name"]: r for r in live["receivers"]}
    problems += [f"receiver only on the live VM: {n}" for n in sorted(set(lr) - set(rr))]
    problems += [f"receiver only in the repo: {n}" for n in sorted(set(rr) - set(lr))]
    problems += [f"receiver `{n}` differs" for n in sorted(set(rr) & set(lr)) if rr[n] != lr[n]]
    if live_env is not None:
        env_t = (
            REPO_ROOT
            / "collections/ansible_collections/lv3/platform/roles/alertmanager_runtime/templates/prometheus-alertmanager.env.j2"
        ).read_text()
        out = (
            jinja2.Environment(undefined=jinja2.StrictUndefined, trim_blocks=True, keep_trailing_newline=True)
            .from_string(env_t)
            .render(**ctx)
        )
        if out.strip() != live_env.strip():
            problems.append(f"Alertmanager ARGS differ: repo `{out.strip()}` vs live `{live_env.strip()}`")
    return problems


def compare_rules(live_rules: Path) -> list[str]:
    defaults = yaml.safe_load(
        (REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/monitoring_vm/defaults/main.yml").read_text()
    )
    shipped = defaults["monitoring_prometheus_adopted_rule_files"]
    problems = []
    for name in shipped:
        live_file, repo_file = live_rules / name, REPO_ROOT / "config" / "prometheus" / "rules" / name
        if not live_file.exists():
            problems.append(f"adopted rule file missing on the live VM: {name}")
        elif live_file.read_bytes() != repo_file.read_bytes():
            problems.append(f"adopted rule file differs: {name}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live-dir", type=Path, required=True)
    args = ap.parse_args()
    d = args.live_dir
    problems: list[str] = []
    problems += compare_prometheus((d / "prometheus.yml").read_text())
    env_file = d / "prometheus-alertmanager"
    problems += compare_alertmanager(
        (d / "alertmanager.yml").read_text(), env_file.read_text() if env_file.exists() else None
    )
    problems += compare_rules(d / "rules")
    if problems:
        print("PARITY FAILED: a role run would change live state:")
        for p in problems:
            print("  -", p)
        return 1
    print("PARITY OK: the repo renders what runs on the monitoring VM (for the checked files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
