from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "rag-context.yml"


def test_rag_context_playbook_converges_ollama_before_platform_context() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text(encoding="utf-8"))

    runtime_play = next(
        play for play in plays if play["name"] == "Converge the platform context API on the Docker runtime VM"
    )

    assert [role["role"] for role in runtime_play["roles"]] == [
        "lv3.platform.docker_runtime",
        "lv3.platform.ollama_runtime",
        "lv3.platform.rag_context_runtime",
    ]
