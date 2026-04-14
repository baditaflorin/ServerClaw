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

    assert "Derive the catalog lookup FQDN from the requested service hostname" in task_names
    assert "catalog_placeholder_domain: example.com" in REPO_INCLUDE_PATH.read_text(encoding="utf-8")
    assert "selected_subdomain.fqdn == catalog_lookup_fqdn" in serialized
    assert "service_dns_fqdn.rsplit('.' ~ hetzner_dns_zone_name, 1)[0]" in serialized


def test_collection_dns_publication_include_keeps_generic_catalog_lookup_and_placeholder_resolution() -> None:
    task_names = _task_names(COLLECTION_INCLUDE_PATH)
    serialized = _serialized_tasks(COLLECTION_INCLUDE_PATH)
    include_text = COLLECTION_INCLUDE_PATH.read_text(encoding="utf-8")

    assert "Load local identity overlay (real deployment values — gitignored)" in task_names
    assert "Derive the catalog lookup FQDN from the requested service hostname" in task_names
    assert "catalog_placeholder_domain: example.com" in include_text
    assert "resolved_dns_target" in serialized
    assert "service_dns_fqdn.rsplit('.' ~ hetzner_dns_zone_name, 1)[0]" in serialized
