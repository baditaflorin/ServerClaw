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
