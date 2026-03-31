#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any


SMOKE_TOKEN = "smoke"
DEFAULT_SUITE_ID = "default-primary-smoke"
DEFAULT_SUITE_NAME = "Default primary smoke"


def normalize_text(value: str) -> str:
    collapsed = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return " ".join(collapsed.split())


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def verification_entries(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    verification = receipt.get("verification")
    if not isinstance(verification, list):
        return []
    return [item for item in verification if isinstance(item, dict)]


def verification_passed(item: dict[str, Any]) -> bool:
    return normalize_text(str(item.get("result", ""))) == "pass"


def passed_verification_text(receipt: dict[str, Any]) -> list[str]:
    return [
        normalize_text(" ".join(str(item.get(field, "")) for field in ("check", "observed")))
        for item in verification_entries(receipt)
        if verification_passed(item)
    ]


def receipt_passed(receipt: dict[str, Any]) -> bool:
    entries = verification_entries(receipt)
    if not entries:
        return False
    return all(verification_passed(item) for item in entries)


def latest_receipt(receipts: list[dict[str, Any]]) -> dict[str, Any] | None:
    ordered = sorted(
        receipts,
        key=lambda item: parse_timestamp(
            str(item.get("recorded_at") or item.get("recorded_on") or item.get("applied_on") or "")
        )
        or datetime(1970, 1, 1, tzinfo=UTC),
        reverse=True,
    )
    return ordered[0] if ordered else None


def default_smoke_suite(service: dict[str, Any], environment: str) -> dict[str, Any]:
    service_name = str(service.get("name") or service.get("id") or "service").strip() or "service"
    return {
        "id": DEFAULT_SUITE_ID,
        "name": DEFAULT_SUITE_NAME,
        "description": (
            f"Require at least one passing smoke-labelled verification item for the primary "
            f"{environment} path of {service_name}."
        ),
        "required_verification_checks": [SMOKE_TOKEN],
    }


def active_environment_binding(service: dict[str, Any], environment: str) -> dict[str, Any] | None:
    environments = service.get("environments")
    if not isinstance(environments, dict):
        return None
    binding = environments.get(environment)
    if not isinstance(binding, dict):
        return None
    if normalize_text(str(binding.get("status", ""))) != "active":
        return None
    return binding


def declared_smoke_suites(service: dict[str, Any], environment: str) -> list[dict[str, Any]]:
    binding = active_environment_binding(service, environment)
    if binding is None:
        return []
    raw_suites = binding.get("smoke_suites")
    if not isinstance(raw_suites, list):
        return [default_smoke_suite(service, environment)]
    suites = [suite for suite in raw_suites if isinstance(suite, dict)]
    return suites or [default_smoke_suite(service, environment)]


def receipt_matches_suite(receipt: dict[str, Any], suite: dict[str, Any]) -> bool:
    verification_tokens = [
        normalize_text(str(token))
        for token in suite.get("required_verification_checks", [])
        if isinstance(token, str) and token.strip()
    ]
    receipt_keywords = [
        normalize_text(str(token))
        for token in suite.get("required_receipt_keywords", [])
        if isinstance(token, str) and token.strip()
    ]
    if not verification_tokens and not receipt_keywords:
        verification_tokens = [SMOKE_TOKEN]

    passed_texts = passed_verification_text(receipt)
    if verification_tokens:
        for token in verification_tokens:
            if not any(token in text for text in passed_texts):
                return False

    if receipt_keywords:
        flattened = normalize_text(json.dumps(receipt, sort_keys=True))
        for token in receipt_keywords:
            if token not in flattened:
                return False

    return True


def matched_smoke_suite_ids(receipt: dict[str, Any], suites: list[dict[str, Any]]) -> list[str]:
    matched: list[str] = []
    for index, suite in enumerate(suites):
        suite_id = str(suite.get("id") or f"suite-{index + 1}").strip() or f"suite-{index + 1}"
        if receipt_matches_suite(receipt, suite):
            matched.append(suite_id)
    return matched


def latest_matching_smoke_receipt(
    receipts: list[dict[str, Any]],
    suites: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[str]]:
    ordered = sorted(
        receipts,
        key=lambda item: parse_timestamp(
            str(item.get("recorded_at") or item.get("recorded_on") or item.get("applied_on") or "")
        )
        or datetime(1970, 1, 1, tzinfo=UTC),
        reverse=True,
    )
    for receipt in ordered:
        matched = matched_smoke_suite_ids(receipt, suites)
        if matched:
            return receipt, matched
    return None, []
