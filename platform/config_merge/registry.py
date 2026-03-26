from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import threading
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

import yaml

from platform.events import build_envelope

from ._db import connection_kind, managed_connection, placeholder, rows_to_dicts
from .catalog import MERGE_ELIGIBLE_PATH, MergeEligibleFileSpec, load_merge_eligible_catalog


def _default_nats_publisher(subject: str, payload: dict[str, Any]) -> None:
    nats_url = os.environ.get("LV3_NATS_URL", "").strip()
    if not nats_url:
        return
    repo_root = Path(__file__).resolve().parents[2]
    drift_lib_path = repo_root / "scripts" / "drift_lib.py"
    import importlib.util

    spec = importlib.util.spec_from_file_location("lv3_config_merge_drift_lib", drift_lib_path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive import guard
        return
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.publish_nats_events(
        [{"subject": subject, "payload": payload}],
        nats_url=nats_url,
        credentials=None,
    )


def _publish_async(
    publisher: Callable[[str, dict[str, Any]], None] | None,
    subject: str,
    payload: dict[str, Any],
) -> None:
    if publisher is None:
        return

    def runner() -> None:
        try:
            publisher(subject, payload)
        except Exception:
            return

    thread = threading.Thread(target=runner, name="config-merge-publisher", daemon=True)
    thread.start()


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _isoformat(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str | dt.datetime | None) -> str:
    if value is None:
        return _isoformat(_utc_now())
    if isinstance(value, dt.datetime):
        return _isoformat(value)
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return _isoformat(parsed)


class DuplicateKeyError(RuntimeError):
    pass


class ConfigMergeRegistry:
    def __init__(
        self,
        *,
        repo_root: str | Path | None = None,
        catalog_path: str | Path | None = None,
        dsn: str | None = None,
        connection_factory: Callable[[], Any] | None = None,
        nats_publisher: Callable[[str, dict[str, Any]], None] | None = _default_nats_publisher,
        publish_nats: bool = False,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
        self.catalog_path = Path(catalog_path) if catalog_path is not None else MERGE_ELIGIBLE_PATH
        self.specs = load_merge_eligible_catalog(self.catalog_path)
        self.dsn = (dsn or "").strip()
        self.connection_factory = connection_factory
        self.nats_publisher = nats_publisher
        self.publish_nats = publish_nats

    def ensure_schema(self) -> None:
        with managed_connection(self.connection_factory, self.dsn) as connection:
            if connection_kind(connection) == "sqlite":
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS config_change_staging (
                        change_id TEXT PRIMARY KEY,
                        file_path TEXT NOT NULL,
                        operation TEXT NOT NULL,
                        key_value TEXT NOT NULL,
                        entry_json TEXT,
                        submitted_by TEXT NOT NULL,
                        context_id TEXT NOT NULL,
                        submitted_at TEXT NOT NULL,
                        merged_at TEXT,
                        status TEXT NOT NULL DEFAULT 'pending',
                        status_reason TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_config_change_staging_status_submitted
                    ON config_change_staging (status, submitted_at);
                    CREATE INDEX IF NOT EXISTS idx_config_change_staging_file_status
                    ON config_change_staging (file_path, status, submitted_at);
                    """
                )
            else:  # pragma: no cover - exercised on live infra, not in unit tests
                migration_path = self.repo_root / "migrations" / "0016_config_merge_schema.sql"
                with connection.cursor() as cursor:
                    cursor.execute(migration_path.read_text(encoding="utf-8"))
            connection.commit()

    def stage_append(
        self,
        *,
        file_path: str,
        entry: dict[str, Any],
        actor: str,
        context_id: str,
        key_value: str | None = None,
        submitted_at: str | dt.datetime | None = None,
    ) -> dict[str, Any]:
        spec = self._require_spec(file_path)
        if "append" not in spec.allowed_operations:
            raise ValueError(f"{file_path} does not allow append operations")

        resolved_key = self._resolve_key_value(spec, entry, key_value=key_value)
        existing = self._entry_by_key(spec, self._load_collection(spec, include_pending=True), resolved_key)
        if existing is not None and spec.conflict_resolution == "reject_duplicate_key":
            raise DuplicateKeyError(f"{spec.key_field}={resolved_key} already exists in {file_path}")

        change = {
            "change_id": str(uuid.uuid4()),
            "file_path": spec.file_path,
            "operation": "append",
            "key_value": resolved_key,
            "entry_json": dict(entry),
            "submitted_by": actor,
            "context_id": context_id,
            "submitted_at": _parse_timestamp(submitted_at),
            "status": "pending",
            "status_reason": None,
            "merged_at": None,
        }
        self._insert_change(change)
        return change

    def merge_pending(
        self,
        *,
        file_path: str | None = None,
        actor: str = "agent/config-merge-job",
        commit_changes: bool = False,
        push: bool = False,
        merged_at: str | dt.datetime | None = None,
    ) -> dict[str, Any]:
        changes = self._list_changes(status="pending", file_path=file_path)
        if not changes:
            return {
                "status": "ok",
                "merged_files": [],
                "merged_change_ids": [],
                "conflict_change_ids": [],
                "pending_count": 0,
            }

        merged_at_value = _parse_timestamp(merged_at)
        by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for change in changes:
            by_file[str(change["file_path"])].append(change)

        merged_change_ids: list[str] = []
        conflict_change_ids: list[str] = []
        merged_files: list[str] = []

        for current_file, file_changes in by_file.items():
            spec = self._require_spec(current_file)
            root = self._load_file_root(spec)
            collection = self._collection_from_root(root, spec)
            candidate = self._clone_collection(collection, spec)
            mergeable: list[dict[str, Any]] = []
            conflicts: list[dict[str, Any]] = []

            for change in file_changes:
                operation = str(change["operation"])
                key_value = str(change["key_value"])
                entry = change.get("entry_json")
                if operation == "append":
                    existing = self._entry_by_key(spec, candidate, key_value)
                    if existing is not None and spec.conflict_resolution == "reject_duplicate_key":
                        conflicts.append(change)
                        continue
                    self._upsert_entry(spec, candidate, key_value, entry)
                    mergeable.append(change)
                    continue
                if operation == "update":
                    self._upsert_entry(spec, candidate, key_value, entry)
                    mergeable.append(change)
                    continue
                if operation == "delete":
                    deleted = self._delete_entry(spec, candidate, key_value)
                    if not deleted and spec.conflict_resolution == "reject_duplicate_key":
                        conflicts.append(change)
                        continue
                    mergeable.append(change)
                    continue
                conflicts.append(change)

            if mergeable:
                root = self._set_collection_on_root(root, spec, candidate)
                self._write_file_root(spec, root)
                merged_files.append(current_file)
                merged_ids = [str(change["change_id"]) for change in mergeable]
                merged_change_ids.extend(merged_ids)
                self._mark_status(merged_ids, status="merged", merged_at=merged_at_value)
                for change in mergeable:
                    self._publish_merge_event(change, actor=actor, status="merged", merged_at=merged_at_value)

            if conflicts:
                conflict_ids = [str(change["change_id"]) for change in conflicts]
                conflict_change_ids.extend(conflict_ids)
                self._mark_status(conflict_ids, status="conflict", status_reason="duplicate_or_invalid_operation")
                for change in conflicts:
                    self._publish_merge_event(
                        change,
                        actor=actor,
                        status="conflict",
                        merged_at=merged_at_value,
                        reason="duplicate_or_invalid_operation",
                    )

        if commit_changes and merged_files:
            self._git_commit(
                merged_files,
                message=f"config: merge {len(merged_change_ids)} staged changes",
                push=push,
            )

        return {
            "status": "ok",
            "merged_files": merged_files,
            "merged_change_ids": merged_change_ids,
            "conflict_change_ids": conflict_change_ids,
            "pending_count": len(changes),
        }

    def read_file(self, file_path: str, *, include_pending: bool = True) -> Any:
        spec = self._require_spec(file_path)
        root = self._load_file_root(spec)
        if not include_pending:
            return root
        collection = self._collection_from_root(root, spec)
        overlaid = self._clone_collection(collection, spec)
        for change in self._list_changes(status="pending", file_path=file_path):
            operation = str(change["operation"])
            key_value = str(change["key_value"])
            entry = change.get("entry_json")
            if operation in {"append", "update"}:
                self._upsert_entry(spec, overlaid, key_value, entry)
            elif operation == "delete":
                self._delete_entry(spec, overlaid, key_value)
        root = self._set_collection_on_root(root, spec, overlaid)
        return root

    def _publish_merge_event(
        self,
        change: dict[str, Any],
        *,
        actor: str,
        status: str,
        merged_at: str,
        reason: str | None = None,
    ) -> None:
        if not self.publish_nats:
            return
        topic = "platform.config.merged" if status == "merged" else "platform.config.merge_conflict"
        payload = {
            "change_id": str(change["change_id"]),
            "file_path": str(change["file_path"]),
            "key_value": str(change["key_value"]),
            "operation": str(change["operation"]),
            "status": status,
        }
        if reason:
            payload["reason"] = reason
        envelope = build_envelope(topic, payload, actor_id=actor, context_id=str(change["context_id"]), ts=merged_at)
        _publish_async(self.nats_publisher, topic, envelope)

    def _require_spec(self, file_path: str) -> MergeEligibleFileSpec:
        spec = self.specs.get(file_path)
        if spec is None:
            raise ValueError(f"{file_path} is not in {self.catalog_path}")
        return spec

    def _load_file_root(self, spec: MergeEligibleFileSpec) -> Any:
        path = self.repo_root / spec.file_path
        text = path.read_text(encoding="utf-8")
        if spec.format == "json":
            return json.loads(text)
        return yaml.safe_load(text)

    def _write_file_root(self, spec: MergeEligibleFileSpec, payload: Any) -> None:
        path = self.repo_root / spec.file_path
        if spec.format == "json":
            rendered = json.dumps(payload, indent=2) + "\n"
        else:
            rendered = yaml.safe_dump(payload, sort_keys=False)
        path.write_text(rendered, encoding="utf-8")

    def _load_collection(self, spec: MergeEligibleFileSpec, *, include_pending: bool) -> Any:
        root = self.read_file(spec.file_path, include_pending=include_pending)
        return self._collection_from_root(root, spec)

    @staticmethod
    def _collection_from_root(root: Any, spec: MergeEligibleFileSpec) -> Any:
        if not spec.collection_path:
            if spec.collection_type == "list" and not isinstance(root, list):
                raise ValueError(f"{spec.file_path} root payload must be a list")
            if spec.collection_type == "mapping" and not isinstance(root, dict):
                raise ValueError(f"{spec.file_path} root payload must be a mapping")
            return root
        current = root
        for part in spec.collection_path:
            if not isinstance(current, dict) or part not in current:
                raise ValueError(f"{spec.file_path} is missing collection path {'.'.join(spec.collection_path)}")
            current = current[part]
        if spec.collection_type == "list" and not isinstance(current, list):
            raise ValueError(f"{spec.file_path} collection must be a list")
        if spec.collection_type == "mapping" and not isinstance(current, dict):
            raise ValueError(f"{spec.file_path} collection must be a mapping")
        return current

    @staticmethod
    def _set_collection_on_root(root: Any, spec: MergeEligibleFileSpec, collection: Any) -> Any:
        if not spec.collection_path:
            return collection
        current = root
        for part in spec.collection_path[:-1]:
            current = current[part]
        current[spec.collection_path[-1]] = collection
        return root

    @staticmethod
    def _clone_collection(collection: Any, spec: MergeEligibleFileSpec) -> Any:
        if spec.collection_type == "list":
            return [dict(item) for item in collection]
        return {key: dict(value) for key, value in collection.items()}

    def _resolve_key_value(self, spec: MergeEligibleFileSpec, entry: dict[str, Any], *, key_value: str | None) -> str:
        if key_value is not None:
            return str(key_value)
        value = entry.get(spec.key_field)
        if value is None:
            raise ValueError(f"{spec.file_path} staged entries must define {spec.key_field}")
        return str(value)

    @staticmethod
    def _entry_by_key(spec: MergeEligibleFileSpec, collection: Any, key_value: str) -> dict[str, Any] | None:
        if spec.collection_type == "list":
            for item in collection:
                if str(item.get(spec.key_field)) == key_value:
                    return dict(item)
            return None
        if key_value not in collection:
            return None
        item = dict(collection[key_value])
        if spec.drop_key_field_on_write:
            item.setdefault(spec.key_field, key_value)
        return item

    @staticmethod
    def _normalized_entry(spec: MergeEligibleFileSpec, key_value: str, entry: dict[str, Any] | None) -> dict[str, Any]:
        payload = dict(entry or {})
        if spec.collection_type == "list":
            payload[spec.key_field] = key_value
            return payload
        if spec.drop_key_field_on_write:
            payload.pop(spec.key_field, None)
        return payload

    def _upsert_entry(self, spec: MergeEligibleFileSpec, collection: Any, key_value: str, entry: dict[str, Any] | None) -> None:
        payload = self._normalized_entry(spec, key_value, entry)
        if spec.collection_type == "list":
            for index, item in enumerate(collection):
                if str(item.get(spec.key_field)) == key_value:
                    collection[index] = payload
                    return
            collection.append(payload)
            return
        collection[key_value] = payload

    @staticmethod
    def _delete_entry(spec: MergeEligibleFileSpec, collection: Any, key_value: str) -> bool:
        if spec.collection_type == "list":
            for index, item in enumerate(collection):
                if str(item.get(spec.key_field)) == key_value:
                    del collection[index]
                    return True
            return False
        if key_value not in collection:
            return False
        del collection[key_value]
        return True

    def _insert_change(self, change: dict[str, Any]) -> None:
        with managed_connection(self.connection_factory, self.dsn) as connection:
            token = placeholder(connection)
            sql = f"""
                INSERT INTO config_change_staging (
                    change_id,
                    file_path,
                    operation,
                    key_value,
                    entry_json,
                    submitted_by,
                    context_id,
                    submitted_at,
                    merged_at,
                    status,
                    status_reason
                )
                VALUES ({token}, {token}, {token}, {token}, {token}, {token}, {token}, {token}, {token}, {token}, {token})
            """
            entry_payload = json.dumps(change["entry_json"], sort_keys=True) if change["entry_json"] is not None else None
            connection.execute(
                sql,
                (
                    change["change_id"],
                    change["file_path"],
                    change["operation"],
                    change["key_value"],
                    entry_payload,
                    change["submitted_by"],
                    change["context_id"],
                    change["submitted_at"],
                    change["merged_at"],
                    change["status"],
                    change["status_reason"],
                ),
            )
            connection.commit()

    def _list_changes(self, *, status: str, file_path: str | None = None) -> list[dict[str, Any]]:
        with managed_connection(self.connection_factory, self.dsn) as connection:
            token = placeholder(connection)
            sql = (
                "SELECT change_id, file_path, operation, key_value, entry_json, submitted_by, context_id, submitted_at, merged_at, status, status_reason "
                "FROM config_change_staging WHERE status = "
                f"{token}"
            )
            params: list[Any] = [status]
            if file_path is not None:
                sql += f" AND file_path = {token}"
                params.append(file_path)
            sql += " ORDER BY submitted_at ASC"
            cursor = connection.execute(sql, params)
            rows = rows_to_dicts(cursor)
        for row in rows:
            if row.get("entry_json"):
                row["entry_json"] = json.loads(row["entry_json"])
        return rows

    def _mark_status(
        self,
        change_ids: list[str],
        *,
        status: str,
        merged_at: str | None = None,
        status_reason: str | None = None,
    ) -> None:
        if not change_ids:
            return
        with managed_connection(self.connection_factory, self.dsn) as connection:
            token = placeholder(connection)
            set_fields = [f"status = {token}", f"status_reason = {token}"]
            params: list[Any] = [status, status_reason]
            if merged_at is not None:
                set_fields.append(f"merged_at = {token}")
                params.append(merged_at)
            placeholders = ", ".join(token for _ in change_ids)
            sql = (
                f"UPDATE config_change_staging SET {', '.join(set_fields)} "
                f"WHERE change_id IN ({placeholders})"
            )
            params.extend(change_ids)
            connection.execute(sql, params)
            connection.commit()

    def _git_commit(self, files: list[str], *, message: str, push: bool) -> None:
        subprocess.run(["git", "-C", str(self.repo_root), "add", *files], check=True)
        subprocess.run(["git", "-C", str(self.repo_root), "commit", "-m", message], check=True)
        if push:
            subprocess.run(["git", "-C", str(self.repo_root), "push"], check=True)
