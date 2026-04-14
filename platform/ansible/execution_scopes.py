from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform.execution_lanes import LaneRegistry, load_execution_lane_catalog
from platform.repo import REPO_ROOT, load_yaml, local_overlay_root


CATALOG_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"
INVENTORY_PATH = REPO_ROOT / "inventory" / "hosts.yml"
ALLOWED_MUTATION_SCOPES = {"host", "lane", "platform"}
ALLOWED_EXECUTION_CLASSES = {"mutation", "diagnostic"}
LIST_HOSTS_HEADER_PATTERN = re.compile(r"^\s+hosts \(\d+\):$")
IMPORT_PLAYBOOK_PATTERN = re.compile(r"^\s*-\s*import_playbook:\s*(?P<path>.+?)\s*$")
SHARD_COMPAT_EXCLUDES = {".ansible", ".git"}
ENV_DEFAULT_EXPR_PATTERN = re.compile(
    r"{{\s*env\s*\|\s*default\(\s*['\"](?P<default>[^'\"]+)['\"]\s*\)\s*}}"
)
ENV_TERNARY_EXPR_PATTERN = re.compile(
    r"{{\s*['\"](?P<when_true>[^'\"]+)['\"]\s*if\s*\(\s*env\s*\|\s*default\(\s*['\"](?P<default>[^'\"]+)['\"]\s*\)\s*\)\s*==\s*['\"](?P<expected>[^'\"]+)['\"]\s*else\s*['\"](?P<when_false>[^'\"]+)['\"]\s*}}"
)
DEFAULT_LANE_RESERVATION_TTL_SECONDS = int(os.environ.get("LV3_EXECUTION_LANE_TTL_SECONDS", "14400"))


class AnsibleExecutionScopeError(RuntimeError):
    """Raised when the execution scope catalog or playbook resolution is invalid."""


@dataclass(frozen=True)
class ScopeCatalogEntry:
    playbook_path: str
    playbook_id: str
    mutation_scope: str
    execution_class: str
    shared_surfaces: tuple[str, ...]
    target_lane: str | None = None
    host_pattern_var: str | None = None
    integration_only: bool = False


@dataclass(frozen=True)
class ResolvedPlaybookScope:
    playbook_path: str
    playbook_id: str
    mutation_scope: str
    execution_class: str
    shared_surfaces: tuple[str, ...]
    target_lane: str | None
    host_pattern_var: str | None
    integration_only: bool
    source_leaf_playbooks: tuple[str, ...]


@dataclass(frozen=True)
class PlannedPlaybookExecution:
    playbook_path: str
    env: str
    run_id: str
    mutation_scope: str
    execution_class: str
    target_lane: str | None
    target_hosts: tuple[str, ...]
    limit_expression: str
    inventory_shard_path: str
    shared_surfaces: tuple[str, ...]
    source_leaf_playbooks: tuple[str, ...]


def normalize_repo_path(path: str | Path, *, repo_root: Path = REPO_ROOT) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (repo_root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    try:
        return candidate.relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise AnsibleExecutionScopeError(f"path '{candidate}' is outside repo root '{repo_root}'") from exc


def load_scope_catalog(*, catalog_path: Path = CATALOG_PATH, repo_root: Path = REPO_ROOT) -> dict[str, ScopeCatalogEntry]:
    payload = load_yaml(catalog_path)
    if not isinstance(payload, dict):
        raise AnsibleExecutionScopeError(f"{catalog_path} must define a mapping")
    playbooks = payload.get("playbooks")
    if not isinstance(playbooks, dict) or not playbooks:
        raise AnsibleExecutionScopeError(f"{catalog_path} must define a non-empty 'playbooks' mapping")

    catalog: dict[str, ScopeCatalogEntry] = {}
    for raw_path, raw_entry in playbooks.items():
        playbook_path = normalize_repo_path(raw_path, repo_root=repo_root)
        if not isinstance(raw_entry, dict):
            raise AnsibleExecutionScopeError(f"{catalog_path}:{raw_path} must define a mapping")

        playbook_id = raw_entry.get("playbook_id")
        if not isinstance(playbook_id, str) or not playbook_id.strip():
            raise AnsibleExecutionScopeError(f"{catalog_path}:{raw_path}.playbook_id must be a non-empty string")

        mutation_scope = raw_entry.get("mutation_scope")
        if mutation_scope not in ALLOWED_MUTATION_SCOPES:
            raise AnsibleExecutionScopeError(
                f"{catalog_path}:{raw_path}.mutation_scope must be one of {sorted(ALLOWED_MUTATION_SCOPES)}"
            )

        execution_class = raw_entry.get("execution_class", "mutation")
        if execution_class not in ALLOWED_EXECUTION_CLASSES:
            raise AnsibleExecutionScopeError(
                f"{catalog_path}:{raw_path}.execution_class must be one of {sorted(ALLOWED_EXECUTION_CLASSES)}"
            )

        raw_shared_surfaces = raw_entry.get("shared_surfaces", [])
        if not isinstance(raw_shared_surfaces, list):
            raise AnsibleExecutionScopeError(f"{catalog_path}:{raw_path}.shared_surfaces must be a list")
        shared_surfaces: list[str] = []
        for index, surface in enumerate(raw_shared_surfaces):
            if not isinstance(surface, str) or not surface.strip():
                raise AnsibleExecutionScopeError(
                    f"{catalog_path}:{raw_path}.shared_surfaces[{index}] must be a non-empty string"
                )
            shared_surfaces.append(surface.strip())

        target_lane = raw_entry.get("target_lane")
        if target_lane is not None and (not isinstance(target_lane, str) or not target_lane.strip()):
            raise AnsibleExecutionScopeError(f"{catalog_path}:{raw_path}.target_lane must be a non-empty string")
        if mutation_scope == "lane" and not target_lane:
            raise AnsibleExecutionScopeError(f"{catalog_path}:{raw_path} lane scope requires target_lane")

        host_pattern_var = raw_entry.get("host_pattern_var")
        if host_pattern_var is not None and (not isinstance(host_pattern_var, str) or not host_pattern_var.strip()):
            raise AnsibleExecutionScopeError(f"{catalog_path}:{raw_path}.host_pattern_var must be a non-empty string")

        integration_only = raw_entry.get("integration_only", False)
        if not isinstance(integration_only, bool):
            raise AnsibleExecutionScopeError(f"{catalog_path}:{raw_path}.integration_only must be boolean")

        catalog[playbook_path] = ScopeCatalogEntry(
            playbook_path=playbook_path,
            playbook_id=playbook_id.strip(),
            mutation_scope=mutation_scope,
            execution_class=execution_class,
            shared_surfaces=tuple(shared_surfaces),
            target_lane=target_lane.strip() if isinstance(target_lane, str) else None,
            host_pattern_var=host_pattern_var.strip() if isinstance(host_pattern_var, str) else None,
            integration_only=integration_only,
        )

    return catalog


def _read_import_playbooks(playbook_path: Path) -> list[str]:
    imports: list[str] = []
    for raw_line in playbook_path.read_text(encoding="utf-8").splitlines():
        match = IMPORT_PLAYBOOK_PATTERN.match(raw_line)
        if not match:
            continue
        import_path = match.group("path").strip().strip("'\"")
        if not import_path:
            continue
        imports.append(import_path)
    return imports


def _unique_preserving_order(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


def _render_hosts_expression(raw_hosts: str, *, env: str) -> str:
    rendered = " ".join(raw_hosts.split())

    def _replace_ternary(match: re.Match[str]) -> str:
        effective_env = env or match.group("default")
        return match.group("when_true") if effective_env == match.group("expected") else match.group("when_false")

    def _replace_env_default(match: re.Match[str]) -> str:
        return env or match.group("default")

    previous = None
    while rendered != previous:
        previous = rendered
        rendered = ENV_TERNARY_EXPR_PATTERN.sub(_replace_ternary, rendered)
        rendered = ENV_DEFAULT_EXPR_PATTERN.sub(_replace_env_default, rendered)

    if "{{" in rendered or "}}" in rendered:
        raise AnsibleExecutionScopeError(f"unsupported hosts expression: {raw_hosts!r}")
    return rendered.strip()


def _parse_extra_vars_payload(payload: str, *, repo_root: Path) -> dict[str, Any]:
    payload = payload.strip()
    if not payload:
        raise AnsibleExecutionScopeError("extra-vars payload must not be empty")
    if payload.startswith("@"):
        extra_vars_path = Path(payload[1:])
        if not extra_vars_path.is_absolute():
            extra_vars_path = (repo_root / extra_vars_path).resolve()
        loaded_payload = load_yaml(extra_vars_path)
        if not isinstance(loaded_payload, dict):
            raise AnsibleExecutionScopeError(f"extra-vars file '{extra_vars_path}' must contain a mapping")
        return {str(key): value for key, value in loaded_payload.items()}
    if payload.startswith("{"):
        loaded_payload = json.loads(payload)
        if not isinstance(loaded_payload, dict):
            raise AnsibleExecutionScopeError("JSON extra-vars payload must contain an object")
        return {str(key): value for key, value in loaded_payload.items()}

    extra_vars: dict[str, Any] = {}
    for token in shlex.split(payload):
        if "=" not in token:
            raise AnsibleExecutionScopeError(f"unsupported extra-vars token: {token!r}")
        key, value = token.split("=", 1)
        if not key:
            raise AnsibleExecutionScopeError(f"extra-vars token must define a key: {token!r}")
        extra_vars[key] = value
    return extra_vars


def extract_extra_vars_from_passthrough(
    passthrough_args: list[str] | None,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    if not passthrough_args:
        return {}

    extra_vars: dict[str, Any] = {}
    index = 0
    while index < len(passthrough_args):
        token = passthrough_args[index]
        payload: str | None = None
        if token in {"-e", "--extra-vars"}:
            if index + 1 >= len(passthrough_args):
                raise AnsibleExecutionScopeError(f"{token} requires a payload")
            payload = passthrough_args[index + 1]
            index += 2
        elif token.startswith("--extra-vars="):
            payload = token.split("=", 1)[1]
            index += 1
        elif token.startswith("-e") and token != "-e":
            payload = token[2:]
            index += 1
        else:
            index += 1
            continue

        extra_vars.update(_parse_extra_vars_payload(payload, repo_root=repo_root))
    return extra_vars


def _collect_inventory_hosts(payload: Any) -> tuple[str, ...]:
    hosts: list[str] = []

    def visit(node: Any) -> None:
        if not isinstance(node, dict):
            return
        node_hosts = node.get("hosts")
        if isinstance(node_hosts, dict):
            hosts.extend(str(host) for host in node_hosts.keys())
        children = node.get("children")
        if isinstance(children, dict):
            for child in children.values():
                visit(child)
        for value in node.values():
            if value is node_hosts or value is children:
                continue
            visit(value)

    visit(payload)
    return _unique_preserving_order(hosts)


def _expand_inventory_limit(
    limit_expression: str,
    *,
    env: str,
    inventory_path: Path,
    repo_root: Path,
    ansible_inventory_bin: str,
) -> tuple[str, ...]:
    if limit_expression == "localhost":
        return ("localhost",)
    command = [
        ansible_inventory_bin,
        "-i",
        str(inventory_path),
        "-l",
        limit_expression,
        "--list",
        "--yaml",
        "-e",
        f"env={env}",
    ]
    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AnsibleExecutionScopeError(
            f"failed to expand inventory limit '{limit_expression}': {result.stderr.strip() or result.stdout.strip()}"
        )
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
        raise AnsibleExecutionScopeError("PyYAML is required to expand inventory host limits") from exc
    payload = yaml.safe_load(result.stdout) or {}
    hosts = _collect_inventory_hosts(payload)
    if not hosts:
        raise AnsibleExecutionScopeError(f"inventory limit '{limit_expression}' resolved no hosts for env '{env}'")
    return hosts


def _discover_playbook_host_patterns(
    playbook: str | Path,
    *,
    env: str,
    repo_root: Path,
    _stack: tuple[str, ...] = (),
) -> tuple[str, ...]:
    playbook_path = normalize_repo_path(playbook, repo_root=repo_root)
    if playbook_path in _stack:
        cycle = " -> ".join([*_stack, playbook_path])
        raise AnsibleExecutionScopeError(f"import_playbook cycle detected while discovering hosts: {cycle}")

    candidate = (repo_root / playbook_path).resolve()
    if not candidate.exists():
        raise AnsibleExecutionScopeError(f"playbook '{playbook_path}' does not exist")

    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
        raise AnsibleExecutionScopeError("PyYAML is required to inspect playbook host expressions") from exc

    payload = yaml.safe_load(candidate.read_text(encoding="utf-8"))
    if payload is None:
        return ()
    if not isinstance(payload, list):
        raise AnsibleExecutionScopeError(f"playbook '{playbook_path}' must contain a top-level list")

    patterns: list[str] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        raw_import = item.get("import_playbook")
        if isinstance(raw_import, str) and raw_import.strip():
            resolved_import = normalize_repo_path(candidate.parent / raw_import.strip().strip("'\""), repo_root=repo_root)
            patterns.extend(
                _discover_playbook_host_patterns(
                    resolved_import,
                    env=env,
                    repo_root=repo_root,
                    _stack=(*_stack, playbook_path),
                )
            )
        raw_hosts = item.get("hosts")
        if raw_hosts is None:
            continue
        if not isinstance(raw_hosts, str) or not raw_hosts.strip():
            raise AnsibleExecutionScopeError(f"playbook '{playbook_path}' has a non-string hosts entry")
        patterns.append(_render_hosts_expression(raw_hosts, env=env))

    return _unique_preserving_order(patterns)


def _aggregate_imported_scope(playbook_path: str, child_scopes: list[ResolvedPlaybookScope]) -> ResolvedPlaybookScope:
    if not child_scopes:
        raise AnsibleExecutionScopeError(f"playbook '{playbook_path}' does not define imports or a leaf catalog entry")
    if len(child_scopes) == 1:
        child = child_scopes[0]
        return ResolvedPlaybookScope(
            playbook_path=playbook_path,
            playbook_id=Path(playbook_path).stem,
            mutation_scope=child.mutation_scope,
            execution_class=child.execution_class,
            shared_surfaces=_unique_preserving_order([playbook_path, *child.shared_surfaces]),
            target_lane=child.target_lane,
            host_pattern_var=child.host_pattern_var,
            integration_only=child.integration_only,
            source_leaf_playbooks=child.source_leaf_playbooks,
        )

    execution_classes = {scope.execution_class for scope in child_scopes}
    execution_class = "diagnostic" if execution_classes == {"diagnostic"} else "mutation"
    child_lanes = {scope.target_lane for scope in child_scopes if scope.target_lane}
    if child_lanes and len(child_lanes) == 1 and all(scope.mutation_scope in {"host", "lane"} for scope in child_scopes):
        mutation_scope = "lane"
        target_lane = next(iter(child_lanes))
    else:
        mutation_scope = "platform"
        target_lane = None
    return ResolvedPlaybookScope(
        playbook_path=playbook_path,
        playbook_id=Path(playbook_path).stem,
        mutation_scope=mutation_scope,
        execution_class=execution_class,
        shared_surfaces=_unique_preserving_order(
            [playbook_path, *(surface for scope in child_scopes for surface in scope.shared_surfaces)]
        ),
        target_lane=target_lane,
        host_pattern_var=None,
        integration_only=playbook_path == "playbooks/site.yml",
        source_leaf_playbooks=_unique_preserving_order(
            [leaf for scope in child_scopes for leaf in scope.source_leaf_playbooks]
        ),
    )


def resolve_playbook_scope(
    playbook: str | Path,
    *,
    repo_root: Path = REPO_ROOT,
    catalog_path: Path = CATALOG_PATH,
    _cache: dict[str, ResolvedPlaybookScope] | None = None,
    _stack: tuple[str, ...] = (),
) -> ResolvedPlaybookScope:
    catalog = load_scope_catalog(catalog_path=catalog_path, repo_root=repo_root)
    cache = {} if _cache is None else _cache
    playbook_path = normalize_repo_path(playbook, repo_root=repo_root)
    if playbook_path in cache:
        return cache[playbook_path]
    if playbook_path in _stack:
        cycle = " -> ".join([*_stack, playbook_path])
        raise AnsibleExecutionScopeError(f"import_playbook cycle detected: {cycle}")

    if playbook_path in catalog:
        entry = catalog[playbook_path]
        resolved = ResolvedPlaybookScope(
            playbook_path=playbook_path,
            playbook_id=entry.playbook_id,
            mutation_scope=entry.mutation_scope,
            execution_class=entry.execution_class,
            shared_surfaces=_unique_preserving_order(
                [
                    playbook_path,
                    *entry.shared_surfaces,
                ]
            ),
            target_lane=entry.target_lane,
            host_pattern_var=entry.host_pattern_var,
            integration_only=entry.integration_only,
            source_leaf_playbooks=(playbook_path,),
        )
        cache[playbook_path] = resolved
        return resolved

    candidate = (repo_root / playbook_path).resolve()
    if not candidate.exists():
        raise AnsibleExecutionScopeError(f"playbook '{playbook_path}' does not exist")

    child_scopes: list[ResolvedPlaybookScope] = []
    for raw_import in _read_import_playbooks(candidate):
        resolved_import = normalize_repo_path(candidate.parent / raw_import, repo_root=repo_root)
        child_scopes.append(
            resolve_playbook_scope(
                resolved_import,
                repo_root=repo_root,
                catalog_path=catalog_path,
                _cache=cache,
                _stack=(*_stack, playbook_path),
            )
        )

    resolved = _aggregate_imported_scope(playbook_path, child_scopes)
    cache[playbook_path] = resolved
    return resolved


def discover_target_hosts(
    playbook: str | Path,
    *,
    env: str,
    inventory_path: Path = INVENTORY_PATH,
    repo_root: Path = REPO_ROOT,
    catalog_path: Path = CATALOG_PATH,
    extra_vars: dict[str, Any] | None = None,
    resolved_scope: ResolvedPlaybookScope | None = None,
    ansible_playbook_bin: str = "ansible-playbook",
    ansible_inventory_bin: str = "ansible-inventory",
) -> tuple[str, ...]:
    del ansible_playbook_bin
    playbook_path = normalize_repo_path(playbook, repo_root=repo_root)
    scope = resolved_scope
    if scope is None:
        try:
            scope = resolve_playbook_scope(playbook_path, repo_root=repo_root, catalog_path=catalog_path)
        except AnsibleExecutionScopeError as exc:
            if "does not define imports or a leaf catalog entry" not in str(exc):
                raise
            scope = None
    if scope and scope.host_pattern_var:
        if extra_vars is None:
            raise AnsibleExecutionScopeError(
                f"playbook '{playbook_path}' requires extra-vars to resolve host pattern '{scope.host_pattern_var}'"
            )
        raw_host_pattern = extra_vars.get(scope.host_pattern_var)
        if raw_host_pattern is None:
            raise AnsibleExecutionScopeError(
                f"playbook '{playbook_path}' requires extra-var '{scope.host_pattern_var}' to resolve target hosts"
            )
        host_pattern = str(raw_host_pattern).strip()
        if not host_pattern:
            raise AnsibleExecutionScopeError(
                f"playbook '{playbook_path}' resolved empty host pattern from extra-var '{scope.host_pattern_var}'"
            )
        host_patterns = (host_pattern,)
    else:
        host_patterns = _discover_playbook_host_patterns(playbook_path, env=env, repo_root=repo_root)
    if not host_patterns:
        raise AnsibleExecutionScopeError(f"playbook '{playbook_path}' resolved no host patterns for env '{env}'")
    hosts: list[str] = []
    for pattern in host_patterns:
        hosts.extend(
            _expand_inventory_limit(
                pattern,
                env=env,
                inventory_path=inventory_path,
                repo_root=repo_root,
                ansible_inventory_bin=ansible_inventory_bin,
            )
        )
    return _unique_preserving_order(hosts)


def _augment_localhost(payload: dict[str, Any]) -> dict[str, Any]:
    all_group = payload.setdefault("all", {})
    hosts = all_group.setdefault("hosts", {})
    if not isinstance(hosts, dict):
        raise AnsibleExecutionScopeError("inventory shard 'all.hosts' must be a mapping")
    localhost = hosts.setdefault("localhost", {})
    if not isinstance(localhost, dict):
        localhost = {}
        hosts["localhost"] = localhost
    localhost.setdefault("ansible_connection", "local")
    return payload


def ensure_shard_repo_compatibility(*, compat_root: Path, repo_root: Path = REPO_ROOT) -> None:
    compat_root.mkdir(parents=True, exist_ok=True)
    for source in repo_root.iterdir():
        if source.name in SHARD_COMPAT_EXCLUDES:
            continue
        target = compat_root / source.name
        if target.exists() or target.is_symlink():
            try:
                if target.resolve() == source.resolve():
                    continue
            except OSError:
                pass
            raise AnsibleExecutionScopeError(
                f"inventory shard compatibility path '{target}' already exists and does not point at '{source}'"
            )
        target.symlink_to(source, target_is_directory=source.is_dir())


def render_inventory_shard(
    *,
    target_hosts: tuple[str, ...],
    env: str,
    output_path: Path,
    inventory_path: Path = INVENTORY_PATH,
    repo_root: Path = REPO_ROOT,
    ansible_inventory_bin: str = "ansible-inventory",
) -> Path:
    non_local_hosts = [host for host in target_hosts if host != "localhost"]
    if non_local_hosts:
        command = [
            ansible_inventory_bin,
            "-i",
            str(inventory_path),
            "-l",
            ",".join(non_local_hosts),
            "--list",
            "--yaml",
            "-e",
            f"env={env}",
        ]
        result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            raise AnsibleExecutionScopeError(
                f"failed to render inventory shard for env '{env}': {result.stderr.strip() or result.stdout.strip()}"
            )
        try:
            import yaml
        except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
            raise AnsibleExecutionScopeError("PyYAML is required to render inventory shards") from exc
        payload = yaml.safe_load(result.stdout)
    else:
        payload = {"all": {"hosts": {}}}

    if "localhost" in target_hosts:
        payload = _augment_localhost(payload)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_shard_repo_compatibility(compat_root=output_path.parent.parent, repo_root=repo_root)
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
        raise AnsibleExecutionScopeError("PyYAML is required to render inventory shards") from exc
    output_path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
    return output_path


def plan_playbook_execution(
    playbook: str | Path,
    *,
    env: str,
    run_id: str | None = None,
    shard_root: Path | None = None,
    extra_vars: dict[str, Any] | None = None,
    inventory_path: Path = INVENTORY_PATH,
    repo_root: Path = REPO_ROOT,
    catalog_path: Path = CATALOG_PATH,
    ansible_playbook_bin: str = "ansible-playbook",
    ansible_inventory_bin: str = "ansible-inventory",
) -> PlannedPlaybookExecution:
    resolved_scope = resolve_playbook_scope(playbook, repo_root=repo_root, catalog_path=catalog_path)
    target_hosts = discover_target_hosts(
        playbook,
        env=env,
        inventory_path=inventory_path,
        repo_root=repo_root,
        catalog_path=catalog_path,
        extra_vars=extra_vars,
        resolved_scope=resolved_scope,
        ansible_playbook_bin=ansible_playbook_bin,
        ansible_inventory_bin=ansible_inventory_bin,
    )
    non_local_hosts = [host for host in target_hosts if host != "localhost"]
    if resolved_scope.mutation_scope == "host" and len(non_local_hosts) != 1:
        raise AnsibleExecutionScopeError(
            f"playbook '{resolved_scope.playbook_path}' is declared host scoped but resolves {len(non_local_hosts)} non-local hosts"
        )
    if resolved_scope.mutation_scope == "lane" and not resolved_scope.target_lane:
        raise AnsibleExecutionScopeError(
            f"playbook '{resolved_scope.playbook_path}' is declared lane scoped but does not declare target_lane"
        )

    effective_run_id = run_id or os.environ.get("PLATFORM_TRACE_ID") or uuid.uuid4().hex
    effective_shard_root = shard_root or (repo_root / ".ansible" / "shards" / effective_run_id)
    shard_path = effective_shard_root / f"{Path(resolved_scope.playbook_path).stem}-{env}.json"
    render_inventory_shard(
        target_hosts=target_hosts,
        env=env,
        output_path=shard_path,
        inventory_path=inventory_path,
        repo_root=repo_root,
        ansible_inventory_bin=ansible_inventory_bin,
    )

    derived_surfaces = [f"host:{host}" for host in non_local_hosts]
    if "localhost" in target_hosts:
        derived_surfaces.append("host:localhost")
    shared_surfaces = _unique_preserving_order([*resolved_scope.shared_surfaces, *derived_surfaces])
    return PlannedPlaybookExecution(
        playbook_path=resolved_scope.playbook_path,
        env=env,
        run_id=effective_run_id,
        mutation_scope=resolved_scope.mutation_scope,
        execution_class=resolved_scope.execution_class,
        target_lane=resolved_scope.target_lane,
        target_hosts=target_hosts,
        limit_expression=",".join(target_hosts),
        inventory_shard_path=str(shard_path),
        shared_surfaces=shared_surfaces,
        source_leaf_playbooks=resolved_scope.source_leaf_playbooks,
    )


def _collect_makefile_entrypoints(makefile_path: Path, repo_root: Path) -> tuple[str, ...]:
    entrypoints: list[str] = []
    for raw_line in makefile_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if "--playbook $(REPO_ROOT)/playbooks/services/$(service).yml" in line:
            entrypoints.extend(
                normalize_repo_path(path, repo_root=repo_root)
                for path in sorted((repo_root / "playbooks" / "services").glob("*.yml"))
                if not path.name.startswith("_")
            )
            continue
        if "--playbook $(REPO_ROOT)/playbooks/groups/$(group).yml" in line:
            entrypoints.extend(
                normalize_repo_path(path, repo_root=repo_root)
                for path in sorted((repo_root / "playbooks" / "groups").glob("*.yml"))
            )
            continue
        for pattern in (r"--playbook\s+\$\(REPO_ROOT\)/(?P<path>playbooks/[^\s]+\.yml)", r"\$\(REPO_ROOT\)/(?P<path>playbooks/[^\s]+\.yml)"):
            match = re.search(pattern, line)
            if not match:
                continue
            path = match.group("path")
            if "$(" in path:
                break
            if "--syntax-check" in line:
                break
            if path.startswith("playbooks/tasks/") or path.startswith("playbooks/vars/"):
                break
            if path.startswith("playbooks/services/_"):
                break
            entrypoints.append(normalize_repo_path(path, repo_root=repo_root))
            break
    return _unique_preserving_order(entrypoints)


def validate_scope_catalog(
    *,
    repo_root: Path = REPO_ROOT,
    catalog_path: Path = CATALOG_PATH,
    inventory_path: Path = INVENTORY_PATH,
) -> None:
    catalog = load_scope_catalog(catalog_path=catalog_path, repo_root=repo_root)
    inventory_payload = load_yaml(inventory_path)
    if not isinstance(inventory_payload, dict):
        raise AnsibleExecutionScopeError(f"{inventory_path} must define a mapping inventory")

    known_hosts = {"localhost"}
    for section in inventory_payload.values():
        if not isinstance(section, dict):
            continue
        children = section.get("children", {})
        if not isinstance(children, dict):
            continue
        for child in children.values():
            if not isinstance(child, dict):
                continue
            for host in (child.get("hosts") or {}).keys():
                known_hosts.add(str(host))

    for playbook_path, entry in catalog.items():
        candidate = repo_root / playbook_path
        if not candidate.exists():
            raise AnsibleExecutionScopeError(f"catalog entry '{playbook_path}' does not exist")
        if entry.mutation_scope == "lane" and not entry.target_lane:
            raise AnsibleExecutionScopeError(f"lane scoped playbook '{playbook_path}' must define target_lane")

    for playbook_path in _collect_makefile_entrypoints(repo_root / "Makefile", repo_root):
        resolved = resolve_playbook_scope(playbook_path, repo_root=repo_root, catalog_path=catalog_path)
        if resolved.execution_class == "mutation" and not resolved.shared_surfaces:
            raise AnsibleExecutionScopeError(f"playbook '{playbook_path}' resolved no shared surfaces")


def run_scoped_playbook(
    playbook: str | Path,
    *,
    env: str,
    passthrough_args: list[str] | None = None,
    run_id: str | None = None,
    shard_root: Path | None = None,
    inventory_path: Path = INVENTORY_PATH,
    repo_root: Path = REPO_ROOT,
    catalog_path: Path = CATALOG_PATH,
    ansible_playbook_bin: str = "ansible-playbook",
    ansible_inventory_bin: str = "ansible-inventory",
    lane_registry: LaneRegistry | None = None,
) -> subprocess.CompletedProcess[str]:
    extra_vars = extract_extra_vars_from_passthrough(passthrough_args, repo_root=repo_root)
    plan = plan_playbook_execution(
        playbook,
        env=env,
        run_id=run_id,
        shard_root=shard_root,
        extra_vars=extra_vars,
        inventory_path=inventory_path,
        repo_root=repo_root,
        catalog_path=catalog_path,
        ansible_playbook_bin=ansible_playbook_bin,
        ansible_inventory_bin=ansible_inventory_bin,
    )
    return run_planned_playbook(
        plan,
        passthrough_args=passthrough_args,
        inventory_path=inventory_path,
        repo_root=repo_root,
        ansible_playbook_bin=ansible_playbook_bin,
        lane_registry=lane_registry,
    )


@contextmanager
def _reserved_lane(
    plan: PlannedPlaybookExecution,
    *,
    repo_root: Path,
    lane_registry: LaneRegistry | None = None,
    ttl_seconds: int = DEFAULT_LANE_RESERVATION_TTL_SECONDS,
) -> Any:
    if plan.execution_class != "mutation" or not plan.target_lane:
        yield None
        return

    catalog = load_execution_lane_catalog(repo_root=repo_root)
    lane = catalog.lanes.get(plan.target_lane)
    if lane is None:
        raise AnsibleExecutionScopeError(f"target lane '{plan.target_lane}' is not defined in config/execution-lanes.yaml")
    if not lane.hostname:
        raise AnsibleExecutionScopeError(f"target lane '{plan.target_lane}' does not declare a hostname")

    registry = lane_registry or LaneRegistry(repo_root=repo_root)
    actor_intent_id = f"ansible-scope:{plan.run_id}"
    reservation = registry.reserve(
        {
            "workflow_id": f"ansible-scope:{plan.playbook_path}",
            "target_vm": lane.hostname,
            "arguments": {
                "target_vm": lane.hostname,
            },
        },
        actor_intent_id=actor_intent_id,
        ttl_seconds=ttl_seconds,
    )
    if reservation.status != "acquired":
        yield reservation
        return

    try:
        yield reservation
    finally:
        registry.release(actor_intent_id)


def _resolve_identity_override(repo_root: Path) -> list[str]:
    """Return extra-vars args for the local identity overlay (ADR 0407).

    If ``.local/identity.yml`` exists, it is injected as ``-e @path`` so that
    deployment-specific values (real domain, operator name) override the
    generic defaults committed in ``inventory/group_vars/all/identity.yml``.
    """
    # .local/ is always relative to the shared repo root, even from worktrees.
    local_identity = local_overlay_root(repo_root) / "identity.yml"
    if local_identity.is_file():
        return ["-e", f"@{local_identity}"]
    return []


def run_planned_playbook(
    plan: PlannedPlaybookExecution,
    *,
    passthrough_args: list[str] | None = None,
    inventory_path: Path = INVENTORY_PATH,
    repo_root: Path = REPO_ROOT,
    ansible_playbook_bin: str = "ansible-playbook",
    lane_registry: LaneRegistry | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        ansible_playbook_bin,
        "-i",
        str(inventory_path),
        "-i",
        plan.inventory_shard_path,
        "--limit",
        plan.limit_expression,
        str(repo_root / plan.playbook_path),
        "-e",
        f"env={plan.env}",
        *_resolve_identity_override(repo_root),
        *(passthrough_args or []),
    ]
    with _reserved_lane(plan, repo_root=repo_root, lane_registry=lane_registry) as lane_reservation:
        if lane_reservation is not None and lane_reservation.status != "acquired":
            stderr = (
                f"execution lane busy: {plan.target_lane} already has "
                f"{lane_reservation.active_count}/{lane_reservation.max_concurrent_ops} active operation(s)"
            )
            print(stderr, file=sys.stderr, flush=True)
            return subprocess.CompletedProcess(command, 3, stdout="", stderr=stderr)
        return subprocess.run(command, cwd=repo_root, text=True, check=False)
