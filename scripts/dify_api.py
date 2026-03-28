#!/usr/bin/env python3

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


class DifyApiError(RuntimeError):
    pass


def read_secret(path: str | Path) -> str:
    return Path(path).expanduser().read_text(encoding="utf-8").strip()


@dataclass
class DifyClient:
    base_url: str
    timeout_seconds: int = 30

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        self.session = requests.Session()

    def _cookie(self, name: str) -> str | None:
        for candidate in (name, f"__Host-{name}"):
            value = self.session.cookies.get(candidate)
            if value:
                return value
        return None

    def _headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        payload = {"Accept": "application/json"}
        access_token = self._cookie("access_token")
        csrf_token = self._cookie("csrf_token")
        if access_token:
            payload["Authorization"] = f"Bearer {access_token}"
        if csrf_token:
            payload["X-CSRF-Token"] = csrf_token
        if self.base_url.startswith("http://"):
            cookie_header = "; ".join(
                f"{cookie.name}={cookie.value}"
                for cookie in self.session.cookies
                if cookie.name in {"access_token", "__Host-access_token", "refresh_token", "__Host-refresh_token", "csrf_token", "__Host-csrf_token"}
            )
            if cookie_header:
                payload["Cookie"] = cookie_header
        if headers:
            payload.update(headers)
        return payload

    @staticmethod
    def _encode_field(value: str) -> str:
        return base64.b64encode(value.encode("utf-8")).decode("ascii")

    def _request(
        self,
        method: str,
        path: str,
        *,
        expected_status: int | tuple[int, ...] = 200,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        expected = (expected_status,) if isinstance(expected_status, int) else expected_status
        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            timeout=self.timeout_seconds,
            headers=self._headers(headers),
            **kwargs,
        )
        if response.status_code not in expected:
            detail = response.text.strip()
            raise DifyApiError(f"{method} {path} returned {response.status_code}: {detail}")
        return response

    def setup_status(self) -> dict[str, Any]:
        return self._request("GET", "/console/api/setup").json()

    def init_status(self) -> dict[str, Any]:
        return self._request("GET", "/console/api/init").json()

    def validate_init_password(self, password: str) -> dict[str, Any]:
        return self._request("POST", "/console/api/init", expected_status=201, json={"password": password}).json()

    def setup(
        self,
        *,
        email: str,
        name: str,
        password: str,
        init_password: str | None = None,
        language: str = "en-US",
    ) -> dict[str, Any]:
        setup_status = self.setup_status()
        if setup_status.get("step") == "finished":
            return setup_status
        if init_password:
            init_status = self.init_status()
            if init_status.get("status") != "finished":
                self.validate_init_password(init_password)
        return self._request(
            "POST",
            "/console/api/setup",
            expected_status=201,
            json={"email": email, "name": name, "password": password, "language": language},
        ).json()

    def login(self, *, email: str, password: str, remember_me: bool = True) -> dict[str, Any]:
        return self._request(
            "POST",
            "/console/api/login",
            json={"email": email, "password": self._encode_field(password), "remember_me": remember_me},
        ).json()

    def list_apps(self, *, name: str | None = None, mode: str = "all", page: int = 1, limit: int = 100) -> list[dict[str, Any]]:
        response = self._request(
            "GET",
            "/console/api/apps",
            params={"page": page, "limit": limit, "mode": mode, "name": name or ""},
        ).json()
        data = response.get("data") or response.get("items") or []
        if not isinstance(data, list):
            raise DifyApiError("unexpected apps payload from Dify")
        return data

    def find_app_by_name(self, name: str) -> dict[str, Any] | None:
        for app in self.list_apps(name=name):
            if app.get("name") == name:
                return app
        return None

    def create_app(
        self,
        *,
        name: str,
        mode: str = "workflow",
        description: str = "",
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/console/api/apps",
            expected_status=(200, 201),
            json={"name": name, "mode": mode, "description": description},
        ).json()

    def import_yaml(
        self,
        *,
        yaml_content: str,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"mode": "yaml-content", "yaml_content": yaml_content}
        if name:
            payload["name"] = name
        if description:
            payload["description"] = description
        return self._request("POST", "/console/api/apps/imports", expected_status=(200, 202), json=payload).json()

    def confirm_import(self, import_id: str) -> dict[str, Any]:
        return self._request("POST", f"/console/api/apps/imports/{import_id}/confirm").json()

    def export_app(self, app_id: str, *, include_secret: bool = False) -> str:
        payload = self._request(
            "GET",
            f"/console/api/apps/{app_id}/export",
            params={"include_secret": str(include_secret).lower()},
        ).json()
        data = payload.get("data")
        if not isinstance(data, str) or not data.strip():
            raise DifyApiError(f"unexpected export payload for app {app_id}")
        return data

    def get_trace_config(self, app_id: str, *, provider: str = "langfuse") -> dict[str, Any]:
        return self._request(
            "GET",
            f"/console/api/apps/{app_id}/trace-config",
            params={"tracing_provider": provider},
        ).json()

    def upsert_trace_config(self, app_id: str, *, provider: str, config: dict[str, Any]) -> dict[str, Any]:
        current = self.get_trace_config(app_id, provider=provider)
        if current.get("has_not_configured"):
            return self._request(
                "POST",
                f"/console/api/apps/{app_id}/trace-config",
                expected_status=(200, 201),
                json={"tracing_provider": provider, "tracing_config": config},
            ).json()
        return self._request(
            "PATCH",
            f"/console/api/apps/{app_id}/trace-config",
            json={"tracing_provider": provider, "tracing_config": config},
        ).json()

    def get_api_tool_provider(self, provider_name: str) -> dict[str, Any] | None:
        response = self.session.get(
            f"{self.base_url}/console/api/workspaces/current/tool-provider/api/get",
            params={"provider": provider_name},
            timeout=self.timeout_seconds,
            headers=self._headers(),
        )
        if response.status_code == 400 and "not added provider" in response.text:
            return None
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise DifyApiError(
                f"GET /console/api/workspaces/current/tool-provider/api/get returned {response.status_code}: {response.text.strip()}"
            )
        return response.json()

    def add_api_tool_provider(
        self,
        *,
        provider_name: str,
        schema: dict[str, Any],
        credentials: dict[str, Any],
        icon: dict[str, Any] | None = None,
        labels: list[str] | None = None,
        custom_disclaimer: str = "",
        privacy_policy: str = "",
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/console/api/workspaces/current/tool-provider/api/add",
            json={
                "provider": provider_name,
                "schema_type": "openapi",
                "schema": json.dumps(schema, indent=2),
                "credentials": credentials,
                "icon": icon or {},
                "labels": labels or [],
                "custom_disclaimer": custom_disclaimer,
                "privacy_policy": privacy_policy,
            },
        ).json()

    def update_api_tool_provider(
        self,
        *,
        provider_name: str,
        schema: dict[str, Any],
        credentials: dict[str, Any],
        icon: dict[str, Any] | None = None,
        labels: list[str] | None = None,
        custom_disclaimer: str = "",
        privacy_policy: str = "",
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/console/api/workspaces/current/tool-provider/api/update",
            json={
                "provider": provider_name,
                "original_provider": provider_name,
                "schema_type": "openapi",
                "schema": json.dumps(schema, indent=2),
                "credentials": credentials,
                "icon": icon or {},
                "labels": labels or [],
                "custom_disclaimer": custom_disclaimer,
                "privacy_policy": privacy_policy,
            },
        ).json()
