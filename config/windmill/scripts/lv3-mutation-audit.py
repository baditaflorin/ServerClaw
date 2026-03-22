import datetime as dt
import json
import os
import re
import urllib.request


ALLOWED_ACTOR_CLASSES = {"operator", "agent", "service", "automation"}
ALLOWED_OUTCOMES = {"success", "failure", "rejected"}
ACTION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _require_string(value, field, allow_empty=False):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    if not allow_empty and not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _require_choice(value, field, allowed):
    value = _require_string(value, field)
    if value not in allowed:
        raise ValueError(f"{field} must be one of {sorted(allowed)}")
    return value


def _utc_now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_correlation_id(action):
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"windmill:{action}:{timestamp}"


def _build_event(
    *,
    actor_class,
    actor_id,
    action,
    target,
    outcome,
    correlation_id=None,
    evidence_ref="",
):
    actor_class = _require_choice(actor_class, "actor_class", ALLOWED_ACTOR_CLASSES)
    actor_id = _require_string(actor_id, "actor_id")
    action = _require_string(action, "action")
    if not ACTION_PATTERN.match(action):
        raise ValueError("action must use lowercase identifier format")
    target = _require_string(target, "target")
    outcome = _require_choice(outcome, "outcome", ALLOWED_OUTCOMES)
    correlation_id = _require_string(correlation_id or _default_correlation_id(action), "correlation_id")
    evidence_ref = _require_string(evidence_ref, "evidence_ref", allow_empty=True)

    return {
        "ts": _utc_now_iso(),
        "actor": {"class": actor_class, "id": actor_id},
        "surface": "windmill",
        "action": action,
        "target": target,
        "outcome": outcome,
        "correlation_id": correlation_id,
        "evidence_ref": evidence_ref,
    }


def _append_jsonl(path, payload):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _post_webhook(url, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        if response.status >= 300:
            raise RuntimeError(f"mutation audit webhook failed with HTTP {response.status}")


def main(
    actor_class="automation",
    actor_id="windmill-job",
    action="run.windmill_job",
    target="windmill-workspace",
    outcome="success",
    correlation_id="",
    evidence_ref="",
):
    event = _build_event(
        actor_class=actor_class,
        actor_id=actor_id,
        action=action,
        target=target,
        outcome=outcome,
        correlation_id=correlation_id or None,
        evidence_ref=evidence_ref,
    )

    sink_path = os.getenv("LV3_MUTATION_AUDIT_FILE", "").strip()
    if sink_path:
        _append_jsonl(sink_path, event)

    webhook_url = os.getenv("LV3_MUTATION_AUDIT_WEBHOOK", "").strip()
    if webhook_url:
        _post_webhook(webhook_url, event)

    return event
