from pathlib import Path

import yaml


ROLE_TASKS = Path("collections/ansible_collections/lv3/platform/roles/hetzner_dns_record/tasks/main.yml")


def _tasks() -> list[dict]:
    return yaml.safe_load(ROLE_TASKS.read_text(encoding="utf-8"))


def _task(name: str) -> dict:
    return next(task for task in _tasks() if task["name"] == name)


def test_single_record_role_translates_rrset_payloads_before_matching() -> None:
    tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "Translate Hetzner DNS zone provider payload into canonical zone facts" in tasks
    assert "Translate Hetzner DNS record provider payload into canonical record facts" in tasks
    assert tasks.count("hetzner_dns_zone_query.json.zones") == 1
    assert tasks.count("hetzner_dns_records_query.json.rrsets") == 1
    assert "dns_provider_boundary_zone.provider_ref" in tasks


def test_single_record_role_queries_only_the_managed_rrset() -> None:
    initial_query = _task("Query existing Hetzner DNS records for the zone")
    post_create_query = _task("Query Hetzner DNS records for the zone after a create attempt")

    for task in (initial_query, post_create_query):
        request_url = task["ansible.builtin.uri"]["url"]
        assert request_url.endswith(
            "/rrsets?name={{ hetzner_dns_record_name | urlencode }}&type={{ hetzner_dns_record_type | urlencode }}"
        )


def test_single_record_role_supports_absent_state() -> None:
    tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "hetzner_dns_record_state in ['present', 'absent']" in tasks
    assert "Delete the canonical DNS record when it is retired" in tasks
    assert "method: DELETE" in tasks


def test_single_record_role_creates_an_absent_rrset_via_the_collection_endpoint() -> None:
    payload_task = _task("Build the canonical DNS rrset provider payload")
    create_task = _task("Create the canonical DNS record when absent")
    payload = payload_task["ansible.builtin.set_fact"]["dns_provider_boundary_desired_record_payload"]
    request = create_task["ansible.builtin.uri"]

    assert request["method"] == "POST"
    assert request["url"].endswith("/zones/{{ dns_provider_boundary_zone.provider_ref }}/rrsets")
    assert "/actions/set_records" not in request["url"]
    assert request["body_format"] == "json"
    assert request["body"] == "{{ dns_provider_boundary_desired_record_payload }}"
    assert "'name': hetzner_dns_record_name" in payload
    assert "'type': hetzner_dns_record_type" in payload
    assert "'ttl': (hetzner_dns_record_ttl | int)" in payload
    assert "'records':" in payload
    assert "'value': hetzner_dns_record_value" in payload


def test_single_record_role_updates_same_name_type_drift_instead_of_creating_duplicates() -> None:
    tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "dns_provider_boundary_same_name_type_records" in tasks
    assert "dns_provider_boundary_matching_records | length == 1" in tasks


def test_single_record_role_retries_transient_provider_errors() -> None:
    tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "retries: 5" in tasks
    assert "delay: 2" in tasks
    assert "429" in tasks
    assert "504" in tasks
    assert "json.error.code" in tasks
    assert "DNS Console brownout during migration" in tasks


def test_single_record_role_rechecks_provider_state_after_create_attempts() -> None:
    tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "Query Hetzner DNS records for the zone after a create attempt" in tasks
    assert "hetzner_dns_rrsets_post_create_query" in tasks
    assert "Verify DNS record creation (record created with HTTP 201)" in tasks
