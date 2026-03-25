from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER_TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "common"
    / "tasks"
    / "openbao_compose_env.yml"
)


def test_helper_unseals_restarted_openbao_before_waiting_for_health() -> None:
    tasks = HELPER_TASKS_PATH.read_text(encoding="utf-8")

    assert "- name: Read the local OpenBao seal status" in tasks
    assert "/v1/sys/seal-status" in tasks
    assert "- name: Unseal the local OpenBao API when it restarted in a sealed state" in tasks
    assert "/v1/sys/unseal" in tasks
    assert "keys_base64[:openbao_init_key_threshold | default(2)]" in tasks
    assert "- name: Assert the local OpenBao API is unsealed before runtime secret injection" in tasks
    assert "- name: Wait for the local OpenBao API to become active" in tasks
