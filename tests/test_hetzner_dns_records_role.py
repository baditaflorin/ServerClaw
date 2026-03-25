from pathlib import Path

import yaml


ROLE_TASKS = Path(
    "collections/ansible_collections/lv3/platform/roles/hetzner_dns_records/tasks/record.yml"
)


def test_missing_live_ttl_defaults_to_desired_ttl() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text())
    update_task = next(
        task
        for task in tasks
        if task["name"] == "Update the Hetzner DNS record when drift is detected"
    )
    condition = " ".join(str(part) for part in update_task["when"])

    assert "hetzner_dns_matching_records[0].ttl" in condition
    assert "default(hetzner_dns_record.ttl | default(60))" in condition
