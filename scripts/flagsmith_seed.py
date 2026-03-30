#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib import error, parse, request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcile and verify repo-managed Flagsmith state.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("reconcile", "verify"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--base-url", required=True)
        subparser.add_argument("--admin-email", required=True)
        subparser.add_argument("--admin-password-file", required=True, type=Path)
        subparser.add_argument("--organisation-name", required=True)
        subparser.add_argument("--project-name", required=True)
        subparser.add_argument("--environment-spec-json", required=True)
        subparser.add_argument("--feature-spec-json", required=True)

    verify = subparsers.choices["verify"]
    verify.add_argument("--verify-boolean-feature", required=True)
    verify.add_argument("--expected-boolean-json", required=True)
    verify.add_argument("--verify-config-feature", required=True)
    verify.add_argument("--expected-config-json", required=True)
    return parser.parse_args()


def normalise_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def read_password(path: Path) -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"password file is empty: {path}")
    return value


def parse_json_argument(raw: str, argument_name: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{argument_name} must contain valid JSON") from exc


def http_json(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    environment_key: str | None = None,
    body: Any | None = None,
    query: dict[str, Any] | None = None,
    expected_status: set[int] | None = None,
) -> Any:
    url = normalise_base_url(base_url) + path
    if query:
        encoded_query = parse.urlencode({key: value for key, value in query.items() if value is not None})
        url = f"{url}?{encoded_query}"

    data: bytes | None = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Token {token}"
    if environment_key:
        headers["X-Environment-Key"] = environment_key
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")

    req = request.Request(url=url, method=method, headers=headers, data=data)
    expected = expected_status or {200}
    try:
        with request.urlopen(req, timeout=30) as response:
            status = response.getcode()
            payload = response.read()
    except error.HTTPError as exc:
        payload = exc.read()
        detail = payload.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"{method} {url} returned {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc.reason}") from exc

    if status not in expected:
        detail = payload.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"{method} {url} returned unexpected status {status}: {detail}")

    if not payload:
        return None
    return json.loads(payload.decode("utf-8"))


def get_results(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return payload["results"]
    raise RuntimeError(f"expected list or paginated result payload, got {type(payload).__name__}")


def login(base_url: str, admin_email: str, admin_password: str) -> str:
    payload = http_json(
        base_url,
        "POST",
        "/api/v1/auth/login/",
        body={"email": admin_email, "password": admin_password},
        expected_status={200},
    )
    token = payload.get("key")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Flagsmith login did not return a token key")
    return token


def list_organisations(base_url: str, token: str) -> list[dict[str, Any]]:
    return get_results(http_json(base_url, "GET", "/api/v1/organisations/", token=token))


def ensure_organisation(base_url: str, token: str, organisation_name: str) -> tuple[dict[str, Any], bool]:
    for organisation in list_organisations(base_url, token):
        if organisation.get("name") == organisation_name:
            return organisation, False
    organisation = http_json(
        base_url,
        "POST",
        "/api/v1/organisations/",
        token=token,
        body={"name": organisation_name},
        expected_status={200, 201},
    )
    return organisation, True


def list_projects(base_url: str, token: str) -> list[dict[str, Any]]:
    return get_results(http_json(base_url, "GET", "/api/v1/projects/", token=token))


def ensure_project(
    base_url: str,
    token: str,
    organisation_id: int,
    project_name: str,
) -> tuple[dict[str, Any], bool]:
    for project in list_projects(base_url, token):
        if project.get("name") == project_name and project.get("organisation") == organisation_id:
            return project, False
    project = http_json(
        base_url,
        "POST",
        "/api/v1/projects/",
        token=token,
        body={"name": project_name, "organisation": organisation_id},
        expected_status={200, 201},
    )
    return project, True


def list_environments(base_url: str, token: str) -> list[dict[str, Any]]:
    return get_results(http_json(base_url, "GET", "/api/v1/environments/", token=token))


def ensure_environment(
    base_url: str,
    token: str,
    project_id: int,
    spec: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    name = spec["name"]
    desired_allow_client_traits = bool(spec.get("allow_client_traits", True))
    for environment in list_environments(base_url, token):
        if environment.get("name") == name and environment.get("project") == project_id:
            if bool(environment.get("allow_client_traits", True)) == desired_allow_client_traits:
                return environment, False
            environment = http_json(
                base_url,
                "PATCH",
                f"/api/v1/environments/{environment['id']}/",
                token=token,
                body={"allow_client_traits": desired_allow_client_traits},
                expected_status={200},
            )
            return environment, True
    body = {
        "name": name,
        "project": project_id,
        "allow_client_traits": desired_allow_client_traits,
    }
    environment = http_json(
        base_url,
        "POST",
        "/api/v1/environments/",
        token=token,
        body=body,
        expected_status={200, 201},
    )
    return environment, True


def list_project_features(base_url: str, token: str, project_id: int) -> list[dict[str, Any]]:
    return get_results(http_json(base_url, "GET", f"/api/v1/projects/{project_id}/features/", token=token))


def ensure_feature(
    base_url: str,
    token: str,
    project_id: int,
    spec: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    name = spec["name"]
    desired_type = spec.get("type", "STANDARD")
    desired_initial_value = str(spec.get("initial_value", ""))
    desired_default_enabled = bool(spec.get("default_enabled", False))
    feature = next((item for item in list_project_features(base_url, token, project_id) if item.get("name") == name), None)
    changed = False
    if feature is None:
        feature = http_json(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/features/",
            token=token,
            body={
                "name": name,
                "type": desired_type,
                "initial_value": desired_initial_value,
                "default_enabled": desired_default_enabled,
            },
            expected_status={200, 201},
        )
        changed = True
    else:
        patch_body: dict[str, Any] = {}
        if feature.get("type") != desired_type:
            patch_body["type"] = desired_type
        if str(feature.get("initial_value", "")) != desired_initial_value:
            patch_body["initial_value"] = desired_initial_value
        if bool(feature.get("default_enabled", False)) != desired_default_enabled:
            patch_body["default_enabled"] = desired_default_enabled
        if patch_body:
            feature = http_json(
                base_url,
                "PATCH",
                f"/api/v1/projects/{project_id}/features/{feature['id']}/",
                token=token,
                body=patch_body,
                expected_status={200},
            )
            changed = True
    return feature, changed


def get_feature_state(base_url: str, token: str, environment_id: int, feature_id: int) -> dict[str, Any]:
    feature_states = get_results(
        http_json(
            base_url,
            "GET",
            "/api/v1/features/featurestates/",
            token=token,
            query={"environment": environment_id, "feature": feature_id},
        )
    )
    if len(feature_states) != 1:
        raise RuntimeError(
            f"expected one feature state for environment {environment_id} and feature {feature_id}, got {len(feature_states)}"
        )
    return feature_states[0]


def ensure_feature_state(
    base_url: str,
    token: str,
    environment: dict[str, Any],
    feature: dict[str, Any],
    override: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    feature_state = get_feature_state(base_url, token, int(environment["id"]), int(feature["id"]))
    patch_body: dict[str, Any] = {}

    desired_enabled = bool(override.get("enabled", feature.get("default_enabled", False)))
    if bool(feature_state.get("enabled", False)) != desired_enabled:
        patch_body["enabled"] = desired_enabled

    if "feature_state_value" in override:
        desired_value = override["feature_state_value"]
        current_value = feature_state.get("feature_state_value")
        if current_value != desired_value:
            patch_body["feature_state_value"] = desired_value

    if patch_body:
        feature_state = http_json(
            base_url,
            "PATCH",
            f"/api/v1/environments/{environment['api_key']}/featurestates/{feature_state['id']}/",
            token=token,
            body=patch_body,
            expected_status={200},
        )
        return feature_state, True
    return feature_state, False


def ensure_server_api_key(
    base_url: str,
    token: str,
    environment: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    key_name = f"LV3 {environment['name']} server key"
    api_keys = get_results(
        http_json(
            base_url,
            "GET",
            f"/api/v1/environments/{environment['api_key']}/api-keys/",
            token=token,
        )
    )
    for api_key in api_keys:
        if api_key.get("name") == key_name:
            if api_key.get("active") is False:
                api_key = http_json(
                    base_url,
                    "PATCH",
                    f"/api/v1/environments/{environment['api_key']}/api-keys/{api_key['id']}/",
                    token=token,
                    body={"active": True, "name": key_name},
                    expected_status={200},
                )
                return api_key, True
            return api_key, False

    api_key = http_json(
        base_url,
        "POST",
        f"/api/v1/environments/{environment['api_key']}/api-keys/",
        token=token,
        body={"name": key_name},
        expected_status={200, 201},
    )
    return api_key, True


def get_server_api_key(
    base_url: str,
    token: str,
    environment: dict[str, Any],
) -> dict[str, Any]:
    key_name = f"LV3 {environment['name']} server key"
    api_keys = get_results(
        http_json(
            base_url,
            "GET",
            f"/api/v1/environments/{environment['api_key']}/api-keys/",
            token=token,
        )
    )
    api_key = next((item for item in api_keys if item.get("name") == key_name and item.get("active") is not False), None)
    if api_key is None:
        raise RuntimeError(f"active server API key {key_name!r} was not found")
    return api_key


def sdk_get_flags(base_url: str, environment_key: str, feature_name: str) -> list[dict[str, Any]]:
    payload = http_json(
        base_url,
        "GET",
        "/api/v1/flags/",
        environment_key=environment_key,
        query={"feature": feature_name},
    )
    return get_results(payload) if isinstance(payload, dict) else payload


def sdk_get_environment_document(base_url: str, environment_key: str) -> dict[str, Any]:
    payload = http_json(
        base_url,
        "GET",
        "/api/v1/environment-document/",
        environment_key=environment_key,
    )
    if not isinstance(payload, dict):
        raise RuntimeError("environment-document response must be an object")
    return payload


def build_openbao_payload(organisation: dict[str, Any], project: dict[str, Any], environment_keys_bundle: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "organisation_id": str(organisation["id"]),
        "organisation_name": organisation["name"],
        "project_id": str(project["id"]),
        "project_name": project["name"],
    }
    for env_name, env_data in environment_keys_bundle["environments"].items():
        payload[f"{env_name}_environment_id"] = str(env_data["id"])
        payload[f"{env_name}_client_api_key"] = env_data["client_api_key"]
        payload[f"{env_name}_server_api_key"] = env_data["server_api_key"]
    return payload


def reconcile(args: argparse.Namespace) -> int:
    base_url = normalise_base_url(args.base_url)
    admin_password = read_password(args.admin_password_file)
    environment_specs = parse_json_argument(args.environment_spec_json, "--environment-spec-json")
    feature_specs = parse_json_argument(args.feature_spec_json, "--feature-spec-json")

    token = login(base_url, args.admin_email, admin_password)
    changed = False

    organisation, organisation_changed = ensure_organisation(base_url, token, args.organisation_name)
    changed = changed or organisation_changed
    project, project_changed = ensure_project(base_url, token, int(organisation["id"]), args.project_name)
    changed = changed or project_changed

    environments_by_name: dict[str, dict[str, Any]] = {}
    environment_keys: dict[str, dict[str, Any]] = {}
    for spec in environment_specs:
        environment, environment_changed = ensure_environment(base_url, token, int(project["id"]), spec)
        changed = changed or environment_changed
        environments_by_name[environment["name"]] = environment

        server_api_key, server_key_changed = ensure_server_api_key(base_url, token, environment)
        changed = changed or server_key_changed
        environment_keys[environment["name"]] = {
            "id": int(environment["id"]),
            "client_api_key": environment["api_key"],
            "server_api_key": server_api_key["key"],
        }

    features_summary: dict[str, Any] = {}
    for spec in feature_specs:
        feature, feature_changed = ensure_feature(base_url, token, int(project["id"]), spec)
        changed = changed or feature_changed
        environment_states: dict[str, Any] = {}
        overrides = spec.get("environment_overrides", {})
        for environment_name, environment in environments_by_name.items():
            override = overrides.get(environment_name, {})
            feature_state, state_changed = ensure_feature_state(base_url, token, environment, feature, override)
            changed = changed or state_changed
            environment_states[environment_name] = {
                "id": int(feature_state["id"]),
                "enabled": bool(feature_state.get("enabled", False)),
                "feature_state_value": feature_state.get("feature_state_value"),
            }
        features_summary[feature["name"]] = {
            "id": int(feature["id"]),
            "type": feature.get("type"),
            "default_enabled": bool(feature.get("default_enabled", False)),
            "initial_value": feature.get("initial_value"),
            "environment_states": environment_states,
        }

    environment_keys_bundle = {
        "organisation": {"id": int(organisation["id"]), "name": organisation["name"]},
        "project": {"id": int(project["id"]), "name": project["name"]},
        "environments": environment_keys,
    }
    output = {
        "changed": changed,
        "organisation": environment_keys_bundle["organisation"],
        "project": environment_keys_bundle["project"],
        "environment_keys_bundle": environment_keys_bundle,
        "openbao_payload": build_openbao_payload(organisation, project, environment_keys_bundle),
        "features": features_summary,
    }
    json.dump(output, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def verify(args: argparse.Namespace) -> int:
    base_url = normalise_base_url(args.base_url)
    admin_password = read_password(args.admin_password_file)
    environment_specs = parse_json_argument(args.environment_spec_json, "--environment-spec-json")
    feature_specs = parse_json_argument(args.feature_spec_json, "--feature-spec-json")
    expected_boolean = parse_json_argument(args.expected_boolean_json, "--expected-boolean-json")
    expected_config = parse_json_argument(args.expected_config_json, "--expected-config-json")

    token = login(base_url, args.admin_email, admin_password)
    organisations = list_organisations(base_url, token)
    organisation = next((item for item in organisations if item.get("name") == args.organisation_name), None)
    if organisation is None:
        raise RuntimeError(f"organisation {args.organisation_name!r} was not found")

    projects = list_projects(base_url, token)
    project = next(
        (item for item in projects if item.get("name") == args.project_name and item.get("organisation") == organisation["id"]),
        None,
    )
    if project is None:
        raise RuntimeError(f"project {args.project_name!r} was not found")

    environments_by_name: dict[str, dict[str, Any]] = {}
    for environment in list_environments(base_url, token):
        if environment.get("project") == project["id"]:
            environments_by_name[environment["name"]] = environment

    for spec in environment_specs:
        if spec["name"] not in environments_by_name:
            raise RuntimeError(f"environment {spec['name']!r} was not found")

    features_by_name: dict[str, dict[str, Any]] = {}
    for feature in list_project_features(base_url, token, int(project["id"])):
        features_by_name[feature["name"]] = feature

    for spec in feature_specs:
        feature = features_by_name.get(spec["name"])
        if feature is None:
            raise RuntimeError(f"feature {spec['name']!r} was not found")
        expected_default_enabled = bool(spec.get("default_enabled", False))
        expected_initial_value = str(spec.get("initial_value", ""))
        actual_default_enabled = bool(feature.get("default_enabled", False))
        actual_initial_value = str(feature.get("initial_value", ""))
        if actual_default_enabled != expected_default_enabled:
            raise RuntimeError(
                f"feature {spec['name']!r} has default_enabled={actual_default_enabled}, expected {expected_default_enabled}"
            )
        if actual_initial_value != expected_initial_value:
            raise RuntimeError(
                f"feature {spec['name']!r} has initial_value={actual_initial_value!r}, expected {expected_initial_value!r}"
            )
        overrides = spec.get("environment_overrides", {})
        for environment_name, override in overrides.items():
            environment = environments_by_name[environment_name]
            feature_state = get_feature_state(base_url, token, int(environment["id"]), int(feature["id"]))
            expected_enabled = bool(override.get("enabled", feature.get("default_enabled", False)))
            actual_enabled = bool(feature_state.get("enabled", False))
            if actual_enabled != expected_enabled:
                raise RuntimeError(
                    f"feature {spec['name']!r} in environment {environment_name!r} has enabled={actual_enabled}, expected {expected_enabled}"
                )
            if "feature_state_value" in override:
                actual_value = feature_state.get("feature_state_value")
                if actual_value != override["feature_state_value"]:
                    raise RuntimeError(
                        f"feature {spec['name']!r} in environment {environment_name!r} has value={actual_value!r}, expected {override['feature_state_value']!r}"
                    )

    boolean_results: dict[str, bool] = {}
    config_results: dict[str, Any] = {}
    for environment_name, expected_enabled in expected_boolean.items():
        environment = environments_by_name[environment_name]
        server_api_key = get_server_api_key(base_url, token, environment)
        flags = sdk_get_flags(base_url, server_api_key["key"], args.verify_boolean_feature)
        if len(flags) != 1:
            raise RuntimeError(
                f"expected one SDK flag response for {args.verify_boolean_feature!r} in environment {environment_name!r}"
            )
        actual_enabled = bool(flags[0]["enabled"])
        if actual_enabled != bool(expected_enabled):
            raise RuntimeError(
                f"SDK flag {args.verify_boolean_feature!r} in environment {environment_name!r} returned enabled={actual_enabled}, expected {expected_enabled}"
            )
        boolean_results[environment_name] = actual_enabled

    for environment_name, expected_value in expected_config.items():
        environment = environments_by_name[environment_name]
        server_api_key = get_server_api_key(base_url, token, environment)
        feature = features_by_name[args.verify_config_feature]
        feature_state = get_feature_state(base_url, token, int(environment["id"]), int(feature["id"]))
        actual_value = feature_state.get("feature_state_value")
        if actual_value in (None, ""):
            actual_value = feature.get("initial_value")
        if actual_value != expected_value:
            raise RuntimeError(
                f"feature {args.verify_config_feature!r} in environment {environment_name!r} resolved to {actual_value!r}, expected {expected_value!r}"
            )
        sdk_get_environment_document(base_url, server_api_key["key"])
        config_results[environment_name] = actual_value

    output = {
        "healthy": True,
        "organisation_id": int(organisation["id"]),
        "project_id": int(project["id"]),
        "boolean_results": boolean_results,
        "config_results": config_results,
        "environment_names": sorted(environments_by_name),
    }
    json.dump(output, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def main() -> int:
    args = parse_args()
    try:
        if args.command == "reconcile":
            return reconcile(args)
        return verify(args)
    except Exception as exc:  # pragma: no cover - exercised through CLI behaviour
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
