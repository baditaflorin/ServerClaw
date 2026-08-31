from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "nomad_oidc_auth"
DEFAULTS_PATH = ROLE_ROOT / "defaults" / "main.yml"
TASKS_PATH = ROLE_ROOT / "tasks" / "main.yml"
SPECS_PATH = ROLE_ROOT / "meta" / "argument_specs.yml"
OAUTH_CLIENTS_PATH = REPO_ROOT / "config" / "authentik" / "oauth-clients.yaml"


def _tasks() -> list[dict]:
    return yaml.safe_load(TASKS_PATH.read_text(encoding="utf-8"))


def test_nomad_oidc_defaults_use_authentik_and_name_the_explicit_retirement_target() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert defaults["nomad_oidc_auth_authentik_client_id"] == "nomad"
    assert defaults["nomad_oidc_auth_authentik_client_secret_local_file"] == (
        "{{ repo_shared_local_root }}/authentik/nomad-client-secret.txt"
    )
    assert defaults["nomad_oidc_auth_authentik_provider_slug"] == "nomad"
    assert "authentik_oidc_provider_base_url" in defaults["nomad_oidc_auth_oidc_discovery_url"]
    assert defaults["nomad_oidc_auth_method_name"] == "authentik"
    assert defaults["nomad_oidc_auth_retired_method_names"] == ["keycloak"]
    assert defaults["nomad_oidc_auth_retire_legacy_methods"] is True


def test_nomad_authentik_client_is_reconciled_with_the_native_callback_uris() -> None:
    manifest = yaml.safe_load(OAUTH_CLIENTS_PATH.read_text(encoding="utf-8"))
    client = next(item for item in manifest["clients"] if item["id"] == "nomad")

    assert client["client_secret_file"] == "authentik/nomad-client-secret.txt"
    assert client["application"]["slug"] == "nomad"
    assert client["provider"]["client_id"] == "nomad"
    assert client["provider"]["redirect_uris"] == [
        "https://scheduler.{{ platform_domain }}/ui/settings/tokens",
        "http://localhost:4649/oidc/callback",
    ]


def test_nomad_role_stages_authentik_before_retiring_only_explicit_legacy_methods() -> None:
    tasks = _tasks()
    names = [task["name"] for task in tasks]

    assert "Create the Authentik OIDC auth method" in names
    assert "Update the Authentik OIDC auth method" in names
    assert "Remove binding rules attached to retired OIDC methods" in names
    assert "Remove retired OIDC auth methods" in names
    assert "Verify retired OIDC auth methods are absent" in names
    assert names.index("Assert the OIDC auth method is active") < names.index(
        "Remove binding rules attached to retired OIDC methods"
    )

    remove_bindings = next(
        task for task in tasks if task["name"] == "Remove binding rules attached to retired OIDC methods"
    )
    remove_methods = next(task for task in tasks if task["name"] == "Remove retired OIDC auth methods")

    assert "nomad_oidc_auth_retired_method_names" in remove_bindings["when"][1]
    assert remove_methods["ansible.builtin.uri"]["method"] == "DELETE"
    assert remove_methods["when"][1] == "item.status | default(404) == 200"


def test_nomad_role_argument_spec_has_no_active_keycloak_contract() -> None:
    specs = yaml.safe_load(SPECS_PATH.read_text(encoding="utf-8"))
    options = specs["argument_specs"]["main"]["options"]

    assert "nomad_oidc_auth_authentik_client_id" in options
    assert "nomad_oidc_auth_authentik_client_secret_local_file" in options
    assert "nomad_oidc_auth_retired_method_names" in options
    assert not any("keycloak" in option for option in options)
