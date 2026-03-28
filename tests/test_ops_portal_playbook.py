from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "ops-portal.yml"


def test_ops_portal_playbook_uses_controller_pwd_as_repo_root() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    play = plays[0]

    assert play["vars"]["ops_portal_repo_root"] == "{{ lookup('ansible.builtin.env', 'PWD') }}"
