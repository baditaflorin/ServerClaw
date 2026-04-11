#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request


TIME_FIELDS = ("weeks", "days", "hours", "minutes", "seconds")
TAG_FIELDS = ("title", "notification_urls", "notification_muted", "overrides_watch")
WATCH_FIELDS = (
    "url",
    "title",
    "tags",
    "paused",
    "time_between_check_use_default",
    "time_between_check",
    "method",
    "fetch_backend",
    "headers",
    "body",
    "notification_urls",
    "notification_title",
    "notification_body",
)


@dataclass(frozen=True)
class Action:
    kind: str
    action: str
    identifier: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "action": self.action,
            "id": self.identifier,
            "detail": self.detail,
        }


class ChangedetectionClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        body = None
        headers = {"x-api-key": self.api_key}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["content-type"] = "application/json"
        req = request.Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=60) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:  # pragma: no cover - exercised through integration
            body_text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed with {exc.code}: {body_text}") from exc
        except error.URLError as exc:  # pragma: no cover - exercised through integration
            raise RuntimeError(f"{method} {path} failed: {exc.reason}") from exc

        if not raw.strip():
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    def list_tags(self) -> dict[str, dict[str, Any]]:
        payload = self._request("GET", "/api/v1/tags")
        return payload if isinstance(payload, dict) else {}

    def get_tag(self, uuid: str) -> dict[str, Any]:
        payload = self._request("GET", f"/api/v1/tag/{uuid}")
        if not isinstance(payload, dict):
            raise RuntimeError(f"Expected JSON object when reading tag {uuid}")
        return payload

    def create_tag(self, payload: dict[str, Any]) -> str:
        response = self._request("POST", "/api/v1/tag", payload)
        if not isinstance(response, dict) or not isinstance(response.get("uuid"), str):
            raise RuntimeError("Tag creation did not return a UUID")
        return response["uuid"]

    def update_tag(self, uuid: str, payload: dict[str, Any]) -> None:
        self._request("PUT", f"/api/v1/tag/{uuid}", payload)

    def delete_tag(self, uuid: str) -> None:
        self._request("DELETE", f"/api/v1/tag/{uuid}")

    def list_watches(self) -> dict[str, dict[str, Any]]:
        payload = self._request("GET", "/api/v1/watch")
        return payload if isinstance(payload, dict) else {}

    def get_watch(self, uuid: str) -> dict[str, Any]:
        payload = self._request("GET", f"/api/v1/watch/{uuid}")
        if not isinstance(payload, dict):
            raise RuntimeError(f"Expected JSON object when reading watch {uuid}")
        return payload

    def create_watch(self, payload: dict[str, Any]) -> str:
        response = self._request("POST", "/api/v1/watch", payload)
        if not isinstance(response, dict) or not isinstance(response.get("uuid"), str):
            raise RuntimeError("Watch creation did not return a UUID")
        return response["uuid"]

    def update_watch(self, uuid: str, payload: dict[str, Any]) -> None:
        self._request("PUT", f"/api/v1/watch/{uuid}", payload)

    def delete_watch(self, uuid: str) -> None:
        self._request("DELETE", f"/api/v1/watch/{uuid}")


def normalize_time_between_check(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {field: 0 for field in TIME_FIELDS}
    return {field: int(value.get(field) or 0) for field in TIME_FIELDS}


def normalize_scalar(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize_scalar(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        if all(isinstance(item, str) for item in value):
            return sorted(value)
        return [normalize_scalar(item) for item in value]
    return value


def normalize_subset(payload: dict[str, Any], fields: tuple[str, ...] | list[str]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for field in fields:
        if field not in payload:
            continue
        value = payload[field]
        if field == "time_between_check":
            normalized[field] = normalize_time_between_check(value)
            continue
        if field == "time_between_check_use_default":
            normalized[field] = bool(value)
            continue
        if field == "notification_muted" or field == "overrides_watch" or field == "paused":
            normalized[field] = bool(value)
            continue
        if field in {"notification_urls", "tags"}:
            normalized[field] = sorted(str(item) for item in value)
            continue
        normalized[field] = normalize_scalar(value)
    return normalized


def load_desired_state(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Desired state must be a JSON object")

    tags = payload.get("tags", [])
    watches = payload.get("watches", [])
    if not isinstance(tags, list) or not isinstance(watches, list):
        raise ValueError("Desired state must include list-valued 'tags' and 'watches'")

    seen_tag_ids: set[str] = set()
    seen_tag_titles: set[str] = set()
    for index, tag in enumerate(tags):
        if not isinstance(tag, dict):
            raise ValueError(f"tags[{index}] must be an object")
        tag_id = str(tag.get("id", "")).strip()
        title = str(tag.get("title", "")).strip()
        if not tag_id or not title:
            raise ValueError(f"tags[{index}] must include non-empty id and title")
        if tag_id in seen_tag_ids:
            raise ValueError(f"Duplicate tag id '{tag_id}'")
        if title in seen_tag_titles:
            raise ValueError(f"Duplicate tag title '{title}'")
        seen_tag_ids.add(tag_id)
        seen_tag_titles.add(title)

    seen_watch_ids: set[str] = set()
    seen_watch_urls: set[str] = set()
    for index, watch in enumerate(watches):
        if not isinstance(watch, dict):
            raise ValueError(f"watches[{index}] must be an object")
        watch_id = str(watch.get("id", "")).strip()
        url = str(watch.get("url", "")).strip()
        group = str(watch.get("group", "")).strip()
        if not watch_id or not url or not group:
            raise ValueError(f"watches[{index}] must include non-empty id, url, and group")
        if group not in seen_tag_ids:
            raise ValueError(f"watches[{index}] references unknown group '{group}'")
        if watch_id in seen_watch_ids:
            raise ValueError(f"Duplicate watch id '{watch_id}'")
        if url in seen_watch_urls:
            raise ValueError(f"Duplicate watch url '{url}'")
        seen_watch_ids.add(watch_id)
        seen_watch_urls.add(url)

    return payload


def load_api_key(args: argparse.Namespace) -> str:
    if args.api_key:
        return args.api_key.strip()
    if args.api_key_file:
        return args.api_key_file.read_text(encoding="utf-8").strip()
    raise ValueError("Provide --api-key or --api-key-file")


def write_report(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def desired_tag_payload(tag: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"title": tag["title"]}
    for field in TAG_FIELDS:
        if field == "title":
            continue
        if field in tag:
            payload[field] = tag[field]
    return payload


def desired_watch_payload(watch: dict[str, Any], tag_uuid_map: dict[str, str]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "url": watch["url"],
        "title": watch["title"],
        "tags": [tag_uuid_map[watch["group"]]],
        "paused": bool(watch.get("paused", False)),
        "time_between_check_use_default": False,
        "time_between_check": {
            "hours": int(watch["interval_hours"]),
            "days": 0,
            "weeks": 0,
            "minutes": 0,
            "seconds": 0,
        },
    }
    for field in WATCH_FIELDS:
        if field in {
            "url",
            "title",
            "tags",
            "paused",
            "time_between_check_use_default",
            "time_between_check",
        }:
            continue
        if field in watch:
            payload[field] = watch[field]
    return payload


def sync_changedetection(
    *,
    client: ChangedetectionClient,
    desired_state: dict[str, Any],
    check_only: bool,
) -> dict[str, Any]:
    actions: list[Action] = []
    desired_tags = sorted(desired_state["tags"], key=lambda item: item["id"])
    desired_watches = sorted(desired_state["watches"], key=lambda item: item["id"])

    existing_tags = client.list_tags()
    existing_tag_by_title = {
        tag["title"]: uuid
        for uuid, tag in existing_tags.items()
        if isinstance(tag, dict) and isinstance(tag.get("title"), str)
    }
    tag_uuid_map: dict[str, str] = {}

    for tag in desired_tags:
        tag_id = tag["id"]
        title = tag["title"]
        payload = desired_tag_payload(tag)
        uuid = existing_tag_by_title.get(title)
        if uuid is None:
            actions.append(Action("tag", "create", tag_id, title))
            if check_only:
                tag_uuid_map[tag_id] = f"pending:{tag_id}"
                continue
            uuid = client.create_tag(payload)
        else:
            current = client.get_tag(uuid)
            comparison_fields = tuple(payload.keys())
            if normalize_subset(current, comparison_fields) != normalize_subset(payload, comparison_fields):
                actions.append(Action("tag", "update", tag_id, title))
                if not check_only:
                    client.update_tag(uuid, payload)
        tag_uuid_map[tag_id] = uuid

    existing_watches = client.list_watches()
    existing_watch_by_url = {
        watch["url"]: uuid
        for uuid, watch in existing_watches.items()
        if isinstance(watch, dict) and isinstance(watch.get("url"), str)
    }
    desired_urls = {watch["url"] for watch in desired_watches}

    for watch in desired_watches:
        watch_id = watch["id"]
        url = watch["url"]
        payload = desired_watch_payload(watch, tag_uuid_map)
        uuid = existing_watch_by_url.get(url)
        if uuid is None:
            actions.append(Action("watch", "create", watch_id, url))
            if not check_only:
                client.create_watch(payload)
            continue
        current = client.get_watch(uuid)
        comparison_fields = tuple(payload.keys())
        if normalize_subset(current, comparison_fields) != normalize_subset(payload, comparison_fields):
            actions.append(Action("watch", "update", watch_id, url))
            if not check_only:
                client.update_watch(uuid, payload)

    for uuid, watch in sorted(existing_watches.items(), key=lambda item: item[1].get("url", "")):
        url = str(watch.get("url", "")).strip()
        if not url or url in desired_urls:
            continue
        actions.append(Action("watch", "delete", uuid, url))
        if not check_only:
            client.delete_watch(uuid)

    desired_titles = {tag["title"] for tag in desired_tags}
    for uuid, tag in sorted(existing_tags.items(), key=lambda item: item[1].get("title", "")):
        title = str(tag.get("title", "")).strip()
        if not title or title in desired_titles:
            continue
        actions.append(Action("tag", "delete", uuid, title))
        if not check_only:
            client.delete_tag(uuid)

    summary = {
        "tags_created": sum(1 for action in actions if action.kind == "tag" and action.action == "create"),
        "tags_updated": sum(1 for action in actions if action.kind == "tag" and action.action == "update"),
        "tags_deleted": sum(1 for action in actions if action.kind == "tag" and action.action == "delete"),
        "watches_created": sum(1 for action in actions if action.kind == "watch" and action.action == "create"),
        "watches_updated": sum(1 for action in actions if action.kind == "watch" and action.action == "update"),
        "watches_deleted": sum(1 for action in actions if action.kind == "watch" and action.action == "delete"),
    }
    return {
        "changed": bool(actions),
        "check_only": check_only,
        "summary": summary,
        "actions": [action.as_dict() for action in actions],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reconcile a repo-managed Changedetection catalogue.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key")
    parser.add_argument("--api-key-file", type=Path)
    parser.add_argument("--desired-state-file", type=Path, required=True)
    parser.add_argument("--report-file", type=Path)
    parser.add_argument("--check-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        desired_state = load_desired_state(args.desired_state_file)
        api_key = load_api_key(args)
        client = ChangedetectionClient(args.base_url, api_key)
        report = sync_changedetection(
            client=client,
            desired_state=desired_state,
            check_only=bool(args.check_only),
        )
        write_report(args.report_file, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"changedetection_sync error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
