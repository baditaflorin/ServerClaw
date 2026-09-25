from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "grafana_sso" / "defaults" / "main.yml"
ROLE_META = REPO_ROOT / "roles" / "grafana_sso" / "meta" / "argument_specs.yml"
ROOT_PLAYBOOK = REPO_ROOT / "playbooks" / "services" / "grafana.yml"
COLLECTION_PLAYBOOK = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "services" / "grafana.yml"
)


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_grafana_sso_loads_the_authentik_secret_from_the_controller_local_artifact() -> None:
    defaults = load_yaml(ROLE_DEFAULTS)
    options = load_yaml(ROLE_META)["argument_specs"]["main"]["options"]

    assert defaults["grafana_sso_client_secret_local_file"] == "{{ authentik_grafana_client_secret_local_file }}"
    assert (
        "lookup('ansible.builtin.file', grafana_sso_client_secret_local_file)" in defaults["grafana_sso_client_secret"]
    )
    assert options["grafana_sso_client_secret_local_file"]["type"] == "path"
    assert "grafana_sso_client_secret" not in options


def test_both_grafana_service_entrypoints_apply_the_authentik_sso_role() -> None:
    for playbook_path in (ROOT_PLAYBOOK, COLLECTION_PLAYBOOK):
        playbook = load_yaml(playbook_path)
        roles = [role["role"] for role in playbook[0]["roles"]]

        assert roles[-1] == "lv3.platform.grafana_sso"
