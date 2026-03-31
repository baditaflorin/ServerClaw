#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request


TAXONOMY_ENDPOINTS = {
    "correspondents": "/api/correspondents/",
    "document_types": "/api/document_types/",
    "tags": "/api/tags/",
}


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


class PaperlessClient:
    def __init__(self, base_url: str, api_token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | list[Any] | None = None,
        raw_body: bytes | None = None,
        headers: dict[str, str] | None = None,
        content_type: str | None = None,
    ) -> Any:
        req_headers = {"Accept": "application/json"}
        if self.api_token:
            req_headers["Authorization"] = f"Token {self.api_token}"
        if headers:
            req_headers.update(headers)

        body = raw_body
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        elif content_type:
            req_headers["Content-Type"] = content_type

        req = request.Request(f"{self.base_url}{path}", data=body, headers=req_headers, method=method)
        try:
            with request.urlopen(req, timeout=120) as response:
                raw = response.read()
        except error.HTTPError as exc:  # pragma: no cover - integration exercised
            body_text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed with {exc.code}: {body_text}") from exc
        except error.URLError as exc:  # pragma: no cover - integration exercised
            raise RuntimeError(f"{method} {path} failed: {exc.reason}") from exc

        if not raw.strip():
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return raw.decode("utf-8", errors="replace")

    def _paginate(self, path: str) -> list[dict[str, Any]]:
        url = path if path.startswith("/") else f"/{path}"
        results: list[dict[str, Any]] = []
        while url:
            payload = self._request("GET", url)
            if isinstance(payload, list):
                results.extend(item for item in payload if isinstance(item, dict))
                break
            if not isinstance(payload, dict):
                raise RuntimeError(f"Expected paginated response for {url}")
            page_results = payload.get("results", [])
            if not isinstance(page_results, list):
                raise RuntimeError(f"Expected list results for {url}")
            results.extend(item for item in page_results if isinstance(item, dict))
            next_url = payload.get("next")
            if not next_url:
                break
            if isinstance(next_url, str) and next_url.startswith(self.base_url):
                url = next_url[len(self.base_url) :]
            else:
                url = str(next_url)
        return results

    def create_token(self, username: str, password: str) -> str:
        payload = self._request("POST", "/api/token/", payload={"username": username, "password": password})
        if isinstance(payload, dict) and isinstance(payload.get("token"), str):
            return payload["token"]
        if isinstance(payload, str) and payload.strip():
            return payload.strip()
        raise RuntimeError("Paperless token endpoint did not return a token")

    def list_taxonomy(self, kind: str) -> list[dict[str, Any]]:
        return self._paginate(f"{TAXONOMY_ENDPOINTS[kind]}?page_size=200")

    def create_taxonomy_item(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request("POST", TAXONOMY_ENDPOINTS[kind], payload=payload)
        if not isinstance(response, dict):
            raise RuntimeError(f"Expected JSON object when creating {kind}")
        return response

    def update_taxonomy_item(self, kind: str, item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request("PATCH", f"{TAXONOMY_ENDPOINTS[kind]}{item_id}/", payload=payload)
        if not isinstance(response, dict):
            raise RuntimeError(f"Expected JSON object when updating {kind}:{item_id}")
        return response

    def list_documents(self, *, query: str | None = None) -> list[dict[str, Any]]:
        qs = {"page_size": "100"}
        if query:
            qs["query"] = query
        return self._paginate(f"/api/documents/?{parse.urlencode(qs)}")

    def get_document(self, document_id: int) -> dict[str, Any]:
        payload = self._request("GET", f"/api/documents/{document_id}/")
        if not isinstance(payload, dict):
            raise RuntimeError(f"Expected JSON object when reading document {document_id}")
        return payload

    def delete_document(self, document_id: int) -> None:
        self._request("DELETE", f"/api/documents/{document_id}/")

    def list_tasks(self, task_id: str) -> list[dict[str, Any]]:
        return self._paginate(f"/api/tasks/?task_id={parse.quote(task_id)}")

    def upload_document(self, *, filename: str, content: bytes, fields: list[tuple[str, str]]) -> Any:
        boundary = f"paperless-sync-{uuid.uuid4().hex}"
        body = bytearray()
        for key, value in fields:
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
            body.extend(value.encode("utf-8"))
            body.extend(b"\r\n")
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'.encode("utf-8")
        )
        body.extend(b"Content-Type: application/pdf\r\n\r\n")
        body.extend(content)
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))
        return self._request(
            "POST",
            "/api/documents/post_document/",
            raw_body=bytes(body),
            content_type=f"multipart/form-data; boundary={boundary}",
        )


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def write_report(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_api_token(args: argparse.Namespace) -> str:
    if getattr(args, "api_token", None):
        return str(args.api_token).strip()
    if getattr(args, "api_token_file", None):
        return read_text(args.api_token_file)
    raise ValueError("Provide --api-token or --api-token-file")


def load_desired_state(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Desired state must be a JSON object")
    for kind in TAXONOMY_ENDPOINTS:
        items = payload.get(kind, [])
        if not isinstance(items, list):
            raise ValueError(f"{kind} must be a list")
        seen_ids: set[str] = set()
        seen_names: set[str] = set()
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"{kind}[{index}] must be an object")
            item_id = str(item.get("id", "")).strip()
            name = str(item.get("name", "")).strip()
            if not item_id or not name:
                raise ValueError(f"{kind}[{index}] must include non-empty id and name")
            if item_id in seen_ids:
                raise ValueError(f"Duplicate {kind} id '{item_id}'")
            if name in seen_names:
                raise ValueError(f"Duplicate {kind} name '{name}'")
            seen_ids.add(item_id)
            seen_names.add(name)
    return payload


def desired_item_payload(item: dict[str, Any]) -> dict[str, Any]:
    payload = {"name": item["name"]}
    for field in ("slug", "matching_algorithm", "is_insensitive", "color"):
        if field in item:
            payload[field] = item[field]
    return payload


def normalize_value(value: Any) -> Any:
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_value(value[key]) for key in sorted(value)}
    return value


def sync_taxonomy(
    *,
    client: Any,
    desired_state: dict[str, Any],
    check_only: bool,
) -> dict[str, Any]:
    actions: list[Action] = []
    summary: dict[str, int] = {}
    unmanaged: dict[str, list[str]] = {}

    for kind in TAXONOMY_ENDPOINTS:
        existing_items = client.list_taxonomy(kind)
        existing_by_name = {str(item.get("name", "")).strip(): item for item in existing_items}
        desired_items = desired_state.get(kind, [])
        desired_names = {item["name"] for item in desired_items}
        unmanaged[kind] = sorted(name for name in existing_by_name if name and name not in desired_names)
        summary[f"{kind}_created"] = 0
        summary[f"{kind}_updated"] = 0

        for item in desired_items:
            item_id = item["id"]
            payload = desired_item_payload(item)
            current = existing_by_name.get(item["name"])
            if current is None:
                actions.append(Action(kind, "create", item_id, item["name"]))
                summary[f"{kind}_created"] += 1
                if not check_only:
                    client.create_taxonomy_item(kind, payload)
                continue

            current_subset = {key: normalize_value(current.get(key)) for key in payload}
            desired_subset = {key: normalize_value(payload.get(key)) for key in payload}
            if current_subset != desired_subset:
                actions.append(Action(kind, "update", item_id, item["name"]))
                summary[f"{kind}_updated"] += 1
                if not check_only:
                    client.update_taxonomy_item(kind, int(current["id"]), payload)

    changed = any(value > 0 for key, value in summary.items() if key.endswith(("_created", "_updated")))
    return {
        "changed": changed,
        "check_only": check_only,
        "summary": summary,
        "actions": [action.as_dict() for action in actions],
        "unmanaged_live_items": unmanaged,
    }


def bootstrap_token(base_url: str, username: str, password_file: Path, token_file: Path) -> dict[str, Any]:
    if token_file.exists() and token_file.read_text(encoding="utf-8").strip():
        return {
            "changed": False,
            "base_url": base_url,
            "username": username,
            "token_file": str(token_file),
        }

    token = PaperlessClient(base_url).create_token(username, read_text(password_file))
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(token + "\n", encoding="utf-8")
    return {
        "changed": True,
        "base_url": base_url,
        "username": username,
        "token_file": str(token_file),
    }


def extract_document_id(payload: Any) -> int | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in {"document_id", "related_document"} and isinstance(value, int):
                return value
            nested = extract_document_id(value)
            if nested is not None:
                return nested
    if isinstance(payload, list):
        for item in payload:
            nested = extract_document_id(item)
            if nested is not None:
                return nested
    return None


def pdf_literal_string(text: str) -> bytes:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode(
        "ascii",
        errors="backslashreplace",
    )


def tiny_pdf_bytes(label: str) -> bytes:
    content_stream = b"BT /F1 12 Tf 36 120 Td (" + pdf_literal_string(label) + b") Tj ET\n"
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>\nendobj\n",
        (
            f"4 0 obj\n<< /Length {len(content_stream)} >>\nstream\n".encode("ascii")
            + content_stream
            + b"endstream\nendobj\n"
        ),
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)

    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(pdf)


def smoke_upload(base_url: str, api_token: str, cleanup: bool = True) -> dict[str, Any]:
    client = PaperlessClient(base_url, api_token=api_token)
    serial_number = (uuid.uuid4().int % 2_000_000_000) + 1
    serial = str(serial_number)
    title = f"LV3 Paperless Smoke {serial}"
    upload_response = client.upload_document(
        filename=f"lv3-paperless-smoke-{serial}.pdf",
        content=tiny_pdf_bytes(title),
        fields=[("title", title), ("archive_serial_number", serial)],
    )
    task_id = None
    if isinstance(upload_response, dict):
        if isinstance(upload_response.get("task_id"), str):
            task_id = upload_response["task_id"]
        elif isinstance(upload_response.get("task"), str):
            task_id = upload_response["task"]
    elif isinstance(upload_response, str) and upload_response.strip():
        task_id = upload_response.strip()

    document: dict[str, Any] | None = None
    document_id = None
    deadline = time.time() + 180
    while time.time() < deadline and document is None:
        if task_id:
            tasks = client.list_tasks(task_id)
            if tasks:
                document_id = extract_document_id(tasks[0])
                if document_id is not None:
                    document = client.get_document(document_id)
                    break
        for candidate in client.list_documents(query=serial):
            if str(candidate.get("archive_serial_number", "")).strip() == serial:
                document = candidate
                document_id = int(candidate["id"])
                break
        if document is None:
            time.sleep(5)

    if document is None or document_id is None:
        raise RuntimeError(f"Timed out waiting for uploaded Paperless document {serial}")

    cleaned_up = False
    if cleanup:
        client.delete_document(document_id)
        cleaned_up = True

    return {
        "changed": False,
        "base_url": base_url,
        "archive_serial_number": serial_number,
        "title": title,
        "task_id": task_id,
        "document_id": document_id,
        "cleanup": cleaned_up,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap and verify repo-managed Paperless taxonomy and API state.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap-token", help="Create the durable Paperless API token when missing.")
    bootstrap.add_argument("--base-url", required=True)
    bootstrap.add_argument("--username", required=True)
    bootstrap.add_argument("--password-file", type=Path, required=True)
    bootstrap.add_argument("--token-file", type=Path, required=True)

    sync = subparsers.add_parser("sync", help="Reconcile the declared Paperless taxonomy.")
    sync.add_argument("--base-url", required=True)
    sync.add_argument("--api-token")
    sync.add_argument("--api-token-file", type=Path)
    sync.add_argument("--desired-state-file", type=Path, required=True)
    sync.add_argument("--report-file", type=Path)

    verify = subparsers.add_parser("verify", help="Check the declared Paperless taxonomy without mutating it.")
    verify.add_argument("--base-url", required=True)
    verify.add_argument("--api-token")
    verify.add_argument("--api-token-file", type=Path)
    verify.add_argument("--desired-state-file", type=Path, required=True)
    verify.add_argument("--report-file", type=Path)

    smoke = subparsers.add_parser("smoke-upload", help="Upload, verify, and optionally clean up a temporary document.")
    smoke.add_argument("--base-url", required=True)
    smoke.add_argument("--api-token")
    smoke.add_argument("--api-token-file", type=Path)
    smoke.add_argument("--report-file", type=Path)
    smoke.add_argument("--no-cleanup", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "bootstrap-token":
            result = bootstrap_token(args.base_url, args.username, args.password_file, args.token_file)
            print(json.dumps(result, sort_keys=True))
            return 0

        if args.command == "sync":
            result = sync_taxonomy(
                client=PaperlessClient(args.base_url, api_token=load_api_token(args)),
                desired_state=load_desired_state(args.desired_state_file),
                check_only=False,
            )
            write_report(args.report_file, result)
            print(json.dumps(result, sort_keys=True))
            return 0

        if args.command == "verify":
            result = sync_taxonomy(
                client=PaperlessClient(args.base_url, api_token=load_api_token(args)),
                desired_state=load_desired_state(args.desired_state_file),
                check_only=True,
            )
            write_report(args.report_file, result)
            print(json.dumps(result, sort_keys=True))
            return 0 if not result["changed"] else 1

        if args.command == "smoke-upload":
            result = smoke_upload(args.base_url, load_api_token(args), cleanup=not args.no_cleanup)
            write_report(args.report_file, result)
            print(json.dumps(result, sort_keys=True))
            return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
