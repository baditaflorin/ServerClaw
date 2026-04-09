#!/usr/bin/env python3
# Purpose: Idempotently configure Dify workspace SSO with a Keycloak OIDC provider.
# Use case: Called by the dify_runtime Ansible role after the stack is running.
#           Replaces the manual UI steps that were previously needed post-deployment.
# Inputs: Dify base URL, admin credentials, Keycloak OIDC settings.
# Outputs: JSON summary with the action taken (configured/already-configured/unavailable).
# Idempotency: Reads the current SSO config first and skips the POST when settings match.

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dify_api import DifyClient, DifyApiError, read_secret

_PROTOCOL = "oidc"


def _sso_matches(current: dict, client_id: str, issuer_url: str) -> bool:
    """Return True when the live SSO config already matches the desired state."""
    return (
        current.get("enabled") is True
        and current.get("type") == _PROTOCOL
        and current.get("client_id") == client_id
        and current.get("issuer_url") == issuer_url
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap Dify workspace SSO to use a Keycloak OIDC provider."
    )
    parser.add_argument("--base-url", required=True, help="Public Dify base URL (e.g. https://agents.localhost)")
    parser.add_argument("--admin-email", required=True, help="Dify admin email used to log in")
    parser.add_argument("--admin-password-file", required=True, help="Path to the Dify admin password file")
    parser.add_argument("--keycloak-client-id", required=True, help="Keycloak client ID registered for Dify")
    parser.add_argument("--keycloak-client-secret-file", required=True, help="Path to the Keycloak client secret file")
    parser.add_argument("--keycloak-issuer-url", required=True, help="Keycloak issuer URL (realm URL, e.g. https://sso.localhost/realms/lv3)")
    args = parser.parse_args()

    admin_password = read_secret(args.admin_password_file)
    client_secret = read_secret(args.keycloak_client_secret_file)

    client = DifyClient(args.base_url)
    client.login(email=args.admin_email, password=admin_password)

    current = client.get_sso_setting()
    if current is None:
        result = {
            "action": "unavailable",
            "reason": "SSO endpoint not present in this Dify version",
        }
        print(json.dumps(result, indent=2))
        return 0

    if _sso_matches(current, client_id=args.keycloak_client_id, issuer_url=args.keycloak_issuer_url):
        result = {
            "action": "already-configured",
            "type": _PROTOCOL,
            "client_id": args.keycloak_client_id,
            "issuer_url": args.keycloak_issuer_url,
        }
        print(json.dumps(result, indent=2))
        return 0

    try:
        response = client.configure_sso(
            enabled=True,
            protocol=_PROTOCOL,
            client_id=args.keycloak_client_id,
            client_secret=client_secret,
            issuer_url=args.keycloak_issuer_url,
        )
    except DifyApiError as exc:
        if "not support programmatic" in str(exc) or "not found" in str(exc).lower():
            result = {"action": "unavailable", "reason": str(exc)}
            print(json.dumps(result, indent=2))
            return 0
        raise

    result = {
        "action": "configured",
        "type": _PROTOCOL,
        "client_id": args.keycloak_client_id,
        "issuer_url": args.keycloak_issuer_url,
        "response": response,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
