#!/usr/bin/env python3

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from controller_automation_toolkit import load_yaml, repo_path


CONFIG_PATH = repo_path("config", "changelog-redaction.yaml")
SUPPORTED_SCHEMA_VERSION = "1.0.0"
STRIP_PLACEHOLDER = "[details omitted]"
REDACTED_VALUE = "[redacted]"
REDACTED_IP = "[redacted ip]"
REDACTED_HOST = "[redacted host]"

PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
)
ALLOWED_LEVELS = {"STRIP", "MASK", "SUMMARISE", "RETAIN"}
EMAIL_PATTERN = re.compile(r"\b([A-Za-z0-9._%+-]+)@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
INTERNAL_FQDN_PATTERN = re.compile(r"\b([a-z0-9][a-z0-9-]*)\.lv3\.internal\b")
VM_HOST_PATTERN = re.compile(r"\b([a-z0-9][a-z0-9-]*?)(?:-(?:lv3|vm))\b")
HV_TOKEN_PATTERN = re.compile(r"\bhvs\.[A-Za-z0-9_-]{10,}\b")
BEARER_TOKEN_PATTERN = re.compile(r"(?i)(Authorization\s*:\s*Bearer\s+)([^\s\"']+)")
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b([A-Za-z0-9_.-]*?(?:token|secret|password|passwd|api[_-]?key|client[_-]?secret)[A-Za-z0-9_.-]*)\b"
    r"(\s*[:=]\s*)([^\s,;)}]+)"
)
DETAIL_PATTERNS = (
    re.compile(r"Traceback \(most recent call last\):"),
    re.compile(r"\bFile \"/"),
    re.compile(r"/Users/"),
    re.compile(r"/usr/(?:local/)?lib/"),
)
RECEIPT_DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True)
class RedactionRule:
    field_pattern: str
    level: str
    mask_fn: str | None = None
    summarise_fn: str | None = None


def _path_segments(path: str) -> list[str]:
    return [part for part in path.split(".") if part]


def _pattern_matches(pattern: str, path: str) -> bool:
    pattern_parts = _path_segments(pattern)
    path_parts = _path_segments(path)
    if len(pattern_parts) != len(path_parts):
        return False
    for expected, actual in zip(pattern_parts, path_parts):
        if expected != "*" and expected != actual:
            return False
    return True


def _sanitize_host_label(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return candidate
    for suffix in ("-lv3", "-vm"):
        if candidate.endswith(suffix):
            return candidate[: -len(suffix)]
    return candidate


def _stringify(value: Any) -> str:
    return "" if value is None else str(value)


def mask_identity_prefix(value: Any) -> Any:
    if isinstance(value, list):
        return [mask_identity_prefix(item) for item in value]
    if isinstance(value, dict):
        return {key: mask_identity_prefix(item) for key, item in value.items()}
    text = _stringify(value).strip()
    if not text:
        return text
    if "@" in text:
        return text.split("@", 1)[0]
    if "/" in text:
        return text.split("/", 1)[0]
    return text


def mask_host_labels(value: Any) -> Any:
    if isinstance(value, list):
        return [mask_host_labels(item) for item in value]
    text = _stringify(value)
    return redact_inline_text(_sanitize_host_label(text))


def mask_target_labels(value: Any) -> Any:
    if not isinstance(value, list):
        return redact_inline_text(_stringify(value))
    result = []
    for item in value:
        text = _stringify(item)
        if ":" in text:
            kind, label = text.split(":", 1)
            result.append(f"{kind}:{redact_inline_text(_sanitize_host_label(label))}")
            continue
        result.append(redact_inline_text(_sanitize_host_label(text)))
    return result


def count_keys(value: Any) -> str:
    if isinstance(value, dict):
        return f"{{{len(value)} params}}"
    if isinstance(value, list):
        return f"{{{len(value)} items}}"
    return STRIP_PLACEHOLDER


def key_names_only(value: Any) -> str:
    if isinstance(value, dict):
        keys = sorted(str(key) for key in value.keys())
        return ", ".join(keys) if keys else "{0 vars}"
    return STRIP_PLACEHOLDER


def receipt_reference(value: Any) -> str:
    match = RECEIPT_DATE_PATTERN.search(_stringify(value))
    if match:
        return f"receipt recorded {match.group(1)}"
    return "[receipt reference omitted]"


def redact_inline_text(value: Any) -> str:
    text = _stringify(value)
    if not text:
        return text
    if any(pattern.search(text) for pattern in DETAIL_PATTERNS):
        return STRIP_PLACEHOLDER

    text = BEARER_TOKEN_PATTERN.sub(r"\1" + REDACTED_VALUE, text)
    text = HV_TOKEN_PATTERN.sub(REDACTED_VALUE, text)
    text = SECRET_ASSIGNMENT_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}{REDACTED_VALUE}", text)
    text = EMAIL_PATTERN.sub(lambda match: match.group(1), text)
    text = INTERNAL_FQDN_PATTERN.sub(lambda match: _sanitize_host_label(match.group(1)), text)
    text = VM_HOST_PATTERN.sub(lambda match: _sanitize_host_label(match.group(0)), text)
    return IP_PATTERN.sub(_mask_ip_match, text)


def _mask_ip_match(match: re.Match[str]) -> str:
    candidate = match.group(0)
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return candidate
    if any(address in network for network in PRIVATE_NETWORKS):
        return REDACTED_IP
    return candidate


def load_redaction_policy(path: Path = CONFIG_PATH) -> dict[str, Any]:
    policy = load_yaml(path)
    validate_redaction_policy(policy, path=path)
    return policy


def validate_redaction_policy(policy: Any, *, path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not isinstance(policy, dict):
        raise ValueError(f"{path} must be a mapping")
    if policy.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(f"{path}.schema_version must be {SUPPORTED_SCHEMA_VERSION}")
    rules = policy.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError(f"{path}.rules must be a non-empty list")
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError(f"{path}.rules[{index}] must be a mapping")
        field_pattern = rule.get("field_pattern")
        if not isinstance(field_pattern, str) or not field_pattern.strip():
            raise ValueError(f"{path}.rules[{index}].field_pattern must be a non-empty string")
        level = rule.get("level")
        if level not in ALLOWED_LEVELS:
            raise ValueError(f"{path}.rules[{index}].level must be one of {sorted(ALLOWED_LEVELS)}")
        if level == "MASK":
            mask_fn = rule.get("mask_fn")
            if mask_fn not in {"identity_prefix", "host_labels", "target_labels", "redact_inline_text"}:
                raise ValueError(f"{path}.rules[{index}].mask_fn is not supported")
        if level == "SUMMARISE":
            summarise_fn = rule.get("summarise_fn")
            if summarise_fn not in {"count_keys", "key_names_only", "receipt_reference"}:
                raise ValueError(f"{path}.rules[{index}].summarise_fn is not supported")
    return policy


class ChangelogRedactor:
    def __init__(self, policy: dict[str, Any] | None = None) -> None:
        self.policy = validate_redaction_policy(policy or load_redaction_policy())
        self.rules = [RedactionRule(**rule) for rule in self.policy["rules"]]
        self.mask_fns = {
            "identity_prefix": mask_identity_prefix,
            "host_labels": mask_host_labels,
            "target_labels": mask_target_labels,
            "redact_inline_text": redact_inline_text,
        }
        self.summarise_fns = {
            "count_keys": count_keys,
            "key_names_only": key_names_only,
            "receipt_reference": receipt_reference,
        }

    def redact_entries(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.redact_entry(entry) for entry in entries]

    def redact_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        redacted = self._redact_value(entry, "")
        if not isinstance(redacted, dict):
            raise ValueError("redacted changelog entry must remain a mapping")
        return redacted

    def _redact_value(self, value: Any, path: str) -> Any:
        rule = self._rule_for_path(path)
        if rule is not None:
            if rule.level == "STRIP":
                return STRIP_PLACEHOLDER
            if rule.level == "SUMMARISE":
                return self.summarise_fns[rule.summarise_fn](value)
            if rule.level == "MASK":
                value = self.mask_fns[rule.mask_fn](value)

        if isinstance(value, dict):
            return {
                key: self._redact_value(item, f"{path}.{key}" if path else key)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact_value(item, f"{path}.*" if path else "*") for item in value]
        if isinstance(value, str):
            return redact_inline_text(value)
        return value

    def _rule_for_path(self, path: str) -> RedactionRule | None:
        if not path:
            return None
        for rule in self.rules:
            if _pattern_matches(rule.field_pattern, path):
                return rule
        return None


def redact_history_entries(
    entries: list[dict[str, Any]],
    *,
    policy: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return ChangelogRedactor(policy).redact_entries(entries)
