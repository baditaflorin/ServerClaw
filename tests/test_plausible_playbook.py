import json
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml
from jinja2 import Template


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "plausible.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "plausible.yml"
MAKEFILE_PATH = REPO_ROOT / "Makefile"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
CLICKHOUSE_LOGS_TEMPLATE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "plausible_runtime"
    / "templates"
    / "clickhouse"
    / "logs.xml.j2"
)
PLAUSIBLE_ROLE_DEFAULTS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "plausible_runtime"
    / "defaults"
    / "main.yml"
)
PLAUSIBLE_CATALOG_PATH = REPO_ROOT / "catalog" / "services" / "plausible" / "service.yaml"


def test_clickhouse_diagnostic_logs_have_one_day_retention() -> None:
    rendered = Template(CLICKHOUSE_LOGS_TEMPLATE_PATH.read_text()).render(
        plausible_clickhouse_system_log_retention_days=1
    )
    root = ET.fromstring(rendered)
    defaults = yaml.safe_load(PLAUSIBLE_ROLE_DEFAULTS_PATH.read_text())
    expected_logs = {
        "text_log",
        "trace_log",
        "metric_log",
        "asynchronous_metric_log",
        "part_log",
        "error_log",
        "background_schedule_pool_log",
        "processors_profile_log",
        "query_log",
        "query_metric_log",
        "asynchronous_insert_log",
    }

    assert defaults["plausible_clickhouse_system_log_retention_days"] == 1
    assert {node.tag for node in root if node.tag != "logger"} == expected_logs
    assert all(root.findtext(f"{table}/ttl") == "event_time + INTERVAL 1 DAY DELETE" for table in expected_logs)
    assert root.findtext("text_log/level") == "warning"

    catalog = yaml.safe_load(PLAUSIBLE_CATALOG_PATH.read_text())
    analytics_events = next(item for item in catalog["data"] if item["id"] == "plausible-analytics-events")
    assert analytics_events["retention_days"] == 365


def test_plausible_playbook_imports_standard_includes() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    imports = [entry["import_playbook"] for entry in plays if "import_playbook" in entry]

    assert imports == [
        "_includes/dns_publication.yml",
        "_includes/docker_runtime_converge.yml",
        "_includes/nginx_edge_publication.yml",
    ]


def test_plausible_service_wrapper_imports_the_canonical_playbook() -> None:
    wrapper_text = SERVICE_WRAPPER_PATH.read_text()
    wrapper = yaml.safe_load(wrapper_text)

    assert "# Purpose: Provide the stable live-apply service wrapper for Plausible Analytics." in wrapper_text
    assert wrapper == [{"import_playbook": "../plausible.yml"}]


def test_converge_plausible_target_uses_the_canonical_playbook() -> None:
    makefile = MAKEFILE_PATH.read_text()
    converge_block = makefile.split("converge-plausible:\n", 1)[1].split("\n\n", 1)[0]

    assert "$(MAKE) preflight WORKFLOW=converge-plausible" in converge_block
    assert "uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate" in converge_block
    assert "$(MAKE) generate-edge-static-sites" in converge_block
    assert "$(REPO_ROOT)/playbooks/plausible.yml" in converge_block


def test_converge_plausible_workflow_bootstraps_shared_edge_generated_portals() -> None:
    workflows = json.loads(WORKFLOW_CATALOG_PATH.read_text(encoding="utf-8"))["workflows"]

    assert workflows["converge-plausible"]["preflight"]["bootstrap_manifest_ids"] == ["shared-edge-generated-portals"]
