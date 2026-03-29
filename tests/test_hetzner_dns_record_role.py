from pathlib import Path


ROLE_TASKS = Path(
    "collections/ansible_collections/lv3/platform/roles/hetzner_dns_record/tasks/main.yml"
)


def test_single_record_role_translates_provider_payloads_before_matching() -> None:
    tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "Translate Hetzner DNS zone provider payload into canonical zone facts" in tasks
    assert "Translate Hetzner DNS record provider payload into canonical record facts" in tasks
    assert tasks.count("hetzner_dns_zone_query.json.zones") == 1
    assert tasks.count("hetzner_dns_records_query.json.records") == 1
    assert "dns_provider_boundary_zone.provider_ref" in tasks
    assert "dns_provider_boundary_matching_records[0].provider_ref" in tasks


def test_single_record_role_supports_absent_state() -> None:
    tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "hetzner_dns_record_state in ['present', 'absent']" in tasks
    assert "Delete the canonical DNS record when it is retired" in tasks
    assert "method: DELETE" in tasks


def test_single_record_role_updates_same_name_type_drift_instead_of_creating_duplicates() -> None:
    tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "dns_provider_boundary_same_name_type_records" in tasks
    assert "if hetzner_dns_record_state == 'present'" in tasks


def test_single_record_role_retries_transient_provider_errors() -> None:
    tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "retries: 5" in tasks
    assert "delay: 2" in tasks
    assert "429" in tasks
    assert "504" in tasks
