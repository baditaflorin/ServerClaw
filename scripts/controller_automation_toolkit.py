#!/usr/bin/env python3

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Final


REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MAKEFILE_PATH: Final[Path] = REPO_ROOT / "Makefile"
README_PATH: Final[Path] = REPO_ROOT / "README.md"
WORKFLOW_CATALOG_PATH: Final[Path] = REPO_ROOT / "config" / "workflow-catalog.json"
SECRET_MANIFEST_PATH: Final[Path] = REPO_ROOT / "config" / "controller-local-secrets.json"
RECEIPTS_DIR: Final[Path] = REPO_ROOT / "receipts" / "live-applies"
MAKE_TARGET_PATTERN: Final[re.Pattern[str]] = re.compile(r"^([A-Za-z0-9_-]+):")
PYYAML_INSTALL_HINT: Final[str] = (
    "Missing dependency: PyYAML. Run via 'uvx --from pyyaml python ...' or "
    "'uv run --with pyyaml ...'."
)
_MISSING = object()


def repo_path(*parts: str) -> Path:
    return REPO_ROOT.joinpath(*parts)


def load_json(path: Path, default: Any = _MISSING) -> Any:
    if not path.exists():
        if default is _MISSING:
            raise FileNotFoundError(path)
        return default
    return json.loads(path.read_text())


def write_json(
    path: Path,
    payload: Any,
    *,
    indent: int = 2,
    sort_keys: bool = False,
    mode: int | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=indent, sort_keys=sort_keys) + "\n")
    if mode is not None:
        path.chmod(mode)


def load_yaml(path: Path) -> Any:
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - direct runtime guard
        raise RuntimeError(PYYAML_INSTALL_HINT) from exc
    return yaml.safe_load(path.read_text())


def run_command(
    command: list[str],
    *,
    cwd: Path = REPO_ROOT,
    text: bool = True,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=text,
        capture_output=capture_output,
        check=False,
    )


def command_succeeds(command: list[str], *, cwd: Path = REPO_ROOT) -> bool:
    return run_command(command, cwd=cwd).returncode == 0


def parse_make_targets(makefile_path: Path = MAKEFILE_PATH) -> set[str]:
    targets = set()
    for line in makefile_path.read_text().splitlines():
        match = MAKE_TARGET_PATTERN.match(line)
        if not match:
            continue
        target = match.group(1)
        if target != ".PHONY":
            targets.add(target)
    return targets


def emit_cli_error(prefix: str, exc: Exception, *, exit_code: int = 2) -> int:
    print(f"{prefix} error: {exc}", file=sys.stderr)
    return exit_code
