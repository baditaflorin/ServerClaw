from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os


DEFAULT_BASE_URL = "https://langfuse.lv3.org"


@dataclass(frozen=True)
class LangfuseConfig:
    host: str
    public_key: str
    secret_key: str
    project_id: str | None = None

    @property
    def trace_base_url(self) -> str:
        return self.host.rstrip("/")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def load_langfuse_config(repo_root: Path | None = None) -> LangfuseConfig:
    root = Path(repo_root or Path(__file__).resolve().parents[2])
    local_dir = root / ".local" / "langfuse"
    project_public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip() or _read_text(
        local_dir / "project-public-key.txt"
    )
    project_secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "").strip() or _read_text(
        local_dir / "project-secret-key.txt"
    )
    host = os.environ.get("LANGFUSE_HOST", "").strip() or DEFAULT_BASE_URL
    project_id_file = local_dir / "project-id.txt"
    project_id = None
    if project_id_file.exists():
        project_id = _read_text(project_id_file)
    return LangfuseConfig(
        host=host.rstrip("/"),
        public_key=project_public_key,
        secret_key=project_secret_key,
        project_id=project_id or os.environ.get("LANGFUSE_PROJECT_ID", "").strip() or None,
    )


def trace_url(host: str, project_id: str, trace_id: str) -> str:
    return f"{host.rstrip('/')}/project/{project_id}/traces/{trace_id}"


def dump_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)
