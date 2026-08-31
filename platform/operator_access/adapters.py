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


class AuthentikAdminAdapter:
    """Manage operator identities through Authentik's governed REST API.

    Authentik uses group UUIDs rather than realm-scoped role names.  The
    adapter therefore reconciles group membership directly and deliberately
    never overwrites an existing user's password during an ordinary roster
    sync.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_token_loader: Callable[[], str | None],
        request: RequestFunc = request_json,
    ):
        self.base_url = base_url.rstrip("/")
        self._api_token_loader = api_token_loader
        self._request = request
        self._user_cache: dict[str, dict[str, Any]] = {}

    def _headers(self) -> dict[str, str]:
        token = self._api_token_loader()
        if not token:
            raise RuntimeError(
                "Authentik admin auth failed: set LV3_AUTHENTIK_BOOTSTRAP_TOKEN or provide "
                ".local/authentik/bootstrap-token.txt."
            )
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def _url(self, path: str, query: Mapping[str, str] | None = None) -> str:
        suffix = urllib.parse.urlencode(query or {})
        return f"{self.base_url}/api/v3{path}" + (f"?{suffix}" if suffix else "")

    @staticmethod
    def _results(payload: Any, *, label: str) -> tuple[list[dict[str, Any]], int | None]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)], None
        if not isinstance(payload, dict):
            raise RuntimeError(f"Authentik {label} did not return a result object.")
        results = payload.get("results")
        if not isinstance(results, list):
            raise RuntimeError(f"Authentik {label} did not return a results list.")
        pagination = payload.get("pagination", {})
        next_page = pagination.get("next") if isinstance(pagination, dict) else None
        if next_page is None:
            return [item for item in results if isinstance(item, dict)], None
        if isinstance(next_page, bool) or not isinstance(next_page, int) or next_page < 1:
            raise RuntimeError(f"Authentik {label} returned an invalid pagination cursor.")
        return [item for item in results if isinstance(item, dict)], next_page

    def _list(self, path: str, query: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
        page = 1
        results: list[dict[str, Any]] = []
        while True:
            request_query = {"page": str(page), "page_size": "100", **dict(query or {})}
            payload = self._request(
                self._url(path, request_query), headers=self._headers(), expected_status=(200,)
            )
            batch, next_page = self._results(payload, label=path)
            results.extend(batch)
            if next_page is None:
                return results
            if next_page <= page:
                raise RuntimeError(f"Authentik {path} returned a non-advancing pagination cursor.")
            page = next_page

    @staticmethod
    def _pk(payload: Mapping[str, Any], *, label: str) -> str:
        value = payload.get("pk", payload.get("id"))
        if isinstance(value, bool) or value is None or str(value).strip() == "":
            raise RuntimeError(f"Authentik {label} did not expose a primary key.")
        return str(value)

    @staticmethod
    def _exact(items: Sequence[dict[str, Any]], *, field: str, value: str, label: str) -> dict[str, Any] | None:
        matches = [item for item in items if item.get(field) == value]
        if len(matches) > 1:
            raise RuntimeError(f"Multiple Authentik {label} objects match {field}={value!r}.")
        return matches[0] if matches else None

    def _group(self, group_name: str) -> dict[str, Any] | None:
        groups = self._list("/core/groups/", {"name": group_name})
        return self._exact(groups, field="name", value=group_name, label="group")

    def ensure_group(self, group_name: str) -> dict[str, Any]:
        group = self._group(group_name)
        if group is not None:
            return group
        created = self._request(
            self._url("/core/groups/"),
            method="POST",
            headers=self._headers(),
            body={"name": group_name},
            expected_status=(201,),
        )
        if isinstance(created, dict) and created.get("name") == group_name:
            return created
        group = self._group(group_name)
        if group is None:
            raise RuntimeError(f"Authentik group '{group_name}' could not be created or found.")
        return group

    def _user(self, username: str) -> dict[str, Any] | None:
        if username in self._user_cache:
            return self._user_cache[username]
        users = self._list("/core/users/", {"username": username, "include_groups": "true"})
        user = self._exact(users, field="username", value=username, label="user")
        if user is not None:
            self._user_cache[username] = user
        return user

    def _user_id(self, username: str) -> str:
        user = self._user(username)
        if user is None:
            raise RuntimeError(f"Authentik user '{username}' was not found.")
        return self._pk(user, label=f"user '{username}'")

    def _group_ids(self, group_names: Sequence[str]) -> list[str]:
        return [self._pk(self.ensure_group(name), label=f"group '{name}'") for name in group_names]

    def ensure_user(self, operator: Mapping[str, Any], *, bootstrap_password: str) -> dict[str, Any]:
        identity = operator["authentik"]
        if not isinstance(identity, Mapping):
            raise RuntimeError("Operator record does not contain an Authentik identity block.")
        username = str(identity["username"])
        payload = {
            "username": username,
            "name": str(operator["name"]),
            "email": str(operator["email"]),
            "is_active": bool(identity["enabled"]),
            "groups": self._group_ids([str(name) for name in identity["groups"]]),
            "type": "internal",
        }
        existing = self._user(username)
        created = existing is None
        if existing is None:
            response = self._request(
                self._url("/core/users/"),
                method="POST",
                headers=self._headers(),
                body=payload,
                expected_status=(201,),
            )
            if not isinstance(response, dict):
                raise RuntimeError(f"Authentik user '{username}' did not return a valid create response.")
            user_id = self._pk(response, label=f"user '{username}'")
            self._request(
                self._url(f"/core/users/{urllib.parse.quote(user_id, safe='')}/set_password/"),
                method="POST",
                headers=self._headers(),
                body={"password": bootstrap_password},
                expected_status=(204,),
            )
        else:
            user_id = self._pk(existing, label=f"user '{username}'")
            self._request(
                self._url(f"/core/users/{urllib.parse.quote(user_id, safe='')}/"),
                method="PATCH",
                headers=self._headers(),
                body=payload,
                expected_status=(200,),
            )
        self._user_cache.pop(username, None)
        return {
            "user_id": user_id,
            "username": username,
            "groups": list(identity["groups"]),
            "created": created,
            "password_set": created,
        }

    def disable_user(self, username: str) -> dict[str, Any]:
        user = self._user(username)
        if user is None:
            return {"status": "missing", "username": username}
        user_id = self._pk(user, label=f"user '{username}'")
        self._request(
            self._url(f"/core/users/{urllib.parse.quote(user_id, safe='')}/"),
            method="PATCH",
            headers=self._headers(),
            body={"is_active": False},
            expected_status=(200,),
        )
        self._user_cache.pop(username, None)
        return {"status": "disabled", "username": username, "user_id": user_id}

    def recover_totp(self, username: str) -> dict[str, Any]:
        user_id = self._user_id(username)
        removed_devices: list[dict[str, Any]] = []
        for device in self._list("/authenticators/admin/totp/"):
            device_user = device.get("user")
            device_user_id = (
                self._pk(device_user, label="TOTP device user") if isinstance(device_user, Mapping) else None
            )
            if device_user_id != user_id:
                continue
            device_id = self._pk(device, label="TOTP device")
            self._request(
                self._url(f"/authenticators/admin/totp/{urllib.parse.quote(device_id, safe='')}/"),
                method="DELETE",
                headers=self._headers(),
                expected_status=(204,),
            )
            removed_devices.append({"id": device_id, "name": str(device.get("name") or "")})
        return {
            "status": "totp-reset",
            "username": username,
            "user_id": user_id,
            "removed_totp_devices": removed_devices,
            "re_enrollment_required": True,
        }

    def reset_password(self, username: str, *, password: str, temporary: bool) -> dict[str, Any]:
        user_id = self._user_id(username)
        self._request(
            self._url(f"/core/users/{urllib.parse.quote(user_id, safe='')}/set_password/"),
            method="POST",
            headers=self._headers(),
            body={"password": password},
            expected_status=(204,),
        )
        self._user_cache.pop(username, None)
        return {
            "status": "password-reset",
            "username": username,
            "user_id": user_id,
            "temporary_requested": temporary,
            "temporary_enforced": False,
            "recovery_flow_required_for_forced_rotation": temporary,
        }

    def inventory_user(self, username: str, *, email_fallback: str) -> dict[str, Any]:
        user = self._user(username)
        if user is None:
            return {"status": "missing", "username": username}
        return {
            "status": "active" if user.get("is_active") else "disabled",
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
