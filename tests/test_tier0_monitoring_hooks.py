"""Optional tier-0 hooks in the monitoring roles (Alertmanager HA mesh, ntfy fan-out, extra Prometheus targets/jobs).

Safety property: with the hooks at their defaults (off) the rendered files are identical to what the roles rendered before the hooks
existed. With the hooks on, the output matches the configuration applied live on monitoring-lv3 on 2026-10-14.
"""

import subprocess
from pathlib import Path

import jinja2
import yaml

REPO = Path(__file__).resolve().parents[1]
ROLES = REPO / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"
ENV_TEMPLATE = ROLES / "alertmanager_runtime" / "templates" / "prometheus-alertmanager.env.j2"
AM_CONFIG = REPO / "config" / "alertmanager" / "alertmanager.yml"
INVENTORY = REPO / "inventory" / "host_vars" / "monitoring.yml"
BASE_REV = "origin/main"


def render(text: str, **variables) -> str:
    env = jinja2.Environment(
        undefined=jinja2.ChainableUndefined, trim_blocks=True, lstrip_blocks=False, keep_trailing_newline=True
    )
    env.filters["from_yaml"] = yaml.safe_load
    env.filters["to_nice_yaml"] = lambda v, indent=2: yaml.safe_dump(v, indent=indent, sort_keys=False)
    env.filters["indent"] = lambda t, width=4, first=False: "\n".join(
        (" " * width if (i or first) and line else "") + line for i, line in enumerate(str(t).splitlines())
    )
    return env.from_string(text).render(**variables)


def git_show(path: Path, rev: str = BASE_REV) -> str | None:
    try:
        return subprocess.run(
            ["git", "show", f"{rev}:{path.relative_to(REPO)}"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout
    except subprocess.CalledProcessError:
        return None


BASE_AM = {
    "alertmanager_runtime_config_file": "/etc/alertmanager/alertmanager.yml",
    "alertmanager_runtime_data_dir": "/var/lib/prometheus/alertmanager",
    "alertmanager_runtime_listen_address": "0.0.0.0:9093",
    "alertmanager_runtime_ntfy_base_url": "http://ntfy.example.com:2586",
    "alertmanager_runtime_ntfy_topics": {"critical": "c", "warning": "w", "watchdog": "h"},
    "alertmanager_runtime_ntfy_query": "tpl=yes",
    "alertmanager_runtime_ntfy_max_alerts": 5,
    "alertmanager_runtime_ntfy_username": "alertmanager-notify",
    "alertmanager_runtime_ntfy_password_file": "/etc/alertmanager/ntfy-password",
    "alertmanager_runtime_triage_webhook_url": "",
    "alertmanager_runtime_pgaudit_relay_webhook_url": "http://127.0.0.1:19094/x",
}


def test_env_template_default_has_no_cluster_flags() -> None:
    out = render(
        ENV_TEMPLATE.read_text(),
        **BASE_AM,
        alertmanager_runtime_cluster_advertise_address="",
        alertmanager_runtime_cluster_peers=[],
    )
    assert out.strip() == (
        'ARGS="--config.file=/etc/alertmanager/alertmanager.yml --storage.path=/var/lib/prometheus/alertmanager '
        '--web.listen-address=0.0.0.0:9093"'
    )


def test_env_template_renders_the_live_cluster_flags() -> None:
    out = render(
        ENV_TEMPLATE.read_text(),
        **BASE_AM,
        alertmanager_runtime_cluster_advertise_address="100.64.0.4:9094",
        alertmanager_runtime_cluster_peers=["100.64.0.21:9094"],
    )
    assert out.strip().endswith(
        '--web.listen-address=0.0.0.0:9093 --cluster.advertise-address=100.64.0.4:9094 --cluster.peer=100.64.0.21:9094"'
    )


def _receivers(rendered: str) -> dict:
    return {r["name"]: r for r in yaml.safe_load(rendered)["receivers"]}


def _significant(text: str) -> list[str]:
    # the "# {% if %}" idiom leaves comment-only lines ("#", "# #") behind; they carry no meaning
    return [line for line in text.splitlines() if line.strip().replace("#", "").strip() != ""]


def test_alertmanager_config_unchanged_when_secondary_ntfy_is_off() -> None:
    new = render(
        AM_CONFIG.read_text(),
        **BASE_AM,
        alertmanager_runtime_secondary_ntfy_base_url="",
        alertmanager_runtime_secondary_ntfy_topics={},
    )
    old_src = git_show(AM_CONFIG)
    assert old_src is not None
    assert _significant(new) == _significant(render(old_src, **BASE_AM))


def test_alertmanager_config_fans_out_every_ntfy_receiver_to_the_second_server() -> None:
    rendered = render(
        AM_CONFIG.read_text(),
        **BASE_AM,
        alertmanager_runtime_secondary_ntfy_base_url="http://100.64.0.21:2586",
        alertmanager_runtime_secondary_ntfy_token_file="/etc/alertmanager/ntfy-tier0-token",
        alertmanager_runtime_secondary_ntfy_topics={"critical": "t0-c", "warning": "t0-w", "watchdog": "t0-h"},
    )
    receivers = _receivers(rendered)
    for name, topic in (("ntfy-critical", "t0-c"), ("ntfy-warning", "t0-w"), ("ntfy-watchdog", "t0-h")):
        hooks = receivers[name]["webhook_configs"]
        assert len(hooks) == 2, name
        assert hooks[0]["url"].startswith("http://ntfy.example.com:2586/")
        assert hooks[1]["url"].startswith(f"http://100.64.0.21:2586/{topic}?tpl=yes")
        assert hooks[1]["http_config"]["authorization"] == {
            "type": "Bearer",
            "credentials_file": "/etc/alertmanager/ntfy-tier0-token",
        }
        assert hooks[1]["max_alerts"] == 5
    assert receivers["ntfy-critical"]["webhook_configs"][1]["send_resolved"] is True
    assert receivers["ntfy-warning"]["webhook_configs"][1]["send_resolved"] is False


def test_secondary_ntfy_needs_topics_not_just_a_url() -> None:
    rendered = render(
        AM_CONFIG.read_text(),
        **BASE_AM,
        alertmanager_runtime_secondary_ntfy_base_url="http://100.64.0.21:2586",
        alertmanager_runtime_secondary_ntfy_topics={},
    )
    assert all(len(r["webhook_configs"]) == 1 for n, r in _receivers(rendered).items() if n.startswith("ntfy-"))


def test_inventory_declares_the_replica_jobs_in_the_existing_extra_scrape_jobs_list() -> None:
    inv = yaml.safe_load(INVENTORY.read_text())
    jobs = {j["job_name"]: j for j in inv["monitoring_prometheus_extra_scrape_jobs"]}
    assert jobs["tier0_node_exporter"]["static_configs"][0]["targets"] == ["100.64.0.21:9101"]
    assert jobs["alertmanager_tier0"]["static_configs"][0]["labels"]["host"] == "infer-tier0"
    assert inv["monitoring_prometheus_extra_alertmanager_targets"] == ["100.64.0.21:9093"]


def test_inventory_values_match_the_live_mesh() -> None:
    inv = yaml.safe_load(INVENTORY.read_text())
    assert inv["alertmanager_runtime_cluster_advertise_address"] == "100.64.0.4:9094"
    assert inv["alertmanager_runtime_cluster_peers"] == ["100.64.0.21:9094"]
    assert inv["alertmanager_runtime_secondary_ntfy_base_url"] == "http://100.64.0.21:2586"
    assert "t0-" not in INVENTORY.read_text(), "anonymously readable ntfy topic names must never be committed"
