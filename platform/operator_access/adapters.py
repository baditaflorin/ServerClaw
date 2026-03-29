from __future__ import annotations

import subprocess
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .http import request_json

RequestFunc = Callable[..., Any]


def _split_name(name: str) -> tuple[str, str]:
    if " " not in name:
        return name, name
    first, last = name.split(" ", 1)
    return first, last


class KeycloakAdminAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        realm: str,
        bootstrap_admin: str,
        bootstrap_password_loader: Callable[[], str | None],
        request: RequestFunc = request_json,
    ):
        self.base_url = base_url.rstrip("/")
        self.realm = realm
        self.bootstrap_admin = bootstrap_admin
        self._bootstrap_password_loader = bootstrap_password_loader
        self._request = request
        self._token: str | None = None
        self._user_cache: dict[str, dict[str, Any]] = {}

    def _admin_token(self) -> str:
        if self._token is not None:
            return self._token
        password = self._bootstrap_password_loader()
        if not password:
            raise RuntimeError("Keycloak bootstrap admin password is not configured.")
        payload = self._request(
            f"{self.base_url}/realms/master/protocol/openid-connect/token",
            method="POST",
            form={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": self.bootstrap_admin,
                "password": password,
            },
        )
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise RuntimeError("Keycloak did not return an access token for the bootstrap admin.")
        self._token = access_token
        return access_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._admin_token()}"}

    def _role_url(self, role_name: str) -> str:
        return (
            f"{self.base_url}/admin/realms/{self.realm}/roles/"
            f"{urllib.parse.quote(role_name, safe='')}"
        )

    def ensure_role(self, role_name: str, *, description: str) -> dict[str, Any]:
        url = self._role_url(role_name)
        try:
            payload = self._request(url, headers=self._headers(), expected_status=(200,))
        except RuntimeError:
            self._request(
                f"{self.base_url}/admin/realms/{self.realm}/roles",
                method="POST",
                headers=self._headers(),
                body={"name": role_name, "description": description},
                expected_status=(201, 204),
            )
            payload = self._request(url, headers=self._headers(), expected_status=(200,))
        if not isinstance(payload, dict):
            raise RuntimeError(f"Keycloak role '{role_name}' did not return an object.")
        return payload

    def ensure_group(self, group_name: str) -> dict[str, Any]:
        search_url = (
            f"{self.base_url}/admin/realms/{self.realm}/groups"
            f"?search={urllib.parse.quote(group_name, safe='')}"
        )
        groups = self._request(search_url, headers=self._headers(), expected_status=(200,))
        if isinstance(groups, list):
            for group in groups:
                if isinstance(group, dict) and group.get("name") == group_name:
                    return group
        self._request(
            f"{self.base_url}/admin/realms/{self.realm}/groups",
            method="POST",
            headers=self._headers(),
            body={"name": group_name},
            expected_status=(201, 204),
        )
        groups = self._request(search_url, headers=self._headers(), expected_status=(200,))
        if isinstance(groups, list):
            for group in groups:
                if isinstance(group, dict) and group.get("name") == group_name:
                    return group
        raise RuntimeError(f"Keycloak group '{group_name}' could not be created or found.")

    def _user(self, username: str) -> dict[str, Any] | None:
        if username in self._user_cache:
            return self._user_cache[username]
        url = (
            f"{self.base_url}/admin/realms/{self.realm}/users"
            f"?username={urllib.parse.quote(username, safe='')}&exact=true"
        )
        users = self._request(url, headers=self._headers(), expected_status=(200,))
        if isinstance(users, list):
            for user in users:
                if isinstance(user, dict) and user.get("username") == username:
                    self._user_cache[username] = user
                    return user
        return None

    def _user_id(self, username: str) -> str:
        user = self._user(username)
        if user is None:
            raise RuntimeError(f"Keycloak user '{username}' was not found.")
        user_id = user.get("id")
        if not isinstance(user_id, str) or not user_id:
            raise RuntimeError(f"Keycloak user '{username}' does not expose an id.")
        return user_id

    def _user_details(self, username: str) -> dict[str, Any]:
        payload = self._request(
            f"{self.base_url}/admin/realms/{self.realm}/users/{self._user_id(username)}",
            headers=self._headers(),
            expected_status=(200,),
        )
        if not isinstance(payload, dict):
            raise RuntimeError(f"Keycloak user '{username}' did not return a valid detail payload.")
        return payload

    def _user_credentials(self, username: str) -> list[dict[str, Any]]:
        payload = self._request(
            f"{self.base_url}/admin/realms/{self.realm}/users/{self._user_id(username)}/credentials",
            headers=self._headers(),
            expected_status=(200,),
        )
        if not isinstance(payload, list):
            raise RuntimeError(f"Keycloak credentials for '{username}' did not return a list.")
        return [entry for entry in payload if isinstance(entry, dict)]

    def ensure_user(self, operator: Mapping[str, Any], *, bootstrap_password: str) -> dict[str, Any]:
        username = str(operator["keycloak"]["username"])
        first_name, last_name = _split_name(str(operator["name"]))
        payload = {
            "username": username,
            "firstName": first_name,
            "lastName": last_name,
            "email": str(operator["email"]),
            "enabled": bool(operator["keycloak"]["enabled"]),
            "emailVerified": True,
            "requiredActions": ["UPDATE_PASSWORD", "CONFIGURE_TOTP"],
            "credentials": [
                {
                    "type": "password",
                    "value": bootstrap_password,
                    "temporary": True,
                }
            ],
            "groups": list(operator["keycloak"]["groups"]),
        }
        existing = self._user(username)
        if existing is None:
            self._request(
                f"{self.base_url}/admin/realms/{self.realm}/users",
                method="POST",
                headers=self._headers(),
                body=payload,
                expected_status=(201, 204),
            )
        else:
            self._request(
                f"{self.base_url}/admin/realms/{self.realm}/users/{self._user_id(username)}",
                method="PUT",
                headers=self._headers(),
                body=payload,
                expected_status=(204,),
            )
        self._user_cache.pop(username, None)
        user_id = self._user_id(username)
        role_representations = [
            self.ensure_role(role_name, description=f"Repo-managed operator role {role_name}.")
            for role_name in operator["keycloak"]["realm_roles"]
        ]
        self._request(
            f"{self.base_url}/admin/realms/{self.realm}/users/{user_id}/role-mappings/realm",
            method="POST",
            headers=self._headers(),
            body=role_representations,
            expected_status=(204,),
        )
        return {
            "user_id": user_id,
            "username": username,
            "realm_roles": list(operator["keycloak"]["realm_roles"]),
        }

    def disable_user(self, username: str) -> dict[str, Any]:
        if self._user(username) is None:
            return {"status": "missing", "username": username}
        details = self._user_details(username)
        details["enabled"] = False
        self._request(
            f"{self.base_url}/admin/realms/{self.realm}/users/{self._user_id(username)}",
            method="PUT",
            headers=self._headers(),
            body=details,
            expected_status=(204,),
        )
        self._user_cache.pop(username, None)
        return {"status": "disabled", "username": username, "user_id": self._user_id(username)}

    def recover_totp(self, username: str) -> dict[str, Any]:
        user_id = self._user_id(username)
        details = self._user_details(username)
        removed_credentials: list[dict[str, str]] = []
        for credential in self._user_credentials(username):
            if credential.get("type") != "otp":
                continue
            credential_id = credential.get("id")
            if not isinstance(credential_id, str) or not credential_id:
                continue
            self._request(
                f"{self.base_url}/admin/realms/{self.realm}/users/{user_id}/credentials/{credential_id}",
                method="DELETE",
                headers=self._headers(),
                expected_status=(200, 204),
            )
            removed_credentials.append(
                {
                    "id": credential_id,
                    "userLabel": str(credential.get("userLabel") or ""),
                }
            )

        required_actions = details.get("requiredActions")
        if not isinstance(required_actions, list):
            required_actions = []
        normalized_required_actions = [str(action) for action in required_actions if str(action).strip()]
        if "CONFIGURE_TOTP" not in normalized_required_actions:
            normalized_required_actions.append("CONFIGURE_TOTP")
        details["requiredActions"] = normalized_required_actions
        self._request(
            f"{self.base_url}/admin/realms/{self.realm}/users/{user_id}",
            method="PUT",
            headers=self._headers(),
            body=details,
            expected_status=(204,),
        )
        self._request(
            f"{self.base_url}/admin/realms/{self.realm}/attack-detection/brute-force/users/{user_id}",
            method="DELETE",
            headers=self._headers(),
            expected_status=(200, 204),
        )
        self._user_cache.pop(username, None)
        return {
            "status": "totp-reset",
            "username": username,
            "user_id": user_id,
            "removed_otp_credentials": removed_credentials,
            "required_actions": normalized_required_actions,
            "failure_counters_cleared": True,
        }

    def reset_password(self, username: str, *, password: str, temporary: bool) -> dict[str, Any]:
        user_id = self._user_id(username)
        details = self._user_details(username)
        self._request(
            f"{self.base_url}/admin/realms/{self.realm}/users/{user_id}/reset-password",
            method="PUT",
            headers=self._headers(),
            body={"type": "password", "temporary": temporary, "value": password},
            expected_status=(204,),
        )
        required_actions = details.get("requiredActions")
        if not isinstance(required_actions, list):
            required_actions = []
        normalized_required_actions = [str(action) for action in required_actions if str(action).strip()]
        if temporary and "UPDATE_PASSWORD" not in normalized_required_actions:
            normalized_required_actions.append("UPDATE_PASSWORD")
        details["requiredActions"] = normalized_required_actions
        self._request(
            f"{self.base_url}/admin/realms/{self.realm}/users/{user_id}",
            method="PUT",
            headers=self._headers(),
            body=details,
            expected_status=(204,),
        )
        self._request(
            f"{self.base_url}/admin/realms/{self.realm}/attack-detection/brute-force/users/{user_id}",
            method="DELETE",
            headers=self._headers(),
            expected_status=(200, 204),
        )
        self._user_cache.pop(username, None)
        return {
            "status": "password-reset",
            "username": username,
            "user_id": user_id,
            "temporary": temporary,
            "required_actions": normalized_required_actions,
            "failure_counters_cleared": True,
        }

    def inventory_user(self, username: str, *, email_fallback: str) -> dict[str, Any]:
        user = self._user(username)
        if user is None:
            return {"status": "missing", "username": username}
        return {
            "status": "active" if user.get("enabled") else "disabled",
            "username": username,
            "email": user.get("email", email_fallback),
        }


class OpenBaoIdentityAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        root_token_loader: Callable[[], str],
        request: RequestFunc = request_json,
    ):
        self.base_url = base_url.rstrip("/")
        self._root_token_loader = root_token_loader
        self._request = request
        self._root_token: str | None = None

    def _headers(self) -> dict[str, str]:
        if self._root_token is None:
            self._root_token = self._root_token_loader()
        return {"X-Vault-Token": self._root_token}

    def ensure_policy(self, policy_name: str, document: str) -> str:
        self._request(
            f"{self.base_url}/v1/sys/policies/acl/{urllib.parse.quote(policy_name, safe='')}",
            method="PUT",
            headers=self._headers(),
            body={"policy": document},
            expected_status=(200, 204),
        )
        return "upserted"

    def ensure_entity(self, operator: Mapping[str, Any]) -> dict[str, Any]:
        entity_name = str(operator["openbao"]["entity_name"])
        payload = {
            "policies": list(operator["openbao"]["policies"]),
            "metadata": {
                "email": str(operator["email"]),
                "role": str(operator["role"]),
                "status": str(operator["status"]),
                "operator_id": str(operator["id"]),
            },
            "disabled": str(operator["status"]) != "active",
        }
        self._request(
            f"{self.base_url}/v1/identity/entity/name/{urllib.parse.quote(entity_name, safe='')}",
            method="POST",
            headers=self._headers(),
            body=payload,
            expected_status=(200, 204),
        )
        current = self._request(
            f"{self.base_url}/v1/identity/entity/name/{urllib.parse.quote(entity_name, safe='')}",
            headers=self._headers(),
            expected_status=(200,),
        )
        entity = current.get("data", {}) if isinstance(current, dict) else {}
        return {
            "entity_name": entity_name,
            "entity_id": entity.get("id", ""),
            "policies": list(operator["openbao"]["policies"]),
            "disabled": payload["disabled"],
        }

    def inventory_entity(self, entity_name: str, *, policies_fallback: Sequence[str]) -> dict[str, Any]:
        current = self._request(
            f"{self.base_url}/v1/identity/entity/name/{urllib.parse.quote(entity_name, safe='')}",
            headers=self._headers(),
            expected_status=(200, 404),
        )
        if not isinstance(current, dict) or "data" not in current:
            return {
                "status": "missing",
                "entity_name": entity_name,
                "entity_id": "",
                "policies": list(policies_fallback),
            }
        entity = current.get("data", {})
        return {
            "status": "disabled" if entity.get("disabled") else "active",
            "entity_name": entity_name,
            "entity_id": entity.get("id", ""),
            "policies": entity.get("policies", list(policies_fallback)),
        }


class StepCACommandAdapter:
    def __init__(
        self,
        *,
        register_command_template: str,
        revoke_command_template: str,
        state_dir: Path,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ):
        self.register_command_template = register_command_template.strip()
        self.revoke_command_template = revoke_command_template.strip()
        self.state_dir = state_dir
        self._runner = runner

    def register_principal(self, operator: Mapping[str, Any], *, enabled: bool) -> dict[str, Any]:
        principal = str(operator["ssh"]["principal"])
        if not enabled:
            return {
                "status": "skipped",
                "reason": f"role '{operator['role']}' does not receive SSH access",
                "principal": principal,
            }
        if not self.register_command_template:
            return {
                "status": "skipped",
                "reason": "LV3_STEP_CA_SSH_REGISTER_COMMAND is not configured",
                "principal": principal,
            }
        public_key = str(operator["ssh"]["public_keys"][0]["public_key"])
        temp_key = self.state_dir / f"{operator['id']}.pub"
        temp_key.parent.mkdir(parents=True, exist_ok=True)
        temp_key.write_text(public_key + "\n", encoding="utf-8")
        try:
            command = self.register_command_template.format(principal=principal, public_key_path=str(temp_key))
            result = self._runner(command, shell=True, text=True, capture_output=True, check=False)
        finally:
            temp_key.unlink(missing_ok=True)
        return {
            "status": "ok" if result.returncode == 0 else "error",
            "principal": principal,
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }

    def revoke_principal(self, operator: Mapping[str, Any], *, enabled: bool) -> dict[str, Any]:
        principal = str(operator["ssh"]["principal"])
        if not enabled:
            return {
                "status": "skipped",
                "reason": f"role '{operator['role']}' does not receive SSH access",
                "principal": principal,
            }
        if not self.revoke_command_template:
            return {
                "status": "skipped",
                "reason": "LV3_STEP_CA_SSH_REVOKE_COMMAND is not configured",
                "principal": principal,
            }
        command = self.revoke_command_template.format(principal=principal)
        result = self._runner(command, shell=True, text=True, capture_output=True, check=False)
        return {
            "status": "ok" if result.returncode == 0 else "error",
            "principal": principal,
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }


class TailscaleApiAdapter:
    def __init__(
        self,
        *,
        api_key_loader: Callable[[], str | None],
        tailnet_loader: Callable[[], str | None],
        invite_endpoint_loader: Callable[[], str],
        request: RequestFunc = request_json,
    ):
        self._api_key_loader = api_key_loader
        self._tailnet_loader = tailnet_loader
        self._invite_endpoint_loader = invite_endpoint_loader
        self._request = request

    def _headers(self) -> dict[str, str]:
        api_key = self._api_key_loader()
        if not api_key:
            raise RuntimeError(
                "Tailscale API key is not configured. Set TAILSCALE_API_KEY or create .local/tailscale/api-key.txt."
            )
        return {"Authorization": f"Bearer {api_key}"}

    def _devices(self) -> list[dict[str, Any]]:
        tailnet = self._tailnet_loader()
        if not tailnet:
            raise RuntimeError("TAILSCALE_TAILNET is not configured.")
        response = self._request(
            f"https://api.tailscale.com/api/v2/tailnet/{urllib.parse.quote(tailnet, safe='')}/devices",
            headers=self._headers(),
            expected_status=(200,),
        )
        devices = response.get("devices", response if isinstance(response, list) else [])
        if not isinstance(devices, list):
            raise RuntimeError("Tailscale devices response did not contain a list.")
        return [device for device in devices if isinstance(device, dict)]

    def invite(self, operator: Mapping[str, Any]) -> dict[str, Any]:
        tailnet = self._tailnet_loader()
        endpoint = self._invite_endpoint_loader()
        login_email = str(operator["tailscale"]["login_email"])
        if not tailnet or not endpoint:
            return {
                "status": "skipped",
                "reason": "TAILSCALE_TAILNET or LV3_TAILSCALE_INVITE_ENDPOINT is not configured",
                "login_email": login_email,
            }
        payload = {
            "email": login_email,
            "tags": list(operator["tailscale"]["tags"]),
        }
        invite = self._request(
            endpoint.format(tailnet=tailnet),
            method="POST",
            headers=self._headers(),
            body=payload,
            expected_status=(200, 201, 202),
        )
        return {
            "status": "ok",
            "login_email": login_email,
            "invite": invite,
        }

    def remove(self, operator: Mapping[str, Any]) -> dict[str, Any]:
        login_email = str(operator["tailscale"]["login_email"])
        if not self._api_key_loader() or not self._tailnet_loader():
            return {
                "status": "skipped",
                "reason": "TAILSCALE_API_KEY or TAILSCALE_TAILNET is not configured",
                "login_email": login_email,
            }
        devices = self._devices()
        device_name = operator["tailscale"].get("device_name")
        device_id = operator["tailscale"].get("device_id")
        matches = [
            device
            for device in devices
            if (device_id and device.get("id") == device_id)
            or (device_name and device.get("hostname") == device_name)
            or device.get("user") == login_email
        ]
        deleted_ids: list[str] = []
        for device in matches:
            candidate_id = device.get("id")
            if not isinstance(candidate_id, str) or not candidate_id:
                continue
            self._request(
                f"https://api.tailscale.com/api/v2/device/{urllib.parse.quote(candidate_id, safe='')}",
                method="DELETE",
                headers=self._headers(),
                expected_status=(200, 202, 204),
            )
            deleted_ids.append(candidate_id)
        return {"status": "ok", "deleted_device_ids": deleted_ids}

    def inventory(self, operator: Mapping[str, Any]) -> dict[str, Any]:
        login_email = str(operator["tailscale"]["login_email"])
        try:
            devices = self._devices()
        except RuntimeError as exc:
            return {"status": "unavailable", "reason": str(exc)}
        matches = [
            device
            for device in devices
            if device.get("id") == operator["tailscale"].get("device_id")
            or device.get("hostname") == operator["tailscale"].get("device_name")
            or device.get("user") == login_email
        ]
        if not matches:
            return {"status": "absent", "login_email": login_email}
        return {
            "status": "connected",
            "devices": [
                {
                    "id": match.get("id", ""),
                    "hostname": match.get("hostname", ""),
                    "last_seen": match.get("lastSeen", ""),
                    "addresses": match.get("addresses", []),
                }
                for match in matches
            ],
        }


class MattermostWebhookAdapter:
    def __init__(
        self,
        *,
        webhook_loader: Callable[[], str | None],
        request: RequestFunc = request_json,
    ):
        self._webhook_loader = webhook_loader
        self._request = request

    def post_text(self, text: str) -> dict[str, Any]:
        webhook = self._webhook_loader()
        if not webhook:
            return {"status": "skipped", "reason": "LV3_MATTERMOST_WEBHOOK is not configured"}
        self._request(webhook, method="POST", body={"text": text}, expected_status=(200,))
        return {"status": "ok"}
