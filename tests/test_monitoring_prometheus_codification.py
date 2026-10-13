"""Regression tests for the codified Prometheus, Scanopy discovery, and Alertmanager state.

The monitoring VM was changed live (stale probe jobs removed, Scanopy file_sd jobs, ntfy-only Alertmanager routing,
OpenObserve remote_write, restored fleet exporters). A full monitoring converge re-renders prometheus.yml and
alertmanager.yml from the role templates, so these tests render the templates offline and pin the properties that must
survive a converge. Ansible-only filters are stubbed; nothing here contacts a host.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import jinja2
import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLES = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"
MONITORING_ROLE = ROLES / "monitoring_vm"
ALERTMANAGER_ROLE = ROLES / "alertmanager_runtime"
MONITORING_HOST_VARS = REPO_ROOT / "inventory" / "host_vars" / "monitoring.yml"
RULES_DIR = REPO_ROOT / "config" / "prometheus" / "rules"

# Values that production derives from the generated topology (hostvars lookups); pinned here for offline rendering.
TOPOLOGY_STUBS = {
    "monitoring_tempo_http_port": 3200,
    "monitoring_blackbox_exporter_port": 9115,
    "monitoring_postgres_audit_metrics_target": "10.10.10.50:12345",
}
ALERTMANAGER_STUBS = {
    "alertmanager_runtime_ntfy_base_url": "http://ntfy.internal.example:2586",
    "alertmanager_runtime_pgaudit_relay_webhook_url": "http://127.0.0.1:19094/alerts/pgaudit-unknown-role",
}


def _environment(search_path: Path) -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(search_path)),
        trim_blocks=True,
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )
    env.filters["bool"] = lambda value: value if isinstance(value, bool) else str(value).lower() in {"1", "true", "yes"}
    env.filters["dirname"] = lambda value: str(Path(value).parent)
    env.filters["to_json"] = lambda value, **_: json.dumps(value)
    env.filters["to_nice_json"] = lambda value, **_: json.dumps(value, indent=4, sort_keys=True)
    env.filters["to_nice_yaml"] = lambda value, indent=2, **_: yaml.safe_dump(
        value, default_flow_style=False, indent=indent, width=1000
    )
    return env


def _resolve(value: Any, context: dict[str, Any], env: jinja2.Environment) -> Any:
    if isinstance(value, str) and "{{" in value and "hostvars" not in value:
        try:
            return env.from_string(value).render(**context)
        except jinja2.TemplateError:
            return value
    if isinstance(value, list):
        return [_resolve(item, context, env) for item in value]
    if isinstance(value, dict):
        return {key: _resolve(item, context, env) for key, item in value.items()}
    return value


def _context(defaults_path: Path, overrides: dict[str, Any]) -> dict[str, Any]:
    env = _environment(defaults_path.parent)
    context: dict[str, Any] = yaml.safe_load(defaults_path.read_text())
    context.update(
        platform_identity={"config_prefix": "0mcp", "unix_prefix": "0mcp"},
        repo_shared_local_root="/controller/.local",
        monitoring_repo_root=str(REPO_ROOT),
        inventory_dir=str(REPO_ROOT / "inventory"),
    )
    context.update(overrides)
    for _ in range(6):
        context = {key: _resolve(value, context, env) for key, value in context.items()}
    context.update(TOPOLOGY_STUBS if "monitoring" in defaults_path.parts[-3] else ALERTMANAGER_STUBS)
    return context


def render_prometheus(use_host_vars: bool, **extra: Any) -> dict[str, Any]:
    overrides = yaml.safe_load(MONITORING_HOST_VARS.read_text()) if use_host_vars else {}
    overrides.update(extra)
    context = _context(MONITORING_ROLE / "defaults" / "main.yml", overrides)
    context["monitoring_health_probe_catalog"] = json.loads(
        (REPO_ROOT / "config" / "health-probe-catalog.json").read_text()
    )
    template = _environment(MONITORING_ROLE / "templates").get_template("prometheus.yml.j2")
    return yaml.safe_load(template.render(**context))


def render_alertmanager() -> tuple[str, dict[str, Any]]:
    context = _context(ALERTMANAGER_ROLE / "defaults" / "main.yml", yaml.safe_load(MONITORING_HOST_VARS.read_text()))
    template = _environment(REPO_ROOT / "config" / "alertmanager").get_template("alertmanager.yml")
    text = template.render(**context)
    return text, yaml.safe_load(text)


def jobs_by_name(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    names = [job["job_name"] for job in config["scrape_configs"]]
    assert len(names) == len(set(names)), "duplicate scrape job names make Prometheus reject the config"
    return {job["job_name"]: job for job in config["scrape_configs"]}


def test_production_render_restores_fleet_exporters_public_edge_and_remote_write() -> None:
    config = render_prometheus(use_host_vars=True)
    jobs = jobs_by_name(config)

    for restored in (
        "pve_0docker_via_tailscale",
        "cadvisor-runtime-general-lv3",
        "public-edge-critical",
    ):
        assert restored in jobs, f"{restored} must survive a converge"

    assert jobs["pve_0docker_via_tailscale"]["metrics_path"] == "/pve"
    assert jobs["public-edge-critical"]["file_sd_configs"][0]["files"] == [
        "/etc/prometheus/file_sd/public-critical-targets.yml"
    ]

    remote_write = config["remote_write"]
    assert len(remote_write) == 1
    assert remote_write[0]["url"].endswith("/api/default/prometheus/api/v1/write")
    assert remote_write[0]["basic_auth"]["password_file"] == (
        "/run/credentials/0mcp-prometheus.service/openobserve_password"
    )
    assert "password" not in remote_write[0]["basic_auth"]


def test_production_render_static_jobs_are_exactly_the_reviewed_set() -> None:
    config = render_prometheus(use_host_vars=True)
    static_jobs = {job["job_name"] for job in config["scrape_configs"] if "static_configs" in job}

    # Anything added here must be a reviewed, reachable target; node_exporter targets come from Scanopy file_sd.
    assert static_jobs == {
        "prometheus",
        "tempo",
        "otelcol-contrib",
        "loki-canary",
        "postgres-audit-alloy",
        "alertmanager-liveness",
        "alertmanager-readiness",
        "gitea-liveness",
        "grafana-liveness",
        "grafana-readiness",
        "openbao-liveness",
        "openbao-readiness",
        "pve_0docker_via_tailscale",
        "cadvisor-runtime-general-lv3",
    }
    assert not any(job["job_name"] == "node_exporter" and "static_configs" in job for job in config["scrape_configs"])


def test_production_render_keeps_only_reachable_catalog_probe_jobs() -> None:
    jobs = jobs_by_name(render_prometheus(use_host_vars=True))
    probe_jobs = {
        name
        for name, job in jobs.items()
        if job.get("params", {}).get("module") and name.endswith(("-liveness", "-readiness"))
    }

    assert probe_jobs == {
        "alertmanager-liveness",
        "alertmanager-readiness",
        "gitea-liveness",
        "grafana-liveness",
        "grafana-readiness",
        "openbao-liveness",
        "openbao-readiness",
    }


def test_production_render_uses_scanopy_file_sd_for_inventory_targets() -> None:
    jobs = jobs_by_name(render_prometheus(use_host_vars=True))

    node = jobs["node_exporter"]
    assert node["file_sd_configs"][0]["files"] == ["/etc/prometheus/file_sd/scanopy-node.json"]
    assert "static_configs" not in node
    assert {"source_labels": ["scanopy_job"], "regex": "(.+)", "target_label": "job"} in node["relabel_configs"]
    # Scanopy publishes every node exporter, hypervisors included, so nothing is dropped from its job.
    assert [rule for rule in node["relabel_configs"] if rule.get("action") == "drop"] == []

    guarded = jobs_by_name(
        render_prometheus(use_host_vars=True, monitoring_scanopy_sd_node_drop_address_regex="100\\.1\\.1\\.1:9100")
    )["node_exporter"]
    drop = next(rule for rule in guarded["relabel_configs"] if rule.get("action") == "drop")
    assert re.fullmatch(drop["regex"], "100.1.1.1:9100") and not re.fullmatch(drop["regex"], "203.0.113.3:9100")

    blackbox = jobs["scanopy-blackbox"]
    assert blackbox["file_sd_configs"][0]["files"] == ["/etc/prometheus/file_sd/scanopy-blackbox.json"]
    assert blackbox["relabel_configs"][-1] == {"target_label": "__address__", "replacement": "127.0.0.1:9115"}


def test_stale_catalog_targets_are_dropped_from_the_generated_blackbox_jobs() -> None:
    jobs = jobs_by_name(render_prometheus(use_host_vars=True))

    for job_name in ("slo-blackbox", "https-tls-blackbox"):
        first = jobs[job_name]["relabel_configs"][0]
        assert first["action"] == "drop"
        for stale in (
            "https://grafana.example.com",
            "http://10.10.10.20:8092/health",
            "https://100.64.0.1/health",
        ):
            assert re.fullmatch(first["regex"], stale), f"{stale} must be dropped"
        for live in ("https://ci.0exec.com/", "http://203.0.113.9:9100/"):
            assert not re.fullmatch(first["regex"], live), f"{live} must be kept"


def test_slo_probe_job_passes_the_public_hostname_and_display_url_to_blackbox() -> None:
    """Edge-published SLO targets connect to the edge's private address and need Host/SNI plus a readable instance."""
    for use_host_vars in (True, False):
        relabels = jobs_by_name(render_prometheus(use_host_vars=use_host_vars))["slo-blackbox"]["relabel_configs"]

        assert {"source_labels": ["probe_hostname"], "target_label": "__param_hostname"} in relabels
        assert {"source_labels": ["display_url"], "regex": "(.+)", "target_label": "instance"} in relabels
        assert relabels[-1] == {"target_label": "__address__", "replacement": "127.0.0.1:9115"}
        # instance defaults to the probe target first, display_url overrides it afterwards
        assert relabels.index({"source_labels": ["__param_target"], "target_label": "instance"}) < relabels.index(
            {"source_labels": ["display_url"], "regex": "(.+)", "target_label": "instance"}
        )


def test_default_render_keeps_legacy_behaviour_for_other_deployments() -> None:
    config = render_prometheus(use_host_vars=False)
    jobs = jobs_by_name(config)
    catalog = json.loads((REPO_ROOT / "config" / "health-probe-catalog.json").read_text())["services"]
    expected_probe_jobs = sum(
        1
        for service in catalog.values()
        for kind in ("liveness", "readiness")
        if service[kind]["kind"] in {"http", "tcp"}
    )

    assert "remote_write" not in config
    assert "node_exporter" not in jobs and "scanopy-blackbox" not in jobs and "public-edge-critical" not in jobs
    assert all("action" not in rule or rule["action"] != "drop" for rule in jobs["slo-blackbox"]["relabel_configs"])
    fixed_jobs = 7  # prometheus, tempo, otelcol-contrib, loki-canary, postgres audit, slo-blackbox, https-tls-blackbox
    assert len(jobs) == fixed_jobs + expected_probe_jobs


def test_prometheus_config_is_validated_and_reloaded_not_restarted() -> None:
    tasks = yaml.safe_load((MONITORING_ROLE / "tasks" / "tracing.yml").read_text())
    render = next(task for task in tasks if task.get("name") == "Render Prometheus configuration")
    handlers = yaml.safe_load((MONITORING_ROLE / "handlers" / "main.yml").read_text())
    reload_handler = next(handler for handler in handlers if handler["name"] == "Reload Prometheus configuration")

    assert render["ansible.builtin.template"]["validate"] == "{{ monitoring_prometheus_config_validate_command }}"
    assert render["notify"] == "Reload Prometheus configuration"
    assert (
        yaml.safe_load((MONITORING_ROLE / "defaults" / "main.yml").read_text())[
            "monitoring_prometheus_config_validate_command"
        ]
        == "promtool check config %s"
    )
    assert "--signal=HUP" in reload_handler["ansible.builtin.command"]["argv"]


def test_remote_write_credential_is_a_systemd_credential_reference_never_a_value() -> None:
    tasks = yaml.safe_load((MONITORING_ROLE / "tasks" / "tracing.yml").read_text())
    names = [task.get("name") for task in tasks]
    dropin = (MONITORING_ROLE / "templates" / "prometheus-credentials-dropin.conf.j2").read_text()
    host_vars = yaml.safe_load(MONITORING_HOST_VARS.read_text())

    assert "LoadCredentialEncrypted={{ credential.name }}:{{ credential.encrypted_file }}" in dropin
    assert names.index("Refuse to continue when an encrypted Prometheus credential is missing") < names.index(
        "Render Prometheus configuration"
    )
    assert host_vars["monitoring_prometheus_remote_write_credentials"] == [
        {"name": "openobserve_password", "encrypted_file": "/etc/credstore.encrypted/openobserve_password"}
    ]


def test_scanopy_tasks_keep_the_api_key_out_of_git_and_private() -> None:
    tasks = yaml.safe_load((MONITORING_ROLE / "tasks" / "scanopy_sd.yml").read_text())
    by_name = {task["name"]: task for task in tasks}
    install_key = by_name["Install the Scanopy API key from the controller-local secret file"]["ansible.builtin.copy"]
    install_key_task = by_name["Install the Scanopy API key from the controller-local secret file"]
    timer = by_name["Enable the Scanopy service-discovery timer"]["ansible.builtin.systemd"]
    directories = by_name["Ensure the Scanopy discovery directories exist"]["loop"]

    assert install_key["src"] == "{{ monitoring_scanopy_sd_api_key_local_file }}"
    assert install_key["mode"] == "0600" and install_key["owner"] == "root"
    assert install_key_task["no_log"] is True
    assert timer["enabled"] is True and "restarted" not in json.dumps(timer)
    assert {"path": "{{ monitoring_scanopy_sd_config_dir }}", "mode": "0700"} in directories
    # The key is referenced by path/variable only; no file in the role or inventory embeds one.
    for path in (MONITORING_ROLE / "files" / "scanopy-sd").iterdir():
        assert not re.search(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}", path.read_text())
    defaults = yaml.safe_load((MONITORING_ROLE / "defaults" / "main.yml").read_text())
    assert defaults["monitoring_scanopy_sd_enabled"] is False
    assert "{{ repo_shared_local_root }}" in defaults["monitoring_scanopy_sd_api_key_local_file"]


def test_scanopy_systemd_units_are_hardened_and_timer_is_five_minutes() -> None:
    context = _context(MONITORING_ROLE / "defaults" / "main.yml", yaml.safe_load(MONITORING_HOST_VARS.read_text()))
    env = _environment(MONITORING_ROLE / "templates")
    service = env.get_template("scanopy-sd.service.j2").render(**context)
    timer = env.get_template("scanopy-sd.timer.j2").render(**context)

    for hardening in ("NoNewPrivileges=yes", "ProtectSystem=strict", "PrivateTmp=yes", "ProtectHome=yes"):
        assert hardening in service
    assert "ReadWritePaths=/etc/prometheus/file_sd /var/lib/scanopy-sd /var/lib/prometheus/node-exporter" in service
    assert "ReadOnlyPaths=/etc/scanopy-sd /opt/scanopy-sd" in service
    assert "OnUnitActiveSec=5min" in timer
    extra = json.loads(env.get_template("scanopy-sd-extra-endpoints.json.j2").render(**context))
    assert extra[0]["service"] == "woodpecker"


def test_discovery_and_watchdog_rules_are_shipped_from_the_repo() -> None:
    inventory = yaml.safe_load((RULES_DIR / "inventory.yml").read_text())
    watchdog = yaml.safe_load((RULES_DIR / "zz-alertmanager-watchdog.yml").read_text())
    inventory_alerts = {rule["alert"] for group in inventory["groups"] for rule in group["rules"]}
    watchdog_rules = [rule for group in watchdog["groups"] for rule in group["rules"]]

    assert inventory_alerts == {
        "ScanopySDStale",
        "ScanopySDMetricsAbsent",
        "ScanopyDiscoveryStale",
        "TargetCountDrop",
        "NodeExporterMissing",
        "ScanopyEndpointDown",
        "ScanopyRetagStale",
        "ScanopyRetagMetricsAbsent",
        "ScanopyDiscoverStale",
        "ScanopyDiscoverMetricsAbsent",
        "ScanopyDiscoveryOverdue",
        "ScanopyDaemonDown",
        "ScanopyGuestWithoutDaemon",
        "ScanopyOnboardStale",
        "ScanopyOnboardMetricsAbsent",
        "ScanopyBackupStale",
        "ScanopyBackupMetricsAbsent",
    }
    assert [rule["alert"] for rule in watchdog_rules] == ["Watchdog"]
    assert watchdog_rules[0]["expr"] == "vector(1)"

    main_tasks = yaml.safe_load((MONITORING_ROLE / "tasks" / "main.yml").read_text())
    scanopy_tasks = yaml.safe_load((MONITORING_ROLE / "tasks" / "scanopy_sd.yml").read_text())
    watchdog_copy = next(
        task for task in main_tasks if task.get("name") == "Copy the Alertmanager Watchdog heartbeat rule"
    )
    inventory_copy = next(
        task for task in scanopy_tasks if task.get("name") == "Copy the Scanopy inventory Prometheus rules"
    )
    assert watchdog_copy["notify"] == inventory_copy["notify"] == "Reload Prometheus configuration"


def test_alertmanager_routes_to_ntfy_only_with_credentials_by_file() -> None:
    text, config = render_alertmanager()
    receivers = {receiver["name"]: receiver for receiver in config["receivers"]}
    routes = config["route"]["routes"]

    assert set(receivers) == {
        "null",
        "pgaudit-unknown-role-relay",
        "ntfy-critical",
        "ntfy-warning",
        "ntfy-watchdog",
        "fleet-triage",
    }
    assert "slack_configs" not in text and "mattermost" not in text.lower()
    for name in ("ntfy-critical", "ntfy-warning", "ntfy-watchdog"):
        basic_auth = receivers[name]["webhook_configs"][0]["http_config"]["basic_auth"]
        assert basic_auth == {"username": "alertmanager-notify", "password_file": "/etc/alertmanager/ntfy-password"}
        assert "password:" not in text.replace("password_file:", "")
    assert "/platform-monitoring-critical?" in receivers["ntfy-critical"]["webhook_configs"][0]["url"]
    assert "&p=5&" in receivers["ntfy-critical"]["webhook_configs"][0]["url"]
    assert "/platform-monitoring-warning?" in receivers["ntfy-warning"]["webhook_configs"][0]["url"]
    assert "/platform-monitoring-watchdog?" in receivers["ntfy-watchdog"]["webhook_configs"][0]["url"]
    assert "&p=1&" in receivers["ntfy-watchdog"]["webhook_configs"][0]["url"]

    by_receiver = {route["receiver"]: route for route in routes if "receiver" in route}
    assert by_receiver["ntfy-watchdog"]["repeat_interval"] == "6h"
    assert by_receiver["null"]["matchers"] == ['severity="info"']
    critical = next(route for route in routes if route["matchers"] == ['severity="critical"'])
    warning = next(route for route in routes if route["matchers"] == ['severity="warning"'])
    assert critical["receiver"] == "ntfy-critical" and critical["repeat_interval"] == "4h"
    assert warning["receiver"] == "ntfy-warning" and warning["group_wait"] == "5m"
    assert warning["group_interval"] == "1h" and warning["repeat_interval"] == "12h"
    assert len(config["inhibit_rules"]) == 4
    assert any(route.get("receiver") == "pgaudit-unknown-role-relay" for route in routes)


def test_fleet_triage_receiver_is_additive_shadow_and_credentialed_by_file() -> None:
    text, config = render_alertmanager()
    routes = config["route"]["routes"]
    triage_route = next(route for route in routes if route.get("receiver") == "fleet-triage")
    receiver = next(item for item in config["receivers"] if item["name"] == "fleet-triage")
    hook = receiver["webhook_configs"][0]

    # Additive: continue true, and it sits BEFORE the first route that can deliver to ntfy.
    assert triage_route["continue"] is True
    assert triage_route["matchers"] == ['severity=~"critical|warning"']
    first_ntfy = next(
        i
        for i, route in enumerate(routes)
        if route.get("receiver", "").startswith("ntfy-") and route.get("receiver") != "ntfy-watchdog"
    )
    assert routes.index(triage_route) < first_ntfy
    assert routes.index(triage_route) > next(
        i for i, route in enumerate(routes) if route.get("receiver") == "pgaudit-unknown-role-relay"
    )
    # Firing only, bounded, short timeout; token by file, never rendered.
    assert hook["send_resolved"] is False and hook["max_alerts"] == 20 and hook["timeout"] == "10s"
    assert hook["url"].endswith("/webhook/alertmanager?source=0mcp")
    assert hook["http_config"]["authorization"] == {
        "type": "Bearer",
        "credentials_file": "/etc/alertmanager/triage-token",
    }
    assert "credentials:" not in text and "bearer_token:" not in text
    # No triage receiver unless the URL is configured (staging and other converges stay unchanged).
    context = _context(ALERTMANAGER_ROLE / "defaults" / "main.yml", {})
    context["alertmanager_runtime_triage_webhook_url"] = ""
    disabled = _environment(REPO_ROOT / "config" / "alertmanager").get_template("alertmanager.yml").render(**context)
    assert "fleet-triage" not in disabled


def test_alertmanager_role_installs_a_prometheus_readable_password_and_validates_config() -> None:
    tasks = yaml.safe_load((ALERTMANAGER_ROLE / "tasks" / "main.yml").read_text())
    persist = next(task for task in tasks if task.get("name") == "Persist Alertmanager ntfy password")
    render = next(task for task in tasks if task.get("name") == "Render Alertmanager configuration")
    copy = persist["ansible.builtin.copy"]
    text = (ALERTMANAGER_ROLE / "tasks" / "main.yml").read_text()

    assert (copy["owner"], copy["group"], copy["mode"]) == ("root", "prometheus", "0640")
    assert persist["no_log"] is True and persist["notify"] == "Reload Alertmanager"
    assert render["ansible.builtin.template"]["validate"] == "amtool check-config %s"
    assert "mattermost" not in text.lower()


def test_no_secret_values_are_committed_with_the_monitoring_codification() -> None:
    paths = [
        MONITORING_HOST_VARS,
        MONITORING_ROLE / "defaults" / "main.yml",
        ALERTMANAGER_ROLE / "defaults" / "main.yml",
        REPO_ROOT / "config" / "alertmanager" / "alertmanager.yml",
    ]
    for path in paths:
        text = path.read_text()
        assert not re.search(r"(?im)^\s*(password|bearer_token|api_key|token|secret|credentials)\s*:\s*\S", text), path
        assert not re.search(r"\$2[aby]\$\d\d\$", text), f"bcrypt hash in {path}"


def test_scanopy_api_key_is_never_replaced_by_an_empty_controller_file() -> None:
    tasks = yaml.safe_load((MONITORING_ROLE / "tasks" / "scanopy_sd.yml").read_text())
    by_name = {task["name"]: task for task in tasks}
    usable = by_name["Decide whether the controller-local Scanopy API key is usable"]["ansible.builtin.set_fact"]
    install = by_name["Install the Scanopy API key from the controller-local secret file"]
    keep = by_name["Keep an existing host-provisioned Scanopy API key private"]
    refuse = by_name["Refuse to run discovery without any non-empty Scanopy API key"]

    assert "stat.size > 0" in usable["monitoring_scanopy_sd_api_key_local_usable"]
    assert install["when"] == "monitoring_scanopy_sd_api_key_local_usable | bool"
    assert keep["when"] == "not (monitoring_scanopy_sd_api_key_local_usable | bool)"
    assert "monitoring_scanopy_sd_api_key_remote_stat.stat.size > 0" in refuse["ansible.builtin.assert"]["that"][0]
    names = [task["name"] for task in tasks]
    assert names.index(refuse["name"]) < names.index(install["name"])


def test_nginx_guest_firewall_keeps_the_monitoring_node_exporter_rule() -> None:
    host_vars = yaml.safe_load((REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml").read_text())
    rules = host_vars["network_policy"]["guests"]["nginx"]["allowed_inbound"]
    monitoring = [rule for rule in rules if rule["source"] == "monitoring"]

    assert len(monitoring) == 1
    assert monitoring[0]["protocol"] == "tcp" and monitoring[0]["ports"] == [9100]


def test_scanopy_retag_is_off_by_default_and_on_for_the_monitoring_host() -> None:
    defaults = yaml.safe_load((MONITORING_ROLE / "defaults" / "main.yml").read_text())
    host_vars = yaml.safe_load(MONITORING_HOST_VARS.read_text())
    main_tasks = yaml.safe_load((MONITORING_ROLE / "tasks" / "main.yml").read_text())
    include = next(
        task for task in main_tasks if task.get("name") == "Install the Scanopy Docker bridge subnet tagging job"
    )

    assert defaults["monitoring_scanopy_retag_enabled"] is False
    assert host_vars["monitoring_scanopy_retag_enabled"] is True
    assert include["ansible.builtin.include_tasks"] == "scanopy_retag.yml"
    assert include["when"] == "monitoring_scanopy_retag_enabled | bool"
    # The retag key may assign tags, so it must not be the Viewer key that scanopy-sd uses.
    assert (
        defaults["monitoring_scanopy_retag_api_key_local_file"] != defaults["monitoring_scanopy_sd_api_key_local_file"]
    )
    assert "{{ repo_shared_local_root }}" in defaults["monitoring_scanopy_retag_api_key_local_file"]
    specs = yaml.safe_load((MONITORING_ROLE / "meta" / "argument_specs.yml").read_text())
    documented = specs["argument_specs"]["main"]["options"]
    for name in (
        "monitoring_scanopy_retag_enabled",
        "monitoring_scanopy_retag_api_key_local_file",
        "monitoring_scanopy_retag_interval",
        "monitoring_scanopy_retag_environment",
    ):
        assert name in documented


def test_scanopy_retag_tasks_keep_the_api_key_out_of_git_and_never_install_an_empty_one() -> None:
    tasks = yaml.safe_load((MONITORING_ROLE / "tasks" / "scanopy_retag.yml").read_text())
    by_name = {task["name"]: task for task in tasks}
    usable = by_name["Decide whether the controller-local Scanopy retag API key is usable"]["ansible.builtin.set_fact"]
    install = by_name["Install the Scanopy retag API key from the controller-local secret file"]
    keep = by_name["Keep an existing host-provisioned Scanopy retag API key private"]
    refuse = by_name["Refuse to run the retag job without any non-empty Scanopy API key"]
    timer = by_name["Enable the Scanopy retag timer"]["ansible.builtin.systemd"]
    directories = by_name["Ensure the Scanopy retag directories exist"]["loop"]

    assert "stat.size > 0" in usable["monitoring_scanopy_retag_api_key_local_usable"]
    assert install["no_log"] is True and install["when"] == "monitoring_scanopy_retag_api_key_local_usable | bool"
    assert install["ansible.builtin.copy"]["src"] == "{{ monitoring_scanopy_retag_api_key_local_file }}"
    assert install["ansible.builtin.copy"]["mode"] == "0600" and install["ansible.builtin.copy"]["owner"] == "root"
    assert keep["when"] == "not (monitoring_scanopy_retag_api_key_local_usable | bool)"
    assert "monitoring_scanopy_retag_api_key_remote_stat.stat.size > 0" in refuse["ansible.builtin.assert"]["that"][0]
    assert {"path": "{{ monitoring_scanopy_retag_config_dir }}", "mode": "0700"} in directories
    assert timer["enabled"] is True and "restarted" not in json.dumps(timer)
    names = [task["name"] for task in tasks]
    assert names.index(refuse["name"]) < names.index(install["name"])
    for path in (MONITORING_ROLE / "files" / "scanopy-retag").iterdir():
        assert not re.search(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}", path.read_text())


def test_scanopy_retag_units_are_hardened_and_timer_is_fifteen_minutes() -> None:
    context = _context(MONITORING_ROLE / "defaults" / "main.yml", yaml.safe_load(MONITORING_HOST_VARS.read_text()))
    env = _environment(MONITORING_ROLE / "templates")
    service = env.get_template("scanopy-retag.service.j2").render(**context)
    timer = env.get_template("scanopy-retag.timer.j2").render(**context)

    for hardening in ("NoNewPrivileges=yes", "ProtectSystem=strict", "PrivateTmp=yes", "ProtectHome=yes"):
        assert hardening in service
    assert "ReadWritePaths=/var/lib/prometheus/node-exporter\n" in service
    assert "ReadOnlyPaths=/etc/scanopy-retag /opt/scanopy-retag" in service
    assert "ExecStart=/usr/bin/python3 /opt/scanopy-retag/scanopy_retag.py" in service
    assert "OnUnitActiveSec=15min" in timer


def test_scanopy_retag_alerts_cover_failure_and_missing_metrics() -> None:
    inventory = yaml.safe_load((RULES_DIR / "inventory.yml").read_text())
    group = next(group for group in inventory["groups"] if group["name"] == "scanopy_retag")
    rules = {rule["alert"]: rule for rule in group["rules"]}

    assert set(rules) == {"ScanopyRetagStale", "ScanopyRetagMetricsAbsent"}
    assert rules["ScanopyRetagStale"]["expr"] == "(time() - scanopy_retag_last_success_timestamp_seconds) > 3600"
    assert rules["ScanopyRetagMetricsAbsent"]["expr"] == "absent(scanopy_retag_last_success_timestamp_seconds)"
    for rule in rules.values():
        assert rule["labels"] == {"severity": "warning", "service": "inventory"}


def test_scanopy_discover_is_off_by_default_and_schedules_every_target_once_per_slot() -> None:
    defaults = yaml.safe_load((MONITORING_ROLE / "defaults" / "main.yml").read_text())
    host_vars = yaml.safe_load(MONITORING_HOST_VARS.read_text())
    main_tasks = yaml.safe_load((MONITORING_ROLE / "tasks" / "main.yml").read_text())
    include = next(task for task in main_tasks if task.get("name") == "Install the external Scanopy discovery trigger")
    schedule = host_vars["monitoring_scanopy_discover_schedule"]
    times = list(schedule.values())

    assert (
        defaults["monitoring_scanopy_discover_enabled"] is False
        and defaults["monitoring_scanopy_discover_schedule"] == {}
    )
    assert host_vars["monitoring_scanopy_discover_enabled"] is True
    assert include["ansible.builtin.include_tasks"] == "scanopy_discover.yml"
    assert include["when"] == "monitoring_scanopy_discover_enabled | bool"
    # One start per 15-minute run and every slot is a distinct quarter hour, so no two hosts are ever started together.
    assert (
        len(times) == len(set(times)) == 41
    )  # every Scanopy daemon: 16 Docker VMs, 4 hypervisor daemons, the rollout guests and the VMs without Docker
    assert all(re.fullmatch(r"([01][0-9]|2[0-3]):[0-5][0-9]", value) for value in times)
    assert all(int(value.split(":")[1]) % 15 == 0 for value in times)
    # The large Docker host keeps a 45-minute window to itself.
    big = schedule["vm-0docker-ubuntu-24-04"]
    next_after = sorted(value for value in times if value > big)[0]
    assert (int(next_after[:2]) * 60 + int(next_after[3:])) - (int(big[:2]) * 60 + int(big[3:])) >= 45
    # It reuses the key installed by the retag tasks and never installs one itself.
    assert defaults["monitoring_scanopy_discover_api_key_file"] == "{{ monitoring_scanopy_retag_api_key_file }}"
    tasks = yaml.safe_load((MONITORING_ROLE / "tasks" / "scanopy_discover.yml").read_text())
    assert not any("api_key_local" in json.dumps(task) for task in tasks)
    refuse = next(
        task for task in tasks if task["name"] == "Refuse to run the discover job without a non-empty Scanopy API key"
    )
    assert "monitoring_scanopy_discover_api_key_stat.stat.size > 0" in refuse["ansible.builtin.assert"]["that"]
    specs = yaml.safe_load((MONITORING_ROLE / "meta" / "argument_specs.yml").read_text())["argument_specs"]["main"][
        "options"
    ]
    for name in (
        "monitoring_scanopy_discover_enabled",
        "monitoring_scanopy_discover_schedule",
        "monitoring_scanopy_discover_on_calendar",
        "monitoring_scanopy_discover_environment",
    ):
        assert name in specs


def test_scanopy_discover_units_are_hardened_and_the_schedule_renders_to_json() -> None:
    context = _context(MONITORING_ROLE / "defaults" / "main.yml", yaml.safe_load(MONITORING_HOST_VARS.read_text()))
    env = _environment(MONITORING_ROLE / "templates")
    service = env.get_template("scanopy-discover.service.j2").render(**context)
    timer = env.get_template("scanopy-discover.timer.j2").render(**context)
    rendered = json.loads(env.get_template("scanopy-discover-schedule.json.j2").render(**context))

    for hardening in ("NoNewPrivileges=yes", "ProtectSystem=strict", "PrivateTmp=yes", "ProtectHome=yes"):
        assert hardening in service
    assert "ReadWritePaths=/var/lib/prometheus/node-exporter\n" in service
    assert "ReadOnlyPaths=/etc/scanopy-retag /opt/scanopy-discover" in service
    assert "ExecStart=/usr/bin/python3 /opt/scanopy-discover/scanopy_discover.py" in service
    assert "OnCalendar=*:02/15" in timer
    assert rendered == yaml.safe_load(MONITORING_HOST_VARS.read_text())["monitoring_scanopy_discover_schedule"]


def test_scanopy_discover_alerts_cover_failure_missing_metrics_and_overdue_hosts() -> None:
    inventory = yaml.safe_load((RULES_DIR / "inventory.yml").read_text())
    group = next(group for group in inventory["groups"] if group["name"] == "scanopy_discover")
    rules = {rule["alert"]: rule for rule in group["rules"]}

    assert set(rules) == {
        "ScanopyDiscoverStale",
        "ScanopyDiscoverMetricsAbsent",
        "ScanopyDiscoveryOverdue",
        "ScanopyDaemonDown",
    }
    # A healthy daemon polls about every 30 s; 10 minutes of silence for 5 minutes is a dead daemon, not a slow poll.
    assert rules["ScanopyDaemonDown"]["expr"] == "scanopy_daemon_last_seen_age_seconds > 600"
    assert rules["ScanopyDaemonDown"]["for"] == "5m"
    assert rules["ScanopyDiscoverStale"]["expr"] == "(time() - scanopy_discover_last_success_timestamp_seconds) > 3600"
    assert rules["ScanopyDiscoverMetricsAbsent"]["expr"] == "absent(scanopy_discover_last_success_timestamp_seconds)"
    assert rules["ScanopyDiscoveryOverdue"]["expr"] == "scanopy_discover_oldest_last_run_age_seconds > 36 * 3600"
    for rule in rules.values():
        assert rule["labels"] == {"severity": "warning", "service": "inventory"}


def test_scanopy_onboard_is_off_by_default_and_wired_into_the_role_and_monitoring_host() -> None:
    defaults = yaml.safe_load((MONITORING_ROLE / "defaults" / "main.yml").read_text())
    host_vars = yaml.safe_load(MONITORING_HOST_VARS.read_text())
    main_tasks = yaml.safe_load((MONITORING_ROLE / "tasks" / "main.yml").read_text())
    include = next(
        task
        for task in main_tasks
        if task.get("name") == "Install the automatic Scanopy onboarding job for new Proxmox guests"
    )
    fleets = {fleet["name"]: fleet for fleet in host_vars["monitoring_scanopy_onboard_fleets"]}

    assert (
        defaults["monitoring_scanopy_onboard_enabled"] is False and defaults["monitoring_scanopy_onboard_fleets"] == []
    )
    assert host_vars["monitoring_scanopy_onboard_enabled"] is True
    assert include["ansible.builtin.include_tasks"] == "scanopy_onboard.yml"
    assert include["when"] == "monitoring_scanopy_onboard_enabled | bool"
    # One entry per hypervisor, each with the relay its guests poll (same relays as the retag/discover documentation).
    assert set(fleets) == {"0docker", "0mcp", "0own", "pve01"}
    assert {name: fleet["relay_url"] for name, fleet in fleets.items()} == {
        "0docker": "http://10.10.10.1:60072",
        "0mcp": "http://10.10.10.1:60072",
        "0own": "http://10.60.10.1:60072",
        "pve01": "http://10.50.0.1:60072",
    }
    # The API key is the one the retag tasks install; this role never installs or replaces one.
    assert defaults["monitoring_scanopy_onboard_api_key_file"] == "{{ monitoring_scanopy_retag_api_key_file }}"
    tasks = yaml.safe_load((MONITORING_ROLE / "tasks" / "scanopy_onboard.yml").read_text())
    assert not any("api_key_local" in json.dumps(task) for task in tasks)
    keygen = next(
        task for task in tasks if task["name"] == "Generate the dedicated onboarding SSH key (only when missing)"
    )
    assert keygen["ansible.builtin.command"]["creates"] == "{{ monitoring_scanopy_onboard_ssh_key_file }}"
    specs = yaml.safe_load((MONITORING_ROLE / "meta" / "argument_specs.yml").read_text())["argument_specs"]["main"][
        "options"
    ]
    for name in (
        "monitoring_scanopy_onboard_enabled",
        "monitoring_scanopy_onboard_fleets",
        "monitoring_scanopy_onboard_site_id",
        "monitoring_scanopy_onboard_docker_credential_id",
        "monitoring_scanopy_onboard_exclude",
        "monitoring_scanopy_onboard_on_calendar",
        "monitoring_scanopy_onboard_environment",
    ):
        assert name in specs


def test_scanopy_onboard_units_are_hardened_and_the_fleet_config_renders_to_json() -> None:
    context = _context(MONITORING_ROLE / "defaults" / "main.yml", yaml.safe_load(MONITORING_HOST_VARS.read_text()))
    env = _environment(MONITORING_ROLE / "templates")
    service = env.get_template("scanopy-onboard.service.j2").render(**context)
    timer = env.get_template("scanopy-onboard.timer.j2").render(**context)
    rendered = json.loads(env.get_template("scanopy-onboard-fleets.json.j2").render(**context))

    for hardening in ("NoNewPrivileges=yes", "ProtectSystem=strict", "PrivateTmp=yes", "ProtectHome=yes"):
        assert hardening in service
    assert "ReadWritePaths=/var/lib/prometheus/node-exporter /var/lib/scanopy-onboard /etc/scanopy-onboard\n" in service
    assert "ExecStart=/usr/bin/python3 /opt/scanopy-onboard/scanopy_onboard.py" in service
    assert "TimeoutStartSec=1500" in service  # two installs of up to ~10 minutes each
    assert "OnCalendar=*:07/15" in timer  # between the discovery trigger runs (:02/:17/:32/:47)
    host_vars = yaml.safe_load(MONITORING_HOST_VARS.read_text())
    assert rendered["fleets"] == host_vars["monitoring_scanopy_onboard_fleets"]
    assert rendered["site_id"] == host_vars["monitoring_scanopy_onboard_site_id"]
    assert rendered["docker_credential_id"] == host_vars["monitoring_scanopy_onboard_docker_credential_id"]


def test_scanopy_onboard_alerts_cover_uncovered_guests_stale_runs_and_missing_metrics() -> None:
    inventory = yaml.safe_load((RULES_DIR / "inventory.yml").read_text())
    group = next(group for group in inventory["groups"] if group["name"] == "scanopy_onboard")
    rules = {rule["alert"]: rule for rule in group["rules"]}

    assert set(rules) == {"ScanopyGuestWithoutDaemon", "ScanopyOnboardStale", "ScanopyOnboardMetricsAbsent"}
    assert (
        rules["ScanopyGuestWithoutDaemon"]["expr"]
        == "(scanopy_onboard_guests_uncovered + scanopy_onboard_guests_unmanageable) > 0"
    )
    assert rules["ScanopyGuestWithoutDaemon"]["for"] == "3h"
    assert rules["ScanopyOnboardStale"]["expr"] == "(time() - scanopy_onboard_last_success_timestamp_seconds) > 7200"
    assert rules["ScanopyOnboardMetricsAbsent"]["expr"] == "absent(scanopy_onboard_last_success_timestamp_seconds)"
    for rule in rules.values():
        assert rule["labels"] == {"severity": "warning", "service": "inventory"}


def test_scanopy_backup_is_off_by_default_hardened_and_alerted() -> None:
    defaults = yaml.safe_load((MONITORING_ROLE / "defaults" / "main.yml").read_text())
    host_vars = yaml.safe_load(MONITORING_HOST_VARS.read_text())
    main_tasks = yaml.safe_load((MONITORING_ROLE / "tasks" / "main.yml").read_text())
    include = next(task for task in main_tasks if task.get("name") == "Install the nightly Scanopy database backup pull")
    tasks = yaml.safe_load((MONITORING_ROLE / "tasks" / "scanopy_backup.yml").read_text())
    specs = yaml.safe_load((MONITORING_ROLE / "meta" / "argument_specs.yml").read_text())["argument_specs"]["main"]["options"]
    context = _context(MONITORING_ROLE / "defaults" / "main.yml", host_vars)
    env = _environment(MONITORING_ROLE / "templates")
    service = env.get_template("scanopy-backup.service.j2").render(**context)
    timer = env.get_template("scanopy-backup.timer.j2").render(**context)
    inventory = yaml.safe_load((RULES_DIR / "inventory.yml").read_text())
    group = next(group for group in inventory["groups"] if group["name"] == "scanopy_backup")
    rules = {rule["alert"]: rule for rule in group["rules"]}

    assert defaults["monitoring_scanopy_backup_enabled"] is False and host_vars["monitoring_scanopy_backup_enabled"] is True
    assert include["ansible.builtin.include_tasks"] == "scanopy_backup.yml"
    assert include["when"] == "monitoring_scanopy_backup_enabled | bool"
    keygen = next(task for task in tasks if task["name"] == "Generate the dedicated backup SSH key (only when missing)")
    assert keygen["ansible.builtin.command"]["creates"] == "{{ monitoring_scanopy_backup_ssh_key_file }}"
    private_dirs = [item for task in tasks if "ansible.builtin.file" in task for item in task["loop"] if item["path"].endswith("backup_dir }}")]
    assert private_dirs and all(item["mode"] == "0700" for item in private_dirs)  # dumps hold credential material
    for name in ("monitoring_scanopy_backup_enabled", "monitoring_scanopy_backup_on_calendar", "monitoring_scanopy_backup_environment"):
        assert name in specs
    for hardening in ("NoNewPrivileges=yes", "ProtectSystem=strict", "PrivateTmp=yes", "ProtectHome=yes", "UMask=0077"):
        assert hardening in service
    assert "ReadWritePaths=/var/backups/scanopy /var/lib/prometheus/node-exporter /etc/scanopy-backup\n" in service
    assert "OnCalendar=*-*-* 03:20:00 UTC" in timer
    assert set(rules) == {"ScanopyBackupStale", "ScanopyBackupMetricsAbsent"}
    assert rules["ScanopyBackupStale"]["expr"] == "(time() - scanopy_backup_last_success_timestamp_seconds) > 36 * 3600"
    assert rules["ScanopyBackupMetricsAbsent"]["expr"] == "absent(scanopy_backup_last_success_timestamp_seconds)"


def test_guests_scraped_for_node_metrics_allow_the_monitoring_guest_on_9100() -> None:
    # Guest nftables is rendered from this policy: a scrape rule added only by hand (or only to the Proxmox firewall) is
    # removed by the next guest-firewall render, which silently turns the target down (NodeExporterMissing).
    policy = yaml.safe_load((REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml").read_text())["network_policy"][
        "guests"
    ]

    for guest in ("docker-build", "runtime-control"):
        rules = [
            rule
            for rule in policy[guest]["allowed_inbound"]
            if rule.get("source") == "monitoring"
            and rule.get("protocol") == "tcp"
            and 9100 in (rule.get("ports") or [])
        ]
        assert rules, f"{guest} must allow monitoring -> tcp 9100 in the canonical network policy"
        assert all(rule.get("forward") is False for rule in rules)


def test_scanopy_relay_is_open_to_the_whole_guest_lan_in_the_canonical_host_firewall_policy() -> None:
    # The 0mcp hypervisor only lets a guest reach the Scanopy relay (10.10.10.1:60072) through its host firewall. The
    # onboarding job installs daemons in guests nobody listed beforehand, so the rule covers the guest LAN instead of a
    # per-guest allowlist; losing it would cut every 0mcp daemon off the server at once.
    policy_path = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"
    policy_text = policy_path.read_text()
    if "# serverclaw-publication-profile: generic" in policy_text:
        pytest.skip("the generic public template intentionally omits deployment-specific firewall exceptions")
    policy = yaml.safe_load(policy_text)
    relay = [
        rule
        for rule in policy["proxmox_host_additional_tcp_rules"]
        if str(rule.get("port")) == "60072" and rule.get("destination") == "10.10.10.1"
    ]
    assert [(rule["source"], rule.get("interface")) for rule in relay] == [("10.10.10.0/24", "vmbr20")]
    guests = {guest["ipv4"] for guest in policy["proxmox_guests"] if guest.get("ipv4")}
    assert guests and all(ip.startswith("10.10.10.") for ip in guests)  # every guest sits inside the allowed subnet
