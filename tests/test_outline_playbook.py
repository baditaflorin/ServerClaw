import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "outline.yml"
SERVICE_PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "services" / "outline.yml"
MAKEFILE_PATH = REPO_ROOT / "Makefile"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
CONTROLLER_SECRET_PATH = REPO_ROOT / "config" / "controller-local-secrets.json"
SECRET_CATALOG_PATH = REPO_ROOT / "config" / "secret-catalog.json"


def test_outline_playbook_converges_only_the_outline_dns_record() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    dns_import = next(play for play in plays if play.get("import_playbook") == "_includes/dns_publication.yml")

    assert dns_import["when"] == "service_needs_dns | default(false)"


def test_outline_playbook_bootstraps_publication_after_edge_publish() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    nginx_play = next(play for play in plays if play.get("import_playbook") == "_includes/nginx_edge_publication.yml")
    publication_play = next(play for play in plays if play.get("name") == "Bootstrap and verify Outline publication")
    publish_task = publication_play["tasks"][0]

    assert plays.index(nginx_play) < plays.index(publication_play)
    assert publication_play["hosts"] == "localhost"
    assert publication_play["connection"] == "local"
    assert publish_task["ansible.builtin.include_role"]["name"] == "lv3.platform.outline_runtime"
    assert publish_task["ansible.builtin.include_role"]["tasks_from"] == "publish.yml"


def test_outline_service_playbook_imports_the_main_outline_playbook() -> None:
    plays = yaml.safe_load(SERVICE_PLAYBOOK_PATH.read_text())
    assert plays == [{"import_playbook": "../outline.yml"}]


def test_outline_converge_requires_explicit_deployment_selection() -> None:
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    converge_block = makefile.split("converge-outline:\n", 1)[1].split("\n\n", 1)[0]

    assert "$(MAKE) preflight-outline-deployment-selection" in converge_block
    assert converge_block.index("preflight-outline-deployment-selection") < converge_block.index(
        "preflight WORKFLOW=converge-outline"
    )


def test_outline_workflow_declares_authentik_and_keycloak_rollback_secrets() -> None:
    workflow = json.loads(WORKFLOW_CATALOG_PATH.read_text(encoding="utf-8"))["workflows"]["converge-outline"]

    assert "preflight-outline-deployment-selection" in workflow["validation_targets"]
    assert "syntax-check-outline" in workflow["validation_targets"]
    required = set(workflow["preflight"]["required_secret_ids"])
    assert {
        "authentik_outline_client_secret",
        "keycloak_outline_client_secret",
        "outline_api_token",
    } <= required


def test_outline_authentik_secret_is_cataloged_without_removing_keycloak_rollback() -> None:
    controller = json.loads(CONTROLLER_SECRET_PATH.read_text(encoding="utf-8"))["secrets"]
    catalog = {entry["id"]: entry for entry in json.loads(SECRET_CATALOG_PATH.read_text(encoding="utf-8"))["secrets"]}

    assert controller["authentik_outline_client_secret"]["path"] == (".local/authentik/outline-client-secret.txt")
    assert catalog["authentik_outline_client_secret"]["owner_service"] == "outline"
    assert controller["keycloak_outline_client_secret"]["status"] == "active"
    assert catalog["keycloak_outline_client_secret"]["owner_service"] == "outline"
