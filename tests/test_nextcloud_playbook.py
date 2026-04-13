from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "nextcloud.yml"
MAKEFILE_PATH = REPO_ROOT / "Makefile"


def test_nextcloud_playbook_imports_standard_includes_and_post_verify() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    imports = [entry["import_playbook"] for entry in plays if "import_playbook" in entry]

    assert imports == [
        "_includes/dns_publication.yml",
        "_includes/postgres_preparation.yml",
        "_includes/nginx_edge_publication.yml",
    ]

    verify_play = next(
        play for play in plays if play.get("name") == "Verify Nextcloud publication after edge convergence"
    )
    verify_tasks = verify_play["tasks"]
    assert verify_play["hosts"] == (
        "{{ 'docker-runtime-staging' if (env | default('production')) == 'staging' else 'runtime-apps' }}"
    )
    assert [task["name"] for task in verify_tasks] == [
        "Run shared Nextcloud post-verify checks",
        "Run shared completion notifications",
    ]


def test_converge_nextcloud_target_stages_edge_static_sites_before_live_apply() -> None:
    makefile = MAKEFILE_PATH.read_text()
    converge_block = makefile.split("converge-nextcloud:\n", 1)[1].split("\n\n", 1)[0]

    assert "$(MAKE) generate-edge-static-sites" in converge_block
