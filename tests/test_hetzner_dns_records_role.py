from pathlib import Path

import yaml


ROLE_TASKS = Path("collections/ansible_collections/lv3/platform/roles/hetzner_dns_records/tasks/record.yml")
MAIN_TASKS = Path("collections/ansible_collections/lv3/platform/roles/hetzner_dns_records/tasks/main.yml")


def test_missing_live_ttl_defaults_to_desired_ttl() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text())
    update_task = next(
        task for task in tasks if task["name"] == "Update the canonical DNS record TTL when only TTL drift is detected"
    )
    condition = " ".join(str(part) for part in update_task["when"])

    assert "dns_provider_boundary_matching_records[0].record_ttl" in condition
    assert "hetzner_dns_record.ttl | default(60) | int" in condition


def test_multi_record_role_translates_provider_payloads_before_matching() -> None:
    main_tasks = MAIN_TASKS.read_text(encoding="utf-8")
    record_tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "Translate Hetzner DNS zone provider payload into canonical zone facts" in main_tasks
    assert "Translate Hetzner DNS rrset provider payload into canonical record facts" in main_tasks
    assert main_tasks.count("hetzner_dns_zone_lookup.json.zones") == 1
    assert "hetzner_dns_existing_rrsets" in main_tasks
    assert "rrset.records | default([])" in main_tasks
    assert "dns_provider_boundary_existing_records" in record_tasks
    assert "hetzner_dns_existing_rrsets" not in record_tasks
    assert "dns_provider_boundary_matching_records[0].provider_ref" in record_tasks


def test_multi_record_role_walks_and_validates_all_rrset_pages() -> None:
    main_tasks = yaml.safe_load(MAIN_TASKS.read_text())
    names = {task["name"] for task in main_tasks}
    main_text = MAIN_TASKS.read_text(encoding="utf-8")

    assert "Read the first page of current Hetzner DNS rrsets for the zone" in names
    assert "Read the remaining pages of current Hetzner DNS rrsets for the zone" in names
    assert "Combine all Hetzner DNS rrset pages" in names
    assert "Assert the paginated Hetzner DNS rrset inventory is complete" in names
    assert "range(2, (hetzner_dns_rrset_last_page | int) + 1)" in main_text
    assert "meta.pagination.total_entries" in main_text
    assert "per_page={{ hetzner_dns_rrsets_per_page | int }}" in main_text
    assert "fits in a single 100-entry page" not in main_text


def test_multi_record_role_supports_absent_state() -> None:
    record_tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "hetzner_dns_record.state | default('present')" in record_tasks
    assert "Delete the canonical DNS record when it is retired" in record_tasks
    assert "method: DELETE" in record_tasks


def test_multi_record_role_updates_same_name_type_drift_instead_of_creating_duplicates() -> None:
    record_tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "dns_provider_boundary_same_name_type_records" in record_tasks
    assert "if (hetzner_dns_record.state | default('present')) == 'present'" in record_tasks
    assert "Build the reconciled full DNS rrset record list" in record_tasks
    assert "Append the missing value to an existing canonical DNS rrset" in record_tasks
    assert "dns_provider_boundary_reconciled_rrset_records" in record_tasks
    assert "existing.record_comment | default('')" in record_tasks


def test_multi_record_role_retries_transient_provider_errors() -> None:
    record_tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "retries: 5" in record_tasks
    assert "delay: 2" in record_tasks
    assert "429" in record_tasks
    assert "504" in record_tasks
    assert "return_content: true" in record_tasks
    assert "hetzner_dns_record_create_response.status in [200, 201]" in record_tasks
    assert "hetzner_dns_record_append_response.status in [200, 201]" in record_tasks
    assert "hetzner_dns_record_update_response.status in [200, 201]" in record_tasks
    assert "hetzner_dns_record_delete_response.status in [200, 201, 204]" in record_tasks


def test_multi_record_role_marks_provider_mutations_as_changed() -> None:
    record_tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert record_tasks.count("changed_when: true") == 5


def test_multi_record_role_builds_native_json_payload_for_create_and_update() -> None:
    record_tasks = ROLE_TASKS.read_text(encoding="utf-8")

    assert "Build the canonical DNS rrset provider payload" in record_tasks
    assert "'ttl': (hetzner_dns_record.ttl | default(60) | int)" in record_tasks
    assert "'records': [" in record_tasks
    assert record_tasks.count('body: "{{ dns_provider_boundary_desired_record_payload }}"') == 1
    assert record_tasks.count('records: "{{ dns_provider_boundary_reconciled_rrset_records }}"') == 2


def test_brownout_manual_fallback_gates_all_write_operations() -> None:
    """ADR 0430 PR 3 — when hetzner_dns_brownout_manual_fallback is true,
    every create/update/delete task must be gated off so the role makes no
    write API calls during the Hetzner DNS-Console brownout.
    """
    record_tasks = yaml.safe_load(ROLE_TASKS.read_text())

    for action_name in (
        "Delete the canonical DNS record when it is retired",
        "Create the canonical DNS record when it does not exist",
        "Append the missing value to an existing canonical DNS rrset",
        "Update the canonical DNS record values when value drift is detected",
        "Update the canonical DNS record TTL when only TTL drift is detected",
    ):
        task = next(t for t in record_tasks if t["name"] == action_name)
        conditions = [str(c) for c in task["when"]]
        assert any("hetzner_dns_brownout_manual_fallback" in c for c in conditions), (
            f"{action_name!r} must be gated by hetzner_dns_brownout_manual_fallback"
        )


def test_brownout_manual_fallback_emits_summary_and_collector() -> None:
    """The role must collect pending record changes (per-record) and emit a
    consolidated summary (in main.yml) when brownout fallback is active.
    """
    main_tasks = MAIN_TASKS.read_text(encoding="utf-8")
    record_tasks = ROLE_TASKS.read_text(encoding="utf-8")

    # per-record collector accumulates pending writes
    assert "hetzner_dns_brownout_pending_records" in record_tasks
    # main.yml resets the accumulator and emits the summary
    assert "Reset the Hetzner DNS brownout pending-record accumulator" in main_tasks
    assert "Summarise Hetzner DNS records awaiting manual publication" in main_tasks
    # operator guidance mentions the manual console and the shutdown date
    assert "https://dns.hetzner.com" in main_tasks
    assert "2026-05-20" in main_tasks


def test_brownout_manual_fallback_default_is_off() -> None:
    """The role must default to normal API-write behaviour so existing
    deployments are unaffected.
    """
    defaults = yaml.safe_load(
        Path("collections/ansible_collections/lv3/platform/roles/hetzner_dns_records/defaults/main.yml").read_text()
    )
    assert defaults["hetzner_dns_brownout_manual_fallback"] is False
