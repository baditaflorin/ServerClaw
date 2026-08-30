from pathlib import Path

import yaml


COMMON_TASKS = Path("collections/ansible_collections/lv3/platform/roles/common/tasks/manage_service_secrets.yml")
ROLE_TASK_GLOB = "collections/ansible_collections/lv3/platform/roles/*/tasks/*.yml"


def test_literal_secret_values_are_not_interpolated_into_shell_source() -> None:
    tasks = yaml.safe_load(COMMON_TASKS.read_text(encoding="utf-8"))
    generation = next(task for task in tasks if task["name"] == "Generate secrets idempotently on the remote host")

    shell_source = generation["ansible.builtin.shell"]
    assert "$LV3_MANAGED_SECRET_VALUE" in shell_source
    assert "{{ item.value" not in shell_source
    assert generation["environment"]["LV3_MANAGED_SECRET_VALUE"] == "{{ item.value | default('') }}"
    assert generation["no_log"] is True


def test_secret_filter_callers_declare_literal_values_not_commands() -> None:
    offenders: list[str] = []
    for path in Path().glob(ROLE_TASK_GLOB):
        source = path.read_text(encoding="utf-8")
        if "tasks_from: manage_service_secrets" not in source:
            continue
        for line_number, line in enumerate(source.splitlines(), start=1):
            if "command:" in line and "| secret" in line:
                offenders.append(f"{path}:{line_number}")

    assert offenders == []


def test_generated_secret_declarations_require_one_source_kind() -> None:
    tasks = yaml.safe_load(COMMON_TASKS.read_text(encoding="utf-8"))
    validation = next(task for task in tasks if task["name"] == "Validate generated secret declarations")
    conditions = validation["ansible.builtin.assert"]["that"]

    assert "(item.value is defined) != (item.command is defined)" in conditions
    assert validation["no_log"] is True
