from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "windmill.yml"


def test_windmill_playbook_relies_on_postgres_role_handlers_instead_of_forcing_restart() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    postgres_play = next(play for play in plays if play["name"] == "Converge PostgreSQL access for Windmill")

    assert "post_tasks" not in postgres_play
