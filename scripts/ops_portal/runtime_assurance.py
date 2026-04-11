from __future__ import annotations

from datetime import datetime, UTC
from typing import Any
from urllib.parse import urlparse

from stage_smoke import declared_smoke_suites, latest_matching_smoke_receipt, receipt_passed as smoke_receipt_passed


UTC = UTC


DEFAULT_OWNER_TEAM = "lv3-platform"
RECEIPT_FRESHNESS_DAYS = 30
HTTP_SCHEMES = {"http", "https"}
PROTECTED_ACCESS_MODELS = {"platform-sso", "upstream-auth"}
LOG_REQUIRED_CATEGORIES = {"access", "automation", "communication", "data", "observability", "security"}
AUTH_KEYWORDS = (
    "auth",
    "browser",
    "callback",
    "login",
    "logout",
    "oauth",
    "oidc",
    "playwright",
    "sign in",
    "sign-in",
)
TLS_KEYWORDS = (
    "blackbox",
    "cert",
    "certificate",
    "https",
    "ssl",
    "testssl",
    "tls",
)
LOG_KEYWORDS = (
    "canary",
    "dozzle",
    "log ingestion",
    "log-path",
    "log query",
    "loki",
    "queryability",
)


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


def humanize_timestamp(value: str | None) -> str:
    parsed = parse_timestamp(value)
    if parsed is None:
        return "Not recorded"
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def tone_for_state(state: str) -> str:
    normalized = state.strip().lower()
    if normalized in {"healthy", "ok", "pass"}:
        return "ok"
    if normalized in {"degraded", "maintenance"}:
        return "warn"
    if normalized in {"critical", "failed"}:
        return "danger"
    return "neutral"


def _active_environments(service: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    environments = service.get("environments")
    if not isinstance(environments, dict):
        return [
            ("production", {"status": "active", "url": service.get("public_url") or service.get("internal_url") or ""})
        ]
    result: list[tuple[str, dict[str, Any]]] = []
    for environment, binding in environments.items():
        if not isinstance(binding, dict):
            continue
        if str(binding.get("status", "planned")).strip().lower() != "active":
            continue
        result.append((str(environment), binding))
    return result


def _http_url_for_environment(service: dict[str, Any], environment_binding: dict[str, Any]) -> str | None:
    candidates = [
        environment_binding.get("url"),
        service.get("public_url"),
        service.get("internal_url"),
    ]
    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        parsed = urlparse(candidate)
        if parsed.scheme in HTTP_SCHEMES:
            return candidate
    return None


def _host_from_url(url: str | None) -> str | None:
    if not isinstance(url, str) or not url.strip():
        return None
    return urlparse(url).hostname


def _health_entry_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    services = payload.get("services") if isinstance(payload, dict) else None
    if not isinstance(services, list):
        return {}
    return {str(item.get("service_id")): item for item in services if isinstance(item, dict) and item.get("service_id")}


def _signal_map(entry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    signals = entry.get("signals") if isinstance(entry, dict) else None
    if not isinstance(signals, list):
        return {}
    return {str(item.get("name")): item for item in signals if isinstance(item, dict) and item.get("name")}


def _has_positive_health(entry: dict[str, Any] | None) -> bool:
    if not isinstance(entry, dict):
        return False
    composite_status = str(entry.get("composite_status") or entry.get("status") or "").strip().lower()
    return composite_status in {"healthy", "degraded", "maintenance"}


def _receipt_environment(receipt: dict[str, Any]) -> str:
    environment = receipt.get("_environment") or receipt.get("environment") or "production"
    return str(environment).strip().lower() or "production"


def _matched_receipts(
    receipts: list[dict[str, Any]],
    service_id: str,
    *,
    environment: str,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for receipt in receipts:
        matched_services = receipt.get("_matched_services")
        if not isinstance(matched_services, list) or service_id not in matched_services:
            continue
        if _receipt_environment(receipt) != environment:
            continue
        matches.append(receipt)
    return matches


def _receipt_passed(receipt: dict[str, Any]) -> bool:
    verification = receipt.get("verification")
    if not isinstance(verification, list):
        return True
    return all(
        str(item.get("result", "pass")).strip().lower() == "pass" for item in verification if isinstance(item, dict)
    )


def _latest_receipt(receipts: list[dict[str, Any]]) -> dict[str, Any] | None:
    ordered = sorted(
        receipts,
        key=lambda item: (
            parse_timestamp(str(item.get("recorded_at") or item.get("recorded_on") or item.get("applied_on") or ""))
            or datetime(1970, 1, 1, tzinfo=UTC)
        ),
        reverse=True,
    )
    return ordered[0] if ordered else None


def _latest_keyword_receipt(receipts: list[dict[str, Any]], keywords: tuple[str, ...]) -> dict[str, Any] | None:
    for receipt in sorted(
        receipts,
        key=lambda item: (
            parse_timestamp(str(item.get("recorded_at") or item.get("recorded_on") or item.get("applied_on") or ""))
            or datetime(1970, 1, 1, tzinfo=UTC)
        ),
        reverse=True,
    ):
        text = str(receipt.get("_normalized_text", ""))
        if any(keyword in text for keyword in keywords):
            return receipt
    return None


def _dimension(
    *,
    dimension_id: str,
    label: str,
    state: str,
    detail: str,
    last_verified: str | None,
    next_action: str,
    required: bool,
) -> dict[str, Any]:
    normalized_state = state if required else "n/a"
    return {
        "id": dimension_id,
        "label": label,
        "required": required,
        "state": normalized_state,
        "detail": detail,
        "last_verified": last_verified,
        "last_verified_label": humanize_timestamp(last_verified),
        "next_action": next_action,
        "tone": tone_for_state(normalized_state),
    }


def _overall_state(dimensions: list[dict[str, Any]]) -> str:
    required_states = [dimension["state"] for dimension in dimensions if dimension.get("required")]
    if not required_states:
        return "unknown"
    if any(state == "failed" for state in required_states):
        return "failed"
    if any(state == "degraded" for state in required_states):
        return "degraded"
    if any(state == "unknown" for state in required_states):
        return "unknown"
    return "pass"


def _overall_detail(dimensions: list[dict[str, Any]]) -> str:
    required = [dimension for dimension in dimensions if dimension.get("required")]
    passing = sum(1 for dimension in required if dimension["state"] == "pass")
    return f"{passing}/{len(required)} required dimensions are currently green"


def _next_action(dimensions: list[dict[str, Any]]) -> tuple[str, str]:
    priority = {"failed": 0, "degraded": 1, "unknown": 2}
    ordered_dimensions = sorted(
        (dimension for dimension in dimensions if dimension.get("required") and dimension["state"] != "pass"),
        key=lambda dimension: (priority.get(str(dimension["state"]), 99), dimension["label"]),
    )
    if not ordered_dimensions:
        return "Maintain the current verification cadence.", "All required dimensions are currently green."
    selected = ordered_dimensions[0]
    return selected["next_action"], selected["label"]


def _latest_verified_timestamp(dimensions: list[dict[str, Any]]) -> str | None:
    timestamps = [
        parse_timestamp(dimension.get("last_verified")) for dimension in dimensions if dimension.get("required")
    ]
    filtered = [value for value in timestamps if value is not None]
    if not filtered:
        return None
    latest = max(filtered)
    return latest.isoformat().replace("+00:00", "Z")


def build_runtime_assurance_models(
    services: list[dict[str, Any]],
    publications: list[dict[str, Any]],
    health_payload: dict[str, Any],
    receipts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    publications_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for publication in publications:
        if not isinstance(publication, dict):
            continue
        service_id = publication.get("service_id")
        environment = publication.get("environment") or "production"
        if not isinstance(service_id, str):
            continue
        publications_by_key.setdefault((service_id, str(environment)), []).append(publication)

    health_map = _health_entry_map(health_payload)
    rows: list[dict[str, Any]] = []

    for service in services:
        if str(service.get("lifecycle_status", "active")).strip().lower() != "active":
            continue
        service_id = str(service.get("id", "")).strip()
        if not service_id:
            continue
        for environment, binding in _active_environments(service):
            publications_for_env = publications_by_key.get((service_id, environment), [])
            health_entry = health_map.get(service_id) if environment == "production" else None
            health_entry_data = health_entry if isinstance(health_entry, dict) else {}
            signal_map = _signal_map(health_entry_data)
            matched_receipts = _matched_receipts(receipts, service_id, environment=environment)
            latest_receipt = _latest_receipt(matched_receipts)
            auth_receipt = _latest_keyword_receipt(matched_receipts, AUTH_KEYWORDS)
            tls_receipt = _latest_keyword_receipt(matched_receipts, TLS_KEYWORDS)
            log_receipt = _latest_keyword_receipt(matched_receipts, LOG_KEYWORDS)
            smoke_suites = declared_smoke_suites(service, environment)
            smoke_receipt, matched_smoke_suite_ids = latest_matching_smoke_receipt(matched_receipts, smoke_suites)

            http_url = _http_url_for_environment(service, binding)
            expected_host = str(binding.get("subdomain") or service.get("subdomain") or _host_from_url(http_url) or "")
            has_http_surface = bool(http_url)
            access_model = next(
                (
                    str(item.get("publication", {}).get("access_model", "")).strip()
                    for item in publications_for_env
                    if isinstance(item.get("publication"), dict)
                ),
                "private-network" if str(service.get("exposure")) == "private-only" else "open",
            )
            requires_auth = has_http_surface and access_model in PROTECTED_ACCESS_MODELS
            requires_tls = bool(http_url and urlparse(http_url).scheme == "https") or any(
                isinstance(item.get("adapter"), dict) and isinstance(item["adapter"].get("tls"), dict)
                for item in publications_for_env
            )
            requires_route = has_http_surface or bool(publications_for_env)
            requires_logs = has_http_surface or str(service.get("category", "")) in LOG_REQUIRED_CATEGORIES

            health_probe = signal_map.get("health_probe", {})
            health_reason = str(
                health_entry_data.get("reason") or health_probe.get("reason") or "No current health-composite reason."
            )
            health_computed_at = str(health_entry_data.get("computed_at") or "")

            if health_entry is None:
                existence = _dimension(
                    dimension_id="existence",
                    label="Existence",
                    state="unknown",
                    detail="No current runtime witness is available for this service and environment.",
                    last_verified=str(latest_receipt.get("recorded_on") or latest_receipt.get("applied_on") or "")
                    if latest_receipt
                    else None,
                    next_action="Converge the service or refresh the live health witness before trusting the declared runtime.",
                    required=True,
                )
            else:
                probe_value = str(health_probe.get("value", "unknown")).strip().lower()
                if probe_value in {"healthy", "ok", "degraded"}:
                    existence = _dimension(
                        dimension_id="existence",
                        label="Existence",
                        state="pass",
                        detail="The current health probe still witnesses the declared runtime endpoint.",
                        last_verified=health_computed_at or None,
                        next_action="No immediate action.",
                        required=True,
                    )
                elif probe_value in {"down", "failed", "error", "unhealthy", "unreachable"}:
                    existence = _dimension(
                        dimension_id="existence",
                        label="Existence",
                        state="failed",
                        detail=health_reason,
                        last_verified=health_computed_at or None,
                        next_action="Inspect the current runtime witness and recover the declared listener before trusting this service.",
                        required=True,
                    )
                else:
                    existence = _dimension(
                        dimension_id="existence",
                        label="Existence",
                        state="unknown",
                        detail="A health entry exists, but it does not currently provide a clear runtime witness result.",
                        last_verified=health_computed_at or None,
                        next_action="Refresh the live witness path so the declared runtime can be proven explicitly.",
                        required=True,
                    )

            if health_entry is None:
                runtime_health = _dimension(
                    dimension_id="runtime_health",
                    label="Runtime",
                    state="unknown",
                    detail="No current health-composite rollup is available for this environment.",
                    last_verified=None,
                    next_action="Refresh the service health composite before treating this service as safe to trust.",
                    required=True,
                )
            else:
                composite_status = (
                    str(health_entry_data.get("composite_status") or health_entry_data.get("status") or "unknown")
                    .strip()
                    .lower()
                )
                if composite_status == "healthy":
                    runtime_health = _dimension(
                        dimension_id="runtime_health",
                        label="Runtime",
                        state="pass",
                        detail=health_reason,
                        last_verified=health_computed_at or None,
                        next_action="No immediate action.",
                        required=True,
                    )
                elif composite_status in {"degraded", "maintenance"}:
                    runtime_health = _dimension(
                        dimension_id="runtime_health",
                        label="Runtime",
                        state="degraded",
                        detail=health_reason,
                        last_verified=health_computed_at or None,
                        next_action="Inspect the health composite and service runbook before relying on this surface.",
                        required=True,
                    )
                elif composite_status == "critical":
                    runtime_health = _dimension(
                        dimension_id="runtime_health",
                        label="Runtime",
                        state="failed",
                        detail=health_reason,
                        last_verified=health_computed_at or None,
                        next_action="Treat the service as unhealthy and recover it through the documented runbook before use.",
                        required=True,
                    )
                else:
                    runtime_health = _dimension(
                        dimension_id="runtime_health",
                        label="Runtime",
                        state="unknown",
                        detail="The health composite does not currently classify this service.",
                        last_verified=health_computed_at or None,
                        next_action="Refresh or repair the health-composite pipeline for this service.",
                        required=True,
                    )

            if not requires_route:
                route_truth = _dimension(
                    dimension_id="route_truth",
                    label="Route",
                    state="n/a",
                    detail="No HTTP or HTTPS publication is declared for this service and environment.",
                    last_verified=None,
                    next_action="No route assertion is required for this surface.",
                    required=False,
                )
            else:
                active_publications = [
                    item
                    for item in publications_for_env
                    if str(item.get("status", "active")).strip().lower() == "active"
                ]
                route_mismatch = any(
                    isinstance(item.get("adapter"), dict)
                    and item["adapter"].get("repo_route_service_id") not in {None, service_id}
                    for item in active_publications
                )
                publication_host_match = not active_publications or any(
                    str(item.get("fqdn", "")).strip() == expected_host for item in active_publications if expected_host
                )
                if route_mismatch or not publication_host_match:
                    route_truth = _dimension(
                        dimension_id="route_truth",
                        label="Route",
                        state="failed",
                        detail="The declared publication metadata does not currently align with the service-environment route identity.",
                        last_verified=None,
                        next_action="Fix the publication registry or edge target so the hostname resolves to the declared service identity.",
                        required=True,
                    )
                elif _has_positive_health(health_entry):
                    route_truth = _dimension(
                        dimension_id="route_truth",
                        label="Route",
                        state="pass",
                        detail="The declared route is present and the current runtime witness still resolves successfully.",
                        last_verified=health_computed_at or None,
                        next_action="No immediate action.",
                        required=True,
                    )
                elif latest_receipt is not None and _receipt_passed(latest_receipt):
                    route_truth = _dimension(
                        dimension_id="route_truth",
                        label="Route",
                        state="degraded",
                        detail="The last live apply proved the route, but the current runtime witness is unavailable or indirect.",
                        last_verified=str(latest_receipt.get("recorded_on") or latest_receipt.get("applied_on") or ""),
                        next_action="Replay route verification from the live environment before trusting this publication.",
                        required=True,
                    )
                else:
                    route_truth = _dimension(
                        dimension_id="route_truth",
                        label="Route",
                        state="unknown",
                        detail="A route is declared, but no current route assertion evidence is matched for this environment.",
                        last_verified=None,
                        next_action="Run or add route assertion verification for the declared hostname and audience.",
                        required=True,
                    )

            if not requires_auth:
                auth_journey = _dimension(
                    dimension_id="auth_journey",
                    label="Auth",
                    state="n/a",
                    detail="This surface does not currently require a protected browser journey assertion.",
                    last_verified=None,
                    next_action="No browser-journey verification is required here.",
                    required=False,
                )
            elif auth_receipt is not None and _receipt_passed(auth_receipt):
                auth_journey = _dimension(
                    dimension_id="auth_journey",
                    label="Auth",
                    state="pass",
                    detail="A matched live receipt records browser or auth-path proof for this protected surface.",
                    last_verified=str(auth_receipt.get("recorded_on") or auth_receipt.get("applied_on") or ""),
                    next_action="No immediate action.",
                    required=True,
                )
            elif _has_positive_health(health_entry):
                auth_journey = _dimension(
                    dimension_id="auth_journey",
                    label="Auth",
                    state="degraded",
                    detail="The protected surface is reachable, but no dedicated login or logout proof is matched yet.",
                    last_verified=health_computed_at or None,
                    next_action="Add or replay browser login and logout verification before treating this surface as fully trusted.",
                    required=True,
                )
            else:
                auth_journey = _dimension(
                    dimension_id="auth_journey",
                    label="Auth",
                    state="unknown",
                    detail="No dedicated authentication-journey evidence is currently matched for this protected surface.",
                    last_verified=None,
                    next_action="Implement or replay browser auth verification so login and logout truth is explicit.",
                    required=True,
                )

            if not requires_tls:
                tls_posture = _dimension(
                    dimension_id="tls_posture",
                    label="TLS",
                    state="n/a",
                    detail="No HTTPS-bearing surface is declared for this service and environment.",
                    last_verified=None,
                    next_action="No TLS posture assertion is required here.",
                    required=False,
                )
            elif tls_receipt is not None and _receipt_passed(tls_receipt):
                tls_posture = _dimension(
                    dimension_id="tls_posture",
                    label="TLS",
                    state="pass",
                    detail="A matched receipt records dedicated HTTPS or TLS verification for this surface.",
                    last_verified=str(tls_receipt.get("recorded_on") or tls_receipt.get("applied_on") or ""),
                    next_action="No immediate action.",
                    required=True,
                )
            elif _has_positive_health(health_entry):
                tls_posture = _dimension(
                    dimension_id="tls_posture",
                    label="TLS",
                    state="degraded",
                    detail="HTTPS is live, but no dedicated TLS posture receipt is matched for this surface yet.",
                    last_verified=health_computed_at or None,
                    next_action="Replay the dedicated TLS assurance path before relying on certificate posture as green.",
                    required=True,
                )
            else:
                tls_posture = _dimension(
                    dimension_id="tls_posture",
                    label="TLS",
                    state="unknown",
                    detail="No dedicated TLS posture evidence is currently matched for this HTTPS surface.",
                    last_verified=None,
                    next_action="Add or replay dedicated TLS verification for this hostname before trusting transport posture.",
                    required=True,
                )

            if not requires_logs:
                log_queryability = _dimension(
                    dimension_id="log_queryability",
                    label="Logs",
                    state="n/a",
                    detail="This surface is currently outside the central log-queryability requirement.",
                    last_verified=None,
                    next_action="No central log canary is required here.",
                    required=False,
                )
            elif log_receipt is not None and _receipt_passed(log_receipt):
                log_queryability = _dimension(
                    dimension_id="log_queryability",
                    label="Logs",
                    state="pass",
                    detail="A matched receipt records central log-path or log-queryability proof for this service.",
                    last_verified=str(log_receipt.get("recorded_on") or log_receipt.get("applied_on") or ""),
                    next_action="No immediate action.",
                    required=True,
                )
            else:
                log_queryability = _dimension(
                    dimension_id="log_queryability",
                    label="Logs",
                    state="unknown",
                    detail="No dedicated central log-ingestion or queryability evidence is currently matched for this service.",
                    last_verified=None,
                    next_action="Add or replay a central log canary before treating this service as fully observable.",
                    required=True,
                )

            if not smoke_suites:
                smoke = _dimension(
                    dimension_id="smoke",
                    label="Smoke",
                    state="failed",
                    detail="No stage-scoped smoke suite is declared for this active service environment.",
                    last_verified=None,
                    next_action="Declare at least one stage-scoped smoke suite before trusting this environment as stage-ready.",
                    required=True,
                )
            elif smoke_receipt is None:
                detail = (
                    "No successful stage-scoped smoke receipt is currently matched for this service."
                    if not matched_receipts
                    else "Receipts exist for this service, but none satisfy the declared smoke suite."
                )
                smoke = _dimension(
                    dimension_id="smoke",
                    label="Smoke",
                    state="unknown",
                    detail=detail,
                    last_verified=None,
                    next_action="Replay the service live apply or smoke path so the primary capability is proven explicitly.",
                    required=True,
                )
            elif not smoke_receipt_passed(smoke_receipt):
                recorded_on = str(
                    smoke_receipt.get("recorded_at")
                    or smoke_receipt.get("recorded_on")
                    or smoke_receipt.get("applied_on")
                    or ""
                )
                smoke = _dimension(
                    dimension_id="smoke",
                    label="Smoke",
                    state="failed",
                    detail=(
                        "The latest matched smoke receipt failed one or more required verification checks for "
                        + ", ".join(matched_smoke_suite_ids)
                        + "."
                    ),
                    last_verified=recorded_on or None,
                    next_action="Repair the service and replay the declared smoke suite before treating this environment as healthy.",
                    required=True,
                )
            else:
                recorded_on = str(
                    smoke_receipt.get("recorded_at")
                    or smoke_receipt.get("recorded_on")
                    or smoke_receipt.get("applied_on")
                    or ""
                )
                recorded_at = parse_timestamp(recorded_on)
                age_days = (
                    None
                    if recorded_at is None
                    else max(0, int((datetime.now(UTC) - recorded_at).total_seconds() // 86400))
                )
                if age_days is not None and age_days <= RECEIPT_FRESHNESS_DAYS:
                    smoke = _dimension(
                        dimension_id="smoke",
                        label="Smoke",
                        state="pass",
                        detail=(
                            "The latest matched smoke receipt satisfies the declared stage smoke suite: "
                            + ", ".join(matched_smoke_suite_ids)
                            + "."
                        ),
                        last_verified=recorded_on,
                        next_action="No immediate action.",
                        required=True,
                    )
                else:
                    smoke = _dimension(
                        dimension_id="smoke",
                        label="Smoke",
                        state="degraded",
                        detail=(
                            "A successful declared smoke receipt exists, but it is older than the preferred freshness window."
                        ),
                        last_verified=recorded_on,
                        next_action="Replay the stage smoke path to refresh user-meaningful proof for this service.",
                        required=True,
                    )

            dimensions = [
                existence,
                runtime_health,
                route_truth,
                auth_journey,
                tls_posture,
                log_queryability,
                smoke,
            ]
            overall_state = _overall_state(dimensions)
            next_action, next_action_dimension = _next_action(dimensions)
            row_url = http_url or str(
                binding.get("url") or service.get("public_url") or service.get("internal_url") or ""
            )

            rows.append(
                {
                    "service_id": service_id,
                    "service_name": service.get("name", service_id),
                    "environment": environment,
                    "owner_team": DEFAULT_OWNER_TEAM,
                    "vm": service.get("vm"),
                    "url": row_url,
                    "runbook": service.get("runbook"),
                    "adr": service.get("adr"),
                    "overall_state": overall_state,
                    "overall_tone": tone_for_state(overall_state),
                    "overall_detail": _overall_detail(dimensions),
                    "next_action": next_action,
                    "next_action_dimension": next_action_dimension,
                    "last_verified": _latest_verified_timestamp(dimensions),
                    "last_verified_label": humanize_timestamp(_latest_verified_timestamp(dimensions)),
                    "dimensions": dimensions,
                }
            )

    state_priority = {"failed": 0, "degraded": 1, "unknown": 2, "pass": 3}
    rows.sort(
        key=lambda row: (
            state_priority.get(str(row["overall_state"]), 99),
            str(row["service_name"]),
            str(row["environment"]),
        )
    )

    summary = {
        "row_count": len(rows),
        "pass_count": sum(1 for row in rows if row["overall_state"] == "pass"),
        "degraded_count": sum(1 for row in rows if row["overall_state"] == "degraded"),
        "failed_count": sum(1 for row in rows if row["overall_state"] == "failed"),
        "unknown_count": sum(1 for row in rows if row["overall_state"] == "unknown"),
    }
    summary["attention_count"] = summary["degraded_count"] + summary["failed_count"] + summary["unknown_count"]
    summary["portfolio_state"] = _overall_state(
        [
            {
                "state": "failed"
                if summary["failed_count"]
                else "degraded"
                if summary["degraded_count"]
                else "unknown"
                if summary["unknown_count"]
                else "pass",
                "required": True,
            }
        ]
        if rows
        else []
    )
    summary["portfolio_tone"] = tone_for_state(summary["portfolio_state"])
    return rows, summary
