from pathlib import Path
import re

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "grafana_sso" / "defaults" / "main.yml"
COLLECTION_ROLE_DEFAULTS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "grafana_sso"
    / "defaults"
    / "main.yml"
)
ROLE_META = REPO_ROOT / "roles" / "grafana_sso" / "meta" / "argument_specs.yml"
ROLE_TASKS = REPO_ROOT / "roles" / "grafana_sso" / "tasks" / "main.yml"
ROOT_PLAYBOOK = REPO_ROOT / "playbooks" / "services" / "grafana.yml"
COLLECTION_PLAYBOOK = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "services" / "grafana.yml"
)
AUTHENTIK_SCOPE_MAPPINGS = REPO_ROOT / "config" / "authentik" / "scope-mappings.yaml"


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


def test_grafana_requests_the_custom_scope_that_supplies_its_groups_claim() -> None:
    tasks = load_yaml(ROLE_TASKS)
    oauth_task = next(task for task in tasks if task.get("name") == "Enable Generic OAuth in Grafana")
    options = {item["option"]: item["value"] for item in oauth_task["loop"]}
    scope_manifest = load_yaml(AUTHENTIK_SCOPE_MAPPINGS)
    grafana_mapping = next(item for item in scope_manifest["mappings"] if item["id"] == "grafana-groups")

    assert options["scopes"] == "openid profile email grafana-groups"
    assert grafana_mapping["scope_name"] == "grafana-groups"
    assert '"groups": [' in grafana_mapping["expression"]
    assert options["groups_attribute_path"] == "groups"


def test_grafana_signout_uses_its_own_authentik_provider_endpoint() -> None:
    for defaults_path in (ROLE_DEFAULTS, COLLECTION_ROLE_DEFAULTS):
        defaults = load_yaml(defaults_path)

        assert defaults["grafana_sso_oidc_logout_url"] == "{{ grafana_sso_oidc_issuer_url }}end-session/"
        assert (
            "{{ grafana_sso_oidc_logout_url }}?post_logout_redirect_uri="
            in defaults["grafana_sso_signout_redirect_url"]
        )
        assert "{{ grafana_sso_session_authority.oidc_logout_url }}" not in defaults["grafana_sso_signout_redirect_url"]
        assert (
            "grafana_sso_session_authority.shared_proxy_cleanup_url | urlencode"
            in defaults["grafana_sso_signout_redirect_url"]
        )


def test_grafana_pins_server_side_authentik_requests_to_the_private_edge() -> None:
    defaults = load_yaml(ROLE_DEFAULTS)
    tasks = load_yaml(ROLE_TASKS)
    pin_task = next(
        task for task in tasks if task.get("name") == "Pin Authentik server-side OIDC requests to the private edge"
    )

    assert defaults["grafana_sso_oidc_hostname"] == "{{ authentik_oidc_base_url | urlsplit('hostname') }}"
    assert (
        defaults["grafana_sso_internal_edge_ipv4"] == "{{ hostvars[platform_topology_host].proxmox_public_edge_ipv4 }}"
    )
    assert pin_task["ansible.builtin.lineinfile"]["path"] == "/etc/hosts"
    assert pin_task["ansible.builtin.lineinfile"]["create"] is False
    assert pin_task["notify"] == "Restart Grafana"
    hostname_matcher = pin_task["ansible.builtin.lineinfile"]["regexp"].replace(
        "{{ grafana_sso_oidc_hostname | regex_escape }}", re.escape("id.example.com")
    )
    assert re.search(hostname_matcher, "10.10.10.10 id.example.com\n")
    assert not re.search(hostname_matcher, "10.10.10.10 unrelated.example.com\n")
