from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence


class IdentityDirectoryPort(Protocol):
    def ensure_role(self, role_name: str, *, description: str) -> dict[str, Any]:
        ...

    def ensure_group(self, group_name: str) -> dict[str, Any]:
        ...

    def ensure_user(self, operator: Mapping[str, Any], *, bootstrap_password: str) -> dict[str, Any]:
        ...

    def disable_user(self, username: str) -> dict[str, Any]:
        ...

    def recover_totp(self, username: str) -> dict[str, Any]:
        ...

    def reset_password(self, username: str, *, password: str, temporary: bool) -> dict[str, Any]:
        ...

    def inventory_user(self, username: str, *, email_fallback: str) -> dict[str, Any]:
        ...


class SecretAuthorityPort(Protocol):
    def ensure_policy(self, policy_name: str, document: str) -> str:
        ...

    def ensure_entity(self, operator: Mapping[str, Any]) -> dict[str, Any]:
        ...

    def inventory_entity(self, entity_name: str, *, policies_fallback: Sequence[str]) -> dict[str, Any]:
        ...


class SSHCertificateRegistryPort(Protocol):
    def register_principal(self, operator: Mapping[str, Any], *, enabled: bool) -> dict[str, Any]:
        ...

    def revoke_principal(self, operator: Mapping[str, Any], *, enabled: bool) -> dict[str, Any]:
        ...


class MeshNetworkPort(Protocol):
    def invite(self, operator: Mapping[str, Any]) -> dict[str, Any]:
        ...

    def remove(self, operator: Mapping[str, Any]) -> dict[str, Any]:
        ...

    def inventory(self, operator: Mapping[str, Any]) -> dict[str, Any]:
        ...


class NotificationPort(Protocol):
    def post_text(self, text: str) -> dict[str, Any]:
        ...
