from __future__ import annotations

from typing import Any


DELIVERY_MODE_BY_EXPOSURE = {
    "edge-published": "shared-edge",
    "informational-only": "informational-edge",
    "private-only": "private-network",
}

ACCESS_MODEL_BY_AUTH_REQUIREMENT = {
    "none": "open",
    "edge_oidc": "platform-sso",
    "upstream_auth": "upstream-auth",
    "private_network": "private-network",
}


def publication_delivery_model(exposure: str) -> str:
    try:
        return DELIVERY_MODE_BY_EXPOSURE[exposure]
    except KeyError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"unsupported publication exposure '{exposure}'") from exc


def publication_access_model(auth_requirement: str) -> str:
    try:
        return ACCESS_MODEL_BY_AUTH_REQUIREMENT[auth_requirement]
    except KeyError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"unsupported publication auth requirement '{auth_requirement}'") from exc


def publication_audience(*, exposure: str, auth_requirement: str) -> str:
    access_model = publication_access_model(auth_requirement)
    if access_model == "private-network":
        return "private-network"
    if access_model in {"platform-sso", "upstream-auth"}:
        return "operator"
    if exposure == "informational-only":
        return "public"
    return "public"


def registry_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries = payload.get("publications")
    if isinstance(entries, list):
        return entries
    legacy = payload.get("subdomains")
    if isinstance(legacy, list):
        return legacy
    return []
