from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "step_ca_ssh_trust"
    / "defaults"
    / "main.yml"
)
TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "step_ca_ssh_trust"
    / "tasks"
    / "main.yml"
)


def test_step_ca_ssh_trust_defaults_define_retry_budget() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())

    assert defaults["step_ca_ssh_sign_delegate_host"] == (
        "{{ playbook_execution_host_patterns.runtime_control[playbook_execution_env] }}"
    )
    assert defaults["step_ca_ssh_issue_retries"] == 4
    assert defaults["step_ca_ssh_issue_delay_seconds"] == 3


def test_step_ca_ssh_trust_delegates_signing_to_runtime_control() -> None:
    tasks = yaml.safe_load(TASKS_PATH.read_text())
    slurp_task = next(task for task in tasks if task["name"] == "Read the SSH host public key that will be signed")
    host_id_task = next(
        task for task in tasks if task["name"] == "Derive the SSH host identity UUID from /etc/machine-id"
    )
    issue_task = next(task for task in tasks if task["name"] == "Issue or renew the SSH host certificate from step-ca")
    install_task = next(
        task for task in tasks if task["name"] == "Install the signed SSH host certificate on the target"
    )

    assert slurp_task["register"] == "step_ca_ssh_host_public_key_slurp"
    assert slurp_task["no_log"] is True
    assert host_id_task["register"] == "step_ca_ssh_host_identity_uuid"
    assert "python3" in host_id_task["ansible.builtin.command"]["argv"]
    assert issue_task["delegate_to"] == "{{ step_ca_ssh_sign_delegate_host }}"
    assert issue_task["register"] == "step_ca_ssh_issue_result"
    assert issue_task["retries"] == "{{ step_ca_ssh_issue_retries }}"
    assert issue_task["delay"] == "{{ step_ca_ssh_issue_delay_seconds }}"
    assert issue_task["until"] == "step_ca_ssh_issue_result.rc == 0"
    assert issue_task["throttle"] == 1
    assert '--host-id "{{ step_ca_ssh_host_identity_uuid.stdout | trim }}"' in issue_task["ansible.builtin.shell"]
    assert 'base64 -d > "$workdir/host.pub"' in issue_task["ansible.builtin.shell"]
    assert "--provisioner-password-file" in issue_task["ansible.builtin.shell"]
    assert "--token" not in issue_task["ansible.builtin.shell"]
    assert issue_task["no_log"] is True
    assert install_task["ansible.builtin.copy"]["content"] == "{{ step_ca_ssh_issue_result.stdout }}"
    assert install_task["no_log"] is True
