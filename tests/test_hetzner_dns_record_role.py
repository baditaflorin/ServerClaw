from pathlib import Path


ROLE_TASKS = Path("collections/ansible_collections/lv3/platform/roles/hetzner_dns_record/tasks/main.yml")


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
    assert "json.error.code" in tasks
    assert "DNS Console brownout during migration" in tasks


def test_single_record_role_sends_json_scalars_and_rejects_embedded_provider_errors() -> None:
    tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "Content-Type: application/json" in tasks
    assert "| to_json" in tasks
    assert "json.error" in tasks
    assert "json.record.id" in tasks


def test_single_record_role_reports_provider_error_details_after_retries() -> None:
    tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "Fail with provider details when DNS record creation did not complete" in tasks
    assert "Fail with provider details when DNS record update did not complete" in tasks
    assert "Fail with provider details when DNS record deletion did not complete" in tasks


def test_single_record_role_rechecks_provider_state_after_create_attempts() -> None:
    tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "Query Hetzner DNS records for the zone after a create attempt" in tasks
    assert "hetzner_dns_records_post_create_query" in tasks
    assert "selectattr('value', 'equalto', hetzner_dns_record_value)" in tasks
