from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "api_gateway_runtime"
    / "defaults"
    / "main.yml"
)


def test_api_gateway_role_uses_internal_keycloak_jwks_url() -> None:
    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")

    assert "api_gateway_keycloak_internal_base_url" in defaults
    assert "http://keycloak:8080" in defaults
    assert "api_gateway_keycloak_verify_base_url: http://127.0.0.1:18080" in defaults
    assert "api_gateway_keycloak_docker_network: keycloak_default" in defaults
    assert "/realms/lv3/protocol/openid-connect/certs" in defaults
    assert "api_gateway_ledger_event_types_src" in defaults
    assert "dest: ledger-event-types.yaml" in defaults
    assert "api_gateway_event_taxonomy_src" in defaults
    assert "dest: event-taxonomy.yaml" in defaults
