from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_INCLUDE_PATH = REPO_ROOT / "playbooks" / "_includes" / "dns_publication.yml"
COLLECTION_INCLUDE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "playbooks"
    / "_includes"
    / "dns_publication.yml"
)


def _task_names(playbook_path: Path) -> list[str]:
    play = yaml.safe_load(playbook_path.read_text(encoding="utf-8"))[0]
    return [task["name"] for task in play["tasks"]]


def _serialized_tasks(playbook_path: Path) -> str:
    play = yaml.safe_load(playbook_path.read_text(encoding="utf-8"))[0]
    return yaml.safe_dump(play["tasks"])


def test_repo_dns_publication_include_normalizes_real_domains_to_generic_catalog_entries() -> None:
    task_names = _task_names(REPO_INCLUDE_PATH)
    serialized = _serialized_tasks(REPO_INCLUDE_PATH)

    assert "Resolve the generic catalog FQDN for the requested service hostname" in task_names
    assert "selected_subdomain_runtime_fqdn == service_dns_fqdn" in serialized
    assert "service_dns_catalog_fqdn" in serialized
    assert "platform_domain" in serialized
    assert "Read the explicit deployment identity overlay selector" in task_names
    assert "PLATFORM_IDENTITY_OVERLAY" in serialized
    assert "regex_replace" in serialized
    assert "identity.yml" in serialized


def test_collection_dns_publication_include_keeps_generic_catalog_lookup_and_placeholder_resolution() -> None:
    task_names = _task_names(COLLECTION_INCLUDE_PATH)
    serialized = _serialized_tasks(COLLECTION_INCLUDE_PATH)

    assert "Load local identity overlay" in task_names
    assert "Resolve the generic catalog FQDN for the requested service hostname" in task_names
    assert "resolved_dns_target" in serialized
    assert "selected_subdomain_runtime_fqdn == service_dns_fqdn_resolved" in serialized
    assert "service_dns_catalog_fqdn" in serialized
    assert "platform_domain" in serialized
    assert "Read the explicit deployment identity overlay selector" in task_names
    assert "PLATFORM_IDENTITY_OVERLAY" in serialized
    assert "regex_replace" in serialized
    assert "identity.yml" in serialized
