from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class OperatorAccessIntegrationError(RuntimeError):
    """Raised when an external integration request fails."""


def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | list[Any] | str | None = None,
    form: dict[str, str] | None = None,
    expected_status: tuple[int, ...] = (200,),
) -> Any:
    request_headers = dict(headers or {})
    data: bytes | None = None
    if body is not None and form is not None:
        raise OperatorAccessIntegrationError("request_json cannot encode JSON and form payloads at the same time.")
    if body is not None:
        if isinstance(body, str):
            data = body.encode("utf-8")
        else:
            data = json.dumps(body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    elif form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    request = urllib.request.Request(url, data=data, method=method, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            content = response.read().decode("utf-8")
            if response.status not in expected_status:
                raise OperatorAccessIntegrationError(f"{method} {url} returned unexpected HTTP {response.status}.")
            if not content.strip():
                return {}
            if "application/json" in response.headers.get("Content-Type", ""):
                return json.loads(content)
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"raw": content}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code in expected_status:
            if not detail.strip():
                return {}
            try:
                return json.loads(detail)
            except json.JSONDecodeError:
                return {"raw": detail}
        raise OperatorAccessIntegrationError(f"{method} {url} failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise OperatorAccessIntegrationError(f"{method} {url} failed: {exc}") from exc
