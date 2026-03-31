from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform.repo import REPO_ROOT, load_json, load_yaml, repo_path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    yaml = None


SKILL_CATALOG_PATH = repo_path("config", "serverclaw", "skill-packs.yaml")
APPROVED_PORT_REFS_PATH = repo_path("config", "serverclaw", "approved-port-refs.json")
AGENT_TOOL_REGISTRY_PATH = repo_path("config", "agent-tool-registry.json")
FRONT_MATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
REF_CATEGORIES = ("tool_refs", "connector_refs", "browser_refs", "memory_refs", "search_refs")


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def _require_identifier(value: Any, path: str) -> str:
    value = _require_str(value, path)
    if not IDENTIFIER_PATTERN.match(value):
        raise ValueError(f"{path} must use lowercase letters, numbers, hyphens, or underscores")
    return value


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


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
    if separator_index is None:
        raise ValueError(f"unsupported YAML line (missing ':'): {content}")
    key = content[:separator_index].strip()
    value = content[separator_index + 1 :].strip()
    return key, value


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
        return json.loads(value) if value[0] == '"' else value[1:-1]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def _load_yaml_without_pyyaml(text: str, path: Path) -> Any:
    raw_lines = text.splitlines()
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
        mapping = {} if initial is None else initial
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
                if index < len(tokens) and tokens[index][0] > indent and not tokens[index][1].startswith("- "):
                    mapping, index = parse_mapping(index, tokens[index][0], mapping)
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


def _load_yaml_text(text: str, path: Path) -> dict[str, Any]:
    payload = (yaml.safe_load(text) if yaml is not None else _load_yaml_without_pyyaml(text, path)) or {}
    return _require_mapping(payload, str(path))


def _relative_to_repo(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


@dataclass(frozen=True)
class SkillPack:
    skill_id: str
    title: str
    description: str
    source_tier: str
    source_path: str
    prompt_markdown: str
    metadata: dict[str, Any]
    tool_refs: list[str]
    connector_refs: list[str]
    browser_refs: list[str]
    memory_refs: list[str]
    search_refs: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "title": self.title,
            "description": self.description,
            "source_tier": self.source_tier,
            "source_path": self.source_path,
            "prompt_markdown": self.prompt_markdown,
            "metadata": self.metadata,
            "tool_refs": self.tool_refs,
            "connector_refs": self.connector_refs,
            "browser_refs": self.browser_refs,
            "memory_refs": self.memory_refs,
            "search_refs": self.search_refs,
        }


class ServerClawSkillPackService:
    def __init__(
        self,
        *,
        repo_root: Path = REPO_ROOT,
        catalog_path: Path = SKILL_CATALOG_PATH,
        approved_port_refs_path: Path = APPROVED_PORT_REFS_PATH,
        tool_registry_path: Path = AGENT_TOOL_REGISTRY_PATH,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.catalog_path = catalog_path if catalog_path.is_absolute() else self.repo_root / catalog_path
        self.approved_port_refs_path = (
            approved_port_refs_path if approved_port_refs_path.is_absolute() else self.repo_root / approved_port_refs_path
        )
        self.tool_registry_path = tool_registry_path if tool_registry_path.is_absolute() else self.repo_root / tool_registry_path

        self.catalog = self._load_catalog()
        self.approved_port_refs = self._load_approved_port_refs()
        self.known_tool_refs = self._load_known_tool_refs()

    def _load_catalog(self) -> dict[str, Any]:
        payload = _require_mapping(load_yaml(self.catalog_path), str(self.catalog_path))
        if _require_str(payload.get("schema_version"), "config/serverclaw/skill-packs.yaml.schema_version") != "1.0.0":
            raise ValueError("config/serverclaw/skill-packs.yaml.schema_version must be 1.0.0")

        roots = _require_mapping(payload.get("skill_roots"), "config/serverclaw/skill-packs.yaml.skill_roots")
        for key in ("bundled", "shared", "imported", "workspaces"):
            _require_str(roots.get(key), f"config/serverclaw/skill-packs.yaml.skill_roots.{key}")

        _require_identifier(
            payload.get("default_workspace_id"),
            "config/serverclaw/skill-packs.yaml.default_workspace_id",
        )

        workspaces = _require_list(payload.get("workspaces"), "config/serverclaw/skill-packs.yaml.workspaces")
        seen_workspace_ids: set[str] = set()
        for index, workspace in enumerate(workspaces):
            workspace = _require_mapping(workspace, f"config/serverclaw/skill-packs.yaml.workspaces[{index}]")
            workspace_id = _require_identifier(
                workspace.get("id"),
                f"config/serverclaw/skill-packs.yaml.workspaces[{index}].id",
            )
            if workspace_id in seen_workspace_ids:
                raise ValueError(f"duplicate workspace id '{workspace_id}' in config/serverclaw/skill-packs.yaml")
            seen_workspace_ids.add(workspace_id)
            _require_str(workspace.get("title"), f"config/serverclaw/skill-packs.yaml.workspaces[{index}].title")
            _require_str(
                workspace.get("description"),
                f"config/serverclaw/skill-packs.yaml.workspaces[{index}].description",
            )

        imported = _require_list(
            payload.get("imported_skill_packs"),
            "config/serverclaw/skill-packs.yaml.imported_skill_packs",
        )
        seen_imported_ids: set[str] = set()
        for index, entry in enumerate(imported):
            entry = _require_mapping(entry, f"config/serverclaw/skill-packs.yaml.imported_skill_packs[{index}]")
            skill_id = _require_identifier(
                entry.get("skill_id"),
                f"config/serverclaw/skill-packs.yaml.imported_skill_packs[{index}].skill_id",
            )
            if skill_id in seen_imported_ids:
                raise ValueError(f"duplicate imported skill id '{skill_id}' in config/serverclaw/skill-packs.yaml")
            seen_imported_ids.add(skill_id)
            _require_str(
                entry.get("provider"),
                f"config/serverclaw/skill-packs.yaml.imported_skill_packs[{index}].provider",
            )
            _require_str(
                entry.get("source_url"),
                f"config/serverclaw/skill-packs.yaml.imported_skill_packs[{index}].source_url",
            )
            _require_str(
                entry.get("mirror_path"),
                f"config/serverclaw/skill-packs.yaml.imported_skill_packs[{index}].mirror_path",
            )
            if entry.get("review_state") != "mirrored_unreviewed":
                raise ValueError(
                    "config/serverclaw/skill-packs.yaml imported skill packs must stay mirrored_unreviewed until promoted into shared"
                )
            if entry.get("enabled") is not False:
                raise ValueError(
                    "config/serverclaw/skill-packs.yaml imported skill packs must stay disabled until promoted into config/serverclaw/skills/shared/"
                )

        return payload

    def _load_approved_port_refs(self) -> dict[str, set[str]]:
        payload = _require_mapping(load_json(self.approved_port_refs_path), str(self.approved_port_refs_path))
        if _require_str(payload.get("schema_version"), "config/serverclaw/approved-port-refs.json.schema_version") != "1.0.0":
            raise ValueError("config/serverclaw/approved-port-refs.json.schema_version must be 1.0.0")

        resolved: dict[str, set[str]] = {}
        for category in ("connector_refs", "browser_refs", "memory_refs", "search_refs"):
            refs = _require_list(payload.get(category), f"config/serverclaw/approved-port-refs.json.{category}")
            category_ids: set[str] = set()
            for index, entry in enumerate(refs):
                entry = _require_mapping(entry, f"config/serverclaw/approved-port-refs.json.{category}[{index}]")
                ref_id = _require_str(entry.get("id"), f"config/serverclaw/approved-port-refs.json.{category}[{index}].id")
                _require_str(
                    entry.get("description"),
                    f"config/serverclaw/approved-port-refs.json.{category}[{index}].description",
                )
                category_ids.add(ref_id)
            resolved[category] = category_ids
        return resolved

    def _load_known_tool_refs(self) -> set[str]:
        payload = _require_mapping(load_json(self.tool_registry_path), str(self.tool_registry_path))
        tools = _require_list(payload.get("tools"), "config/agent-tool-registry.json.tools")
        return {
            _require_str(_require_mapping(tool, "config/agent-tool-registry.json.tools[]").get("name"), "tool.name")
            for tool in tools
        }

    def _resolve_path(self, relative_path: str) -> Path:
        path = (self.repo_root / relative_path).resolve()
        try:
            path.relative_to(self.repo_root)
        except ValueError as exc:
            raise ValueError(f"path escapes repository root: {relative_path}") from exc
        return path

    def _root_paths(self) -> dict[str, Path]:
        roots = _require_mapping(self.catalog.get("skill_roots"), "config/serverclaw/skill-packs.yaml.skill_roots")
        return {
            "bundled": self._resolve_path(_require_str(roots.get("bundled"), "skill_roots.bundled")),
            "shared": self._resolve_path(_require_str(roots.get("shared"), "skill_roots.shared")),
            "imported": self._resolve_path(_require_str(roots.get("imported"), "skill_roots.imported")),
            "workspaces": self._resolve_path(_require_str(roots.get("workspaces"), "skill_roots.workspaces")),
        }

    def _workspace_catalog(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for entry in _require_list(self.catalog.get("workspaces"), "config/serverclaw/skill-packs.yaml.workspaces"):
            workspace = _require_mapping(entry, "config/serverclaw/skill-packs.yaml.workspaces[]")
            workspace_id = _require_identifier(workspace.get("id"), "workspace.id")
            result[workspace_id] = workspace
        return result

    def _validate_ref_lists(self, skill_id: str, refs: dict[str, list[str]]) -> None:
        for tool_ref in refs["tool_refs"]:
            if tool_ref not in self.known_tool_refs:
                raise ValueError(f"skill '{skill_id}' references unknown governed tool '{tool_ref}'")

        for category in ("connector_refs", "browser_refs", "memory_refs", "search_refs"):
            approved = self.approved_port_refs[category]
            for ref in refs[category]:
                if ref not in approved:
                    raise ValueError(f"skill '{skill_id}' references unapproved {category[:-5].replace('_', ' ')} '{ref}'")

    def _parse_skill_pack(self, skill_id: str, skill_file: Path, *, source_tier: str) -> SkillPack:
        raw_text = skill_file.read_text(encoding="utf-8")
        match = FRONT_MATTER_PATTERN.match(raw_text)
        if not match:
            raise ValueError(f"{skill_file} must start with YAML front matter")

        frontmatter = _load_yaml_text(match.group(1), skill_file)
        title = _require_str(frontmatter.get("name"), f"{skill_file}.name")
        description = _require_str(frontmatter.get("description"), f"{skill_file}.description")
        metadata = frontmatter.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{skill_file}.metadata must be valid JSON when supplied as a string") from exc
        metadata = _require_mapping(metadata, f"{skill_file}.metadata")
        lv3_meta = _require_mapping(metadata.get("lv3") or {}, f"{skill_file}.metadata.lv3")

        refs: dict[str, list[str]] = {}
        for category in REF_CATEGORIES:
            values = lv3_meta.get(category) or []
            refs[category] = _dedupe_strings(
                [_require_str(value, f"{skill_file}.metadata.lv3.{category}[]") for value in _require_list(values, f"{skill_file}.metadata.lv3.{category}")]
            )

        self._validate_ref_lists(skill_id, refs)

        prompt_markdown = raw_text[match.end() :].strip()
        if not prompt_markdown:
            raise ValueError(f"{skill_file} must contain prompt content after the front matter")

        return SkillPack(
            skill_id=skill_id,
            title=title,
            description=description,
            source_tier=source_tier,
            source_path=_relative_to_repo(skill_file, self.repo_root),
            prompt_markdown=prompt_markdown,
            metadata=metadata,
            tool_refs=refs["tool_refs"],
            connector_refs=refs["connector_refs"],
            browser_refs=refs["browser_refs"],
            memory_refs=refs["memory_refs"],
            search_refs=refs["search_refs"],
        )

    def _discover_skills(self, root: Path, *, source_tier: str) -> dict[str, SkillPack]:
        skills: dict[str, SkillPack] = {}
        if not root.exists():
            return skills
        for skill_file in sorted(root.rglob("SKILL.md")):
            skill_dir = skill_file.parent
            skill_id = _require_identifier(skill_dir.name, str(skill_dir))
            if skill_id in skills:
                raise ValueError(f"duplicate {source_tier} skill id '{skill_id}' under {root}")
            skills[skill_id] = self._parse_skill_pack(skill_id, skill_file, source_tier=source_tier)
        return skills

    def _workspace_root(self, workspace_id: str) -> Path:
        workspace = self._workspace_catalog().get(workspace_id)
        if workspace is None:
            raise FileNotFoundError(f"unknown workspace '{workspace_id}'")
        workspaces_root = self._root_paths()["workspaces"]
        return workspaces_root / workspace_id / "skills"

    def list_skill_packs(
        self,
        *,
        workspace_id: str | None = None,
        skill_id: str | None = None,
        include_imported: bool = True,
        include_prompt_manifest: bool = False,
    ) -> dict[str, Any]:
        resolved_workspace_id = workspace_id or _require_identifier(
            self.catalog.get("default_workspace_id"),
            "config/serverclaw/skill-packs.yaml.default_workspace_id",
        )
        if workspace_id is not None:
            resolved_workspace_id = _require_identifier(workspace_id, "workspace_id")

        roots = self._root_paths()
        bundled = self._discover_skills(roots["bundled"], source_tier="bundled")
        shared = self._discover_skills(roots["shared"], source_tier="shared")
        workspace = self._discover_skills(self._workspace_root(resolved_workspace_id), source_tier="workspace")

        active: dict[str, SkillPack] = {}
        shadowed: list[dict[str, Any]] = []
        for source_name, catalog in (("bundled", bundled), ("shared", shared), ("workspace", workspace)):
            for entry_skill_id, pack in sorted(catalog.items()):
                previous = active.get(entry_skill_id)
                active[entry_skill_id] = pack
                if previous is not None:
                    shadowed.append(
                        {
                            "skill_id": entry_skill_id,
                            "active_source_tier": source_name,
                            "shadowed_source_tier": previous.source_tier,
                            "shadowed_source_path": previous.source_path,
                        }
                    )

        if skill_id is not None:
            requested_skill_id = _require_identifier(skill_id, "skill_id")
            filtered = active.get(requested_skill_id)
            if filtered is None:
                raise FileNotFoundError(f"unknown active skill '{requested_skill_id}' for workspace '{resolved_workspace_id}'")
            active_skills = [filtered]
            shadowed_skills = [entry for entry in shadowed if entry["skill_id"] == requested_skill_id]
        else:
            active_skills = [active[key] for key in sorted(active)]
            shadowed_skills = shadowed

        imported_skills: list[dict[str, Any]] = []
        if include_imported:
            imported_catalog = {
                _require_identifier(entry["skill_id"], "imported.skill_id"): entry
                for entry in _require_list(
                    self.catalog.get("imported_skill_packs"),
                    "config/serverclaw/skill-packs.yaml.imported_skill_packs",
                )
            }
            discovered_imported = self._discover_skills(roots["imported"], source_tier="imported")
            for imported_skill_id, imported_skill in sorted(discovered_imported.items()):
                entry = imported_catalog.get(imported_skill_id)
                if entry is None:
                    raise ValueError(
                        f"imported skill '{imported_skill_id}' exists on disk but is missing from config/serverclaw/skill-packs.yaml"
                    )
                expected_path = self._resolve_path(_require_str(entry.get("mirror_path"), "imported.mirror_path"))
                if expected_path != self.repo_root / imported_skill.source_path:
                    raise ValueError(
                        f"imported skill '{imported_skill_id}' mirror_path does not match the committed SKILL.md location"
                    )
                imported_skills.append(
                    {
                        **imported_skill.to_dict(),
                        "provider": _require_str(entry.get("provider"), "imported.provider"),
                        "source_url": _require_str(entry.get("source_url"), "imported.source_url"),
                        "review_state": entry["review_state"],
                        "enabled": entry["enabled"],
                    }
                )

        prompt_manifest = [
            {
                "skill_id": pack.skill_id,
                "title": pack.title,
                "source_tier": pack.source_tier,
                "source_path": pack.source_path,
                "description": pack.description,
            }
            for pack in active_skills
        ]

        return {
            "workspace_id": resolved_workspace_id,
            "default_workspace_id": self.catalog["default_workspace_id"],
            "active_skill_count": len(active_skills),
            "active_skills": [pack.to_dict() for pack in active_skills],
            "shadowed_skills": shadowed_skills,
            "imported_skills": imported_skills,
            "prompt_manifest": prompt_manifest if include_prompt_manifest else [],
        }

    def validate_repository_contract(self) -> dict[str, Any]:
        summary = self.list_skill_packs(include_prompt_manifest=True)
        workspace_ids = sorted(self._workspace_catalog())
        if summary["active_skill_count"] == 0:
            raise ValueError("at least one active ServerClaw skill pack must be present")
        return {
            "default_workspace_id": self.catalog["default_workspace_id"],
            "workspace_ids": workspace_ids,
            "active_skill_count": summary["active_skill_count"],
            "imported_skill_count": len(summary["imported_skills"]),
        }


def list_serverclaw_skill_packs(
    *,
    repo_root: Path = REPO_ROOT,
    workspace_id: str | None = None,
    skill_id: str | None = None,
    include_imported: bool = True,
    include_prompt_manifest: bool = False,
) -> dict[str, Any]:
    service = ServerClawSkillPackService(repo_root=repo_root)
    return service.list_skill_packs(
        workspace_id=workspace_id,
        skill_id=skill_id,
        include_imported=include_imported,
        include_prompt_manifest=include_prompt_manifest,
    )


def validate_serverclaw_skill_pack_repository(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    service = ServerClawSkillPackService(repo_root=repo_root)
    return service.validate_repository_contract()
