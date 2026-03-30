from pathlib import Path

import yaml


ROLE_TASKS = Path(
    "collections/ansible_collections/lv3/platform/roles/hetzner_dns_records/tasks/record.yml"
)
MAIN_TASKS = Path(
    "collections/ansible_collections/lv3/platform/roles/hetzner_dns_records/tasks/main.yml"
)


def test_missing_live_ttl_defaults_to_desired_ttl() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text())
    update_task = next(
        task
        for task in tasks
        if task["name"] == "Update the canonical DNS record when drift is detected"
    )
    condition = " ".join(str(part) for part in update_task["when"])

    assert "dns_provider_boundary_matching_records[0].record_ttl" in condition
    assert "hetzner_dns_record.ttl | default(60) | int" in condition


def test_multi_record_role_translates_provider_payloads_before_matching() -> None:
    main_tasks = MAIN_TASKS.read_text(encoding="utf-8")
    record_tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "Translate Hetzner DNS zone provider payload into canonical zone facts" in main_tasks
    assert "Translate Hetzner DNS record provider payload into canonical record facts" in main_tasks
    assert main_tasks.count("hetzner_dns_zone_lookup.json.zones") == 1
    assert main_tasks.count("hetzner_dns_records_lookup.json.records") == 1
    assert "dns_provider_boundary_existing_records" in record_tasks
    assert "hetzner_dns_records_lookup.json.records" not in record_tasks
    assert "dns_provider_boundary_matching_records[0].provider_ref" in record_tasks


def test_multi_record_role_supports_absent_state() -> None:
    record_tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "hetzner_dns_record.state | default('present')" in record_tasks
    assert "Delete the canonical DNS record when it is retired" in record_tasks
    assert "method: DELETE" in record_tasks


def test_multi_record_role_updates_same_name_type_drift_instead_of_creating_duplicates() -> None:
    record_tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "dns_provider_boundary_same_name_type_records" in record_tasks
    assert "if (hetzner_dns_record.state | default('present')) == 'present'" in record_tasks


def test_multi_record_role_retries_transient_provider_errors() -> None:
    record_tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "retries: 5" in record_tasks
    assert "delay: 2" in record_tasks
    assert "429" in record_tasks
    assert "504" in record_tasks


def test_multi_record_role_marks_provider_mutations_as_changed() -> None:
    record_tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert record_tasks.count("changed_when: true") == 3


def test_multi_record_role_builds_native_json_payload_for_create_and_update() -> None:
    record_tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "Build the canonical DNS record provider payload" in record_tasks
    assert "'ttl': (hetzner_dns_record.ttl | default(60) | int)" in record_tasks
    assert record_tasks.count('body: "{{ dns_provider_boundary_desired_record_payload }}"') == 2
