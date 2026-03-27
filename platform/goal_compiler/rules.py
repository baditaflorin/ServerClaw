from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .schema import RiskClass


PLACEHOLDER_PATTERN = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


@dataclass(frozen=True)
class GroupAlias:
    services: list[str]
    workflow_id: str | None = None
    hosts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AliasConfig:
    phrase_aliases: dict[str, str]
    service_aliases: dict[str, str]
    groups: dict[str, GroupAlias]


@dataclass(frozen=True)
class RulePattern:
    kind: str
    value: str

    def match(self, text: str) -> dict[str, str] | None:
        if self.kind == "contains":
            return {} if self.value in text else None
        if self.kind == "regex":
            matched = re.fullmatch(self.value, text)
            return matched.groupdict() if matched else None
        if self.kind == "template":
            matched = re.fullmatch(_template_to_regex(self.value), text)
            return matched.groupdict() if matched else None
        raise ValueError(f"Unsupported rule pattern kind '{self.kind}'")


@dataclass(frozen=True)
class GoalRule:
    rule_id: str
    patterns: list[RulePattern]
    action: str
    target_kind: str
    default_risk_class: RiskClass
    allowed_tools: list[str]
    rollback_path: str | None
    requires_approval_above: RiskClass
    ttl_seconds: int
    workflow_id: str | None
    workflow_candidates: list[str]
    success_criteria: list[str]
    preconditions: list[str]
    scope_defaults: dict[str, list[Any]]

    def match(self, text: str) -> dict[str, str] | None:
        for pattern in self.patterns:
            captures = pattern.match(text)
            if captures is not None:
                return captures
        return None


def _template_to_regex(template: str) -> str:
    cursor = 0
    parts = ["^"]
    for match in PLACEHOLDER_PATTERN.finditer(template):
        literal = template[cursor : match.start()]
        parts.append(re.escape(literal))
        placeholder = match.group(1)
        parts.append(f"(?P<{placeholder}>[a-z0-9_./ -]+?)")
        cursor = match.end()
    parts.append(re.escape(template[cursor:]))
    parts.append("$")
    return "".join(parts)


def load_alias_config(path: Path) -> AliasConfig:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    groups: dict[str, GroupAlias] = {}
    for name, data in (payload.get("groups") or {}).items():
        groups[str(name)] = GroupAlias(
            services=list(data.get("services", [])),
            workflow_id=data.get("workflow_id"),
            hosts=list(data.get("hosts", [])),
        )
    return AliasConfig(
        phrase_aliases={str(key): str(value) for key, value in (payload.get("phrase_aliases") or {}).items()},
        service_aliases={str(key): str(value) for key, value in (payload.get("service_aliases") or {}).items()},
        groups=groups,
    )


def load_goal_rules(path: Path) -> list[GoalRule]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules = []
    for item in payload.get("rules", []):
        patterns = [
            RulePattern(kind=str(pattern["type"]), value=str(pattern["value"]))
            for pattern in item.get("patterns", [])
        ]
        rules.append(
            GoalRule(
                rule_id=str(item["id"]),
                patterns=patterns,
                action=str(item["action"]),
                target_kind=str(item.get("target_kind", "service")),
                default_risk_class=RiskClass(str(item["default_risk_class"])),
                allowed_tools=[str(tool) for tool in item.get("allowed_tools", [])],
                rollback_path=item.get("rollback_path"),
                requires_approval_above=RiskClass(str(item.get("requires_approval_above", "LOW"))),
                ttl_seconds=int(item.get("ttl_seconds", 300)),
                workflow_id=item.get("workflow_id"),
                workflow_candidates=[str(value) for value in item.get("workflow_candidates", [])],
                success_criteria=[str(value) for value in item.get("success_criteria", [])],
                preconditions=[str(value) for value in item.get("preconditions", [])],
                scope_defaults={
                    "allowed_hosts": list(item.get("scope_defaults", {}).get("allowed_hosts", [])),
                    "allowed_services": list(item.get("scope_defaults", {}).get("allowed_services", [])),
                    "allowed_vmids": list(item.get("scope_defaults", {}).get("allowed_vmids", [])),
                },
            )
        )
    return rules


def match_rule(text: str, rules: list[GoalRule]) -> tuple[GoalRule, dict[str, str]] | None:
    for rule in rules:
        captures = rule.match(text)
        if captures is not None:
            return rule, captures
    return None
