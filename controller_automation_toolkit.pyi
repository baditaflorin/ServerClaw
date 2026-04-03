from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT: Path
README_PATH: Path
PYYAML_INSTALL_HINT: str

def emit_cli_error(prefix: str, exc: Exception, *, exit_code: int = ...) -> int: ...
def load_json(path: str | Path) -> dict[str, Any]: ...
def load_yaml(path: str | Path) -> Any: ...
def repo_path(*parts: str) -> Path: ...
def resolve_repo_local_path(path_value: str | Path, *, repo_root: Path = ...) -> Path: ...
def run_command(
    command: Sequence[str],
    *,
    cwd: str | Path | None = ...,
    env: Mapping[str, str] | None = ...,
    check: bool = ...,
) -> Any: ...
def write_json(
    path: str | Path,
    payload: Any,
    *,
    indent: int = ...,
    sort_keys: bool = ...,
    mode: int | None = ...,
) -> None: ...
