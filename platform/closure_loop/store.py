from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


class LoopStateStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def list_runs(self) -> list[dict[str, Any]]:
        payload = self._read()
        runs = payload.get("runs", [])
        if not isinstance(runs, list):
            return []
        return [item for item in runs if isinstance(item, dict)]

    def get(self, run_id: str) -> dict[str, Any] | None:
        for item in self.list_runs():
            if str(item.get("run_id")) == run_id:
                return item
        return None

    def upsert(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = self._read()
        runs = [
            item
            for item in payload.get("runs", [])
            if isinstance(item, dict) and str(item.get("run_id")) != str(record.get("run_id"))
        ]
        runs.append(record)
        self._write({"runs": sorted(runs, key=lambda item: str(item.get("created_at", "")))})
        return record

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"runs": []}
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"runs": []}

    def _write(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", delete=False, dir=self._path.parent, encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temp_path = Path(handle.name)
        temp_path.replace(self._path)
