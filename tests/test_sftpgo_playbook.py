from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "sftpgo.yml"
SERVICE_PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "services" / "sftpgo.yml"
MAKEFILE_PATH = REPO_ROOT / "Makefile"


def test_sftpgo_playbook_imports_standard_includes_and_publish_play() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    imports = [entry["import_playbook"] for entry in plays if "import_playbook" in entry]

    assert imports == [
        "_includes/dns_publication.yml",
        "_includes/postgres_preparation.yml",
        "_includes/docker_runtime_converge.yml",
        "_includes/nginx_edge_publication.yml",
    ]

    publish_play = next(
        play for play in plays if play.get("name") == "Bootstrap and verify the SFTPGo publication contract"
    )
    publish_tasks = publish_play["tasks"]
    assert publish_play["hosts"] == "localhost"
    assert publish_tasks == [
        {
            "name": "Bootstrap and verify the SFTPGo provisioning and publication contract",
            "ansible.builtin.include_role": {
                "name": "lv3.platform.sftpgo_runtime",
                "tasks_from": "publish.yml",
            },
        }
    ]


def test_root_service_wrapper_imports_the_sftpgo_playbook() -> None:
    service = yaml.safe_load(SERVICE_PLAYBOOK_PATH.read_text())
    assert service == [{"import_playbook": "../sftpgo.yml"}]


def test_converge_sftpgo_stages_edge_static_sites_before_live_apply() -> None:
    makefile = MAKEFILE_PATH.read_text()
    converge_block = makefile.split("converge-sftpgo:\n", 1)[1].split("\n\n", 1)[0]

    assert "$(MAKE) generate-edge-static-sites" in converge_block
    assert "HETZNER_DNS_API_TOKEN" in converge_block
