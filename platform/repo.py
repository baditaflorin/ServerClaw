from __future__ import annotations

import json
import re
import subprocess
import sys
from ast import literal_eval
from pathlib import Path, PurePosixPath
from typing import Any, Final


REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
# The Ansible inventory hostname of the hypervisor / topology host.
# Used by 25+ scripts that read host_vars for topology data.
# ADR 0407: centralized here to keep the deployment-specific name in one place.
TOPOLOGY_HOST: Final[str] = "proxmox_florin"
TOPOLOGY_HOST_VARS_PATH: Final[Path] = REPO_ROOT / "inventory" / "host_vars" / f"{TOPOLOGY_HOST}.yml"
PACKAGED_SIBLING_DIRS: Final[set[str]] = {"config"}
MAKEFILE_PATH: Final[Path] = REPO_ROOT / "Makefile"
README_PATH: Final[Path] = REPO_ROOT / "README.md"
RECEIPTS_DIR: Final[Path] = REPO_ROOT / "receipts" / "live-applies"
MAKE_TARGET_PATTERN: Final[re.Pattern[str]] = re.compile(r"^([A-Za-z0-9_-]+):")
WINDOWS_ABSOLUTE_PATH_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z]:/")
PYYAML_INSTALL_HINT: Final[str] = (
    "Missing dependency: PyYAML. Run via 'uvx --from pyyaml python ...' or 'uv run --with pyyaml ...'."
)
_MISSING = object()


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _shared_worktree_root() -> Path | None:
    if REPO_ROOT.parent.name != ".worktrees":
        return None
    return REPO_ROOT.parent.parent


def shared_repo_root(repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    if root.parent.name == ".worktrees":
        return root.parent.parent
    return root


def _shared_repo_root(repo_root: Path = REPO_ROOT) -> Path:
    return shared_repo_root(repo_root)


def local_overlay_root(repo_root: Path | None = None) -> Path:
    return shared_repo_root(repo_root) / ".local"


def resolve_local_overlay_path(path_value: str | Path, *, repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    path = Path(path_value).expanduser()
    if _path_exists(path):
        return path

    if not path.is_absolute():
        if path.parts and path.parts[0] == ".local":
            return local_overlay_root(root).joinpath(*path.parts[1:])
        candidate = root / path
        return candidate if _path_exists(candidate) else candidate

    marker = ".local"
    if marker not in path.parts:
        return path
    marker_index = path.parts.index(marker)
    return local_overlay_root(root).joinpath(*path.parts[marker_index + 1 :])


def repo_path(*parts: str) -> Path:
    if not parts:
        return REPO_ROOT

    candidate = REPO_ROOT.joinpath(*parts)
    if _path_exists(candidate):
        return candidate

    head = parts[0]
    if head in PACKAGED_SIBLING_DIRS:
        sibling_root = REPO_ROOT.parent / head
        if _path_exists(sibling_root):
            return sibling_root.joinpath(*parts[1:])

    if head == ".local":
        return local_overlay_root(REPO_ROOT).joinpath(*parts[1:])

    return candidate


def resolve_repo_local_path(path_value: str | Path, *, repo_root: Path = REPO_ROOT) -> Path:
    return resolve_local_overlay_path(path_value, repo_root=Path(repo_root))


def validate_repo_relative_path(value: str, *, label: str = "path") -> str:
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        raise ValueError(f"{label} must be a non-empty string")
    if normalized.startswith("/") or normalized.startswith("~") or WINDOWS_ABSOLUTE_PATH_PATTERN.match(normalized):
        raise ValueError(f"{label} must be repository-relative, not absolute")
    if ".." in PurePosixPath(normalized).parts:
        raise ValueError(f"{label} must stay within the repository root")
    return normalized


WORKFLOW_CATALOG_PATH: Final[Path] = repo_path("config", "workflow-catalog.json")
SECRET_MANIFEST_PATH: Final[Path] = repo_path("config", "controller-local-secrets.json")


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


def _strip_inline_comment(value: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(value):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            if index == 0 or value[index - 1].isspace():
                return value[:index].rstrip()
    return value.rstrip()


def _find_mapping_separator(content: str) -> int | None:
    in_single = False
    in_double = False
    for index, char in enumerate(content):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == ":" and not in_single and not in_double:
            if index == len(content) - 1 or content[index + 1].isspace():
                return index
    return None


def _split_key_value(content: str) -> tuple[str, str | None]:
    separator_index = _find_mapping_separator(content)
    if separator_index is not None:
        key = content[:separator_index].strip()
        value = content[separator_index + 1 :].strip()
        return key, value
    raise ValueError(f"Unsupported YAML line (missing ':'): {content}")


def _parse_simple_scalar(value: str) -> Any:
    value = _strip_inline_comment(value).strip()
    if not value:
        return ""
    if value in {"null", "~"}:
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "[]":
        return []
    if value == "{}":
        return {}
    if value[0] in {"'", '"'} and value[-1] == value[0]:
        return literal_eval(value)
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def _load_yaml_without_pyyaml(path: Path) -> Any:
    raw_lines = path.read_text().splitlines()
    tokens: list[tuple[int, str]] = []
    for raw_line in raw_lines:
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        content = _strip_inline_comment(raw_line[indent:]).rstrip()
        if not content:
            continue
        tokens.append((indent, content))

    def parse_mapping_entry(index: int, indent: int, mapping: dict[str, Any]) -> int:
        if index >= len(tokens):
            return index
        line_indent, content = tokens[index]
        if line_indent != indent or content.startswith("- "):
            return index
        key, value = _split_key_value(content)
        if not key:
            raise ValueError(f"{path}:{index + 1} defines an empty YAML key")
        index += 1
        if value:
            mapping[key] = _parse_simple_scalar(value)
            return index
        if index < len(tokens) and tokens[index][0] > indent:
            child_indent = tokens[index][0]
            child, index = parse_block(index, child_indent)
            mapping[key] = child
            return index
        mapping[key] = None
        return index

    def parse_mapping(index: int, indent: int, initial: dict[str, Any] | None = None) -> tuple[dict[str, Any], int]:
        mapping: dict[str, Any] = {} if initial is None else initial
        while index < len(tokens):
            line_indent, content = tokens[index]
            if line_indent < indent:
                break
            if line_indent > indent:
                raise ValueError(f"{path}:{index + 1} has unexpected indentation")
            if content.startswith("- "):
                break
            index = parse_mapping_entry(index, indent, mapping)
        return mapping, index

    def parse_list(index: int, indent: int) -> tuple[list[Any], int]:
        items: list[Any] = []
        while index < len(tokens):
            line_indent, content = tokens[index]
            if line_indent < indent:
                break
            if line_indent > indent:
                raise ValueError(f"{path}:{index + 1} has unexpected indentation")
            if not content.startswith("- "):
                break
            item_content = content[2:].strip()
            index += 1
            if not item_content:
                if index < len(tokens) and tokens[index][0] > indent:
                    child_indent = tokens[index][0]
                    item, index = parse_block(index, child_indent)
                else:
                    item = None
                items.append(item)
                continue
            if _find_mapping_separator(item_content) is not None:
                key, value = _split_key_value(item_content)
                mapping: dict[str, Any] = {}
                if value:
                    mapping[key] = _parse_simple_scalar(value)
                elif index < len(tokens) and tokens[index][0] > indent:
                    child_indent = tokens[index][0]
                    child, index = parse_block(index, child_indent)
                    mapping[key] = child
                else:
                    mapping[key] = None
                if index < len(tokens) and tokens[index][0] > indent:
                    child_indent = tokens[index][0]
                    if child_indent == indent + 2 and not tokens[index][1].startswith("- "):
                        mapping, index = parse_mapping(index, child_indent, mapping)
                items.append(mapping)
                continue
            items.append(_parse_simple_scalar(item_content))
        return items, index

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(tokens):
            return None, index
        if tokens[index][1].startswith("- "):
            return parse_list(index, indent)
        return parse_mapping(index, indent)

    if not tokens:
        return None
    payload, index = parse_block(0, tokens[0][0])
    if index != len(tokens):
        raise ValueError(f"{path} contains unsupported YAML near line {index + 1}")
    return payload


def load_yaml(path: Path) -> Any:
    try:
        import yaml  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:  # pragma: no cover - direct runtime guard
        try:
            return _load_yaml_without_pyyaml(path)
        except ValueError as parse_error:
            raise RuntimeError(PYYAML_INSTALL_HINT) from parse_error
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
