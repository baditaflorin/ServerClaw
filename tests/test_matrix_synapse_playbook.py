from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "matrix-synapse.yml"


def test_matrix_synapse_playbook_imports_standard_includes_and_public_verify() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    imports = [entry["import_playbook"] for entry in plays if "import_playbook" in entry]

    assert imports == [
        "_includes/dns_publication.yml",
        "_includes/nginx_edge_publication.yml",
    ]

    assert {"role": "lv3.platform.proxmox_tailscale_proxy"} in plays[1]["roles"]
    assert {"role": "lv3.platform.matrix_synapse_postgres"} in plays[2]["roles"]
    assert {"role": "lv3.platform.matrix_synapse_runtime"} in plays[3]["roles"]

    public_verify_play = next(
        play for play in plays if play.get("name") == "Verify the public Matrix Synapse bridge surfaces"
    )
    public_verify_task = public_verify_play["tasks"][0]
    assert public_verify_play["hosts"] == "localhost"
    assert public_verify_task["ansible.builtin.include_role"]["name"] == "lv3.platform.matrix_synapse_runtime"
    assert public_verify_task["ansible.builtin.include_role"]["tasks_from"] == "public_verify.yml"
