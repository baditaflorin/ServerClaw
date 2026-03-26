from __future__ import annotations

import importlib.util
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any


BOOTSTRAP_ENV_VAR = "LV3_WORLD_STATE_DIRECT"
BASE_UV_DEPENDENCIES = ("psycopg[binary]", "pyyaml")
NATS_UV_DEPENDENCY = "nats-py"


def maybe_run_via_uv(
    *,
    script_path: Path,
    repo_path: str | Path,
    dsn: str | None,
    publish_nats: bool,
) -> dict[str, Any] | None:
    if os.environ.get(BOOTSTRAP_ENV_VAR, "").strip() == "1":
        return None
    if not _missing_runtime_dependencies(publish_nats=publish_nats):
        return None

    repo_root = Path(repo_path)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        output_path = Path(handle.name)

    command = ["uv", "run"]
    for dependency in BASE_UV_DEPENDENCIES:
        command.extend(["--with", dependency])
    if publish_nats:
        command.extend(["--with", NATS_UV_DEPENDENCY])
    command.extend(
        [
            "python",
            str(script_path),
            "--repo-path",
            str(repo_root),
            "--output-file",
            str(output_path),
        ]
    )
    if dsn:
        command.extend(["--dsn", dsn])
    if not publish_nats:
        command.append("--no-publish-nats")

    env = dict(os.environ)
    env["PYTHONPATH"] = f"{repo_root}:{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(repo_root)
    env[BOOTSTRAP_ENV_VAR] = "1"
    result = subprocess.run(command, cwd=repo_root, env=env, text=True, capture_output=True, check=False)
    output = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else result.stdout.strip()
    output_path.unlink(missing_ok=True)
    if result.returncode != 0:
        return {
            "status": "error",
            "command": " ".join(shlex.quote(part) for part in command),
            "returncode": result.returncode,
            "stdout": output,
            "stderr": result.stderr.strip(),
        }
    if not output:
        return {
            "status": "error",
            "reason": "fallback subprocess produced no JSON output",
            "command": " ".join(shlex.quote(part) for part in command),
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    return json.loads(output)


def render_result(result: dict[str, Any], *, output_file: Path | None = None) -> None:
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if output_file:
        output_file.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


def _missing_runtime_dependencies(*, publish_nats: bool) -> list[str]:
    modules = ["psycopg", "yaml"]
    if publish_nats:
        modules.append("nats")
    return [name for name in modules if importlib.util.find_spec(name) is None]
