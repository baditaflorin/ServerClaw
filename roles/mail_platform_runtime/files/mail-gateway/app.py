import json
import os
import smtplib
import ssl
from copy import deepcopy
from email.message import EmailMessage
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


STATE_FILE = Path(os.getenv("STATE_FILE", "/data/state.json"))
BREVO_API_KEY = os.environ["BREVO_API_KEY"]
BREVO_API_URL = os.getenv("BREVO_API_URL", "https://api.brevo.com/v3/smtp/email")
DEFAULT_FROM_EMAIL = os.environ["DEFAULT_FROM_EMAIL"]
DEFAULT_FROM_NAME = os.getenv("DEFAULT_FROM_NAME", "LV3 Mail Gateway")
DEFAULT_REPLY_TO_EMAIL = os.getenv("DEFAULT_REPLY_TO_EMAIL")
GATEWAY_API_KEY = os.environ["GATEWAY_API_KEY"]
LOCAL_SMTP_HOST = os.getenv("LOCAL_SMTP_HOST", "stalwart")
LOCAL_SMTP_PORT = int(os.getenv("LOCAL_SMTP_PORT", "587"))
LOCAL_SMTP_USERNAME = os.getenv("LOCAL_SMTP_USERNAME")
LOCAL_SMTP_PASSWORD = os.getenv("LOCAL_SMTP_PASSWORD")
STALWART_API_URL = os.getenv("STALWART_API_URL", "http://stalwart:8080")
STALWART_ADMIN_USER = os.getenv("STALWART_ADMIN_USER", "admin")
STALWART_ADMIN_PASSWORD = os.environ["STALWART_ADMIN_PASSWORD"]
ATTEMPT_LOCAL_FIRST = env_bool("ATTEMPT_LOCAL_FIRST", False)
FORCE_BREVO_FALLBACK = env_bool("FORCE_BREVO_FALLBACK", True)

DEFAULT_STATE = {
    "webhook_events_total": 0,
    "event_counters": {},
    "send_counters": {
        "requests_total": 0,
        "local_smtp_success_total": 0,
        "local_smtp_failure_total": 0,
        "brevo_success_total": 0,
        "brevo_failure_total": 0,
        "fallback_total": 0,
    },
}


class SendRequest(BaseModel):
    to: list[str] = Field(min_length=1)
    subject: str
    text: str | None = None
    html: str | None = None
    from_email: str | None = None
    from_name: str | None = None
    reply_to: str | None = None
    force_fallback: bool = False


class DomainUpsertRequest(BaseModel):
    description: str | None = None


class MailboxUpsertRequest(BaseModel):
    password: str | None = None
    description: str | None = None
    emails: list[str] | None = None


app = FastAPI()


def require_api_key(
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    if x_api_key == GATEWAY_API_KEY:
        return
    if authorization and authorization.startswith("Bearer "):
        if authorization.removeprefix("Bearer ").strip() == GATEWAY_API_KEY:
            return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def load_state() -> dict:
    if not STATE_FILE.exists():
        return deepcopy(DEFAULT_STATE)
    try:
        with STATE_FILE.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return deepcopy(DEFAULT_STATE)

    merged = deepcopy(DEFAULT_STATE)
    merged["webhook_events_total"] = int(state.get("webhook_events_total", 0))
    merged["event_counters"].update(state.get("event_counters", {}))
    merged["send_counters"].update(state.get("send_counters", {}))
    return merged


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=str(STATE_FILE.parent), delete=False) as handle:
        json.dump(state, handle, sort_keys=True)
        handle.write("\n")
        temp_name = handle.name
    os.replace(temp_name, STATE_FILE)


def increment_counter(container: dict, key: str, amount: int = 1) -> None:
    container[key] = int(container.get(key, 0)) + amount


async def stalwart_request(method: str, path: str, json_body: Any | None = None) -> Any:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.request(
            method,
            f"{STALWART_API_URL}{path}",
            auth=(STALWART_ADMIN_USER, STALWART_ADMIN_PASSWORD),
            headers={"Accept": "application/json"},
            json=json_body,
        )
        response.raise_for_status()
        return response.json()


async def list_principals(principal_type: str) -> list[dict[str, Any]]:
    payload = await stalwart_request("GET", f"/api/principal?types={principal_type}")
    return payload.get("data", {}).get("items", [])


async def get_principal_by_name(principal_type: str, name: str) -> dict[str, Any] | None:
    for item in await list_principals(principal_type):
        if item.get("name") == name:
            return item
    return None


async def fetch_principal(principal_id: int | str) -> dict[str, Any]:
    payload = await stalwart_request("GET", f"/api/principal/{principal_id}")
    return payload.get("data", {})


async def patch_principal(principal_id: int | str, operations: list[dict[str, Any]]) -> None:
    await stalwart_request("PATCH", f"/api/principal/{principal_id}", operations)


async def delete_principal(principal_id: int | str) -> None:
    await stalwart_request("DELETE", f"/api/principal/{principal_id}")


def principal_emails(principal: dict[str, Any]) -> list[str]:
    emails = principal.get("emails", [])
    if isinstance(emails, list):
        return [str(value) for value in emails]
    if isinstance(emails, str) and emails:
        return [emails]
    return []


def mailbox_payload(localpart: str, payload: MailboxUpsertRequest) -> dict[str, Any]:
    return {
        "type": "individual",
        "quota": 0,
        "name": localpart,
        "description": payload.description or "LV3 managed mailbox",
        "secrets": [payload.password] if payload.password else [],
        "emails": payload.emails if payload.emails is not None else [],
        "urls": [],
        "memberOf": [],
        "roles": ["user"],
        "lists": [],
        "members": [],
        "enabledPermissions": [],
        "disabledPermissions": [],
        "externalMembers": [],
    }


def send_via_local_smtp(payload: SendRequest) -> None:
    message = EmailMessage()
    sender_name = payload.from_name or DEFAULT_FROM_NAME
    sender_email = payload.from_email or DEFAULT_FROM_EMAIL
    message["From"] = f"{sender_name} <{sender_email}>"
    message["To"] = ", ".join(payload.to)
    message["Subject"] = payload.subject
    if payload.reply_to or DEFAULT_REPLY_TO_EMAIL:
        message["Reply-To"] = payload.reply_to or DEFAULT_REPLY_TO_EMAIL
    if payload.html:
        message.set_content(payload.text or "HTML message available")
        message.add_alternative(payload.html, subtype="html")
    else:
        message.set_content(payload.text or "")

    context = ssl.create_default_context()
    with smtplib.SMTP(LOCAL_SMTP_HOST, LOCAL_SMTP_PORT, timeout=20) as client:
        client.starttls(context=context)
        if LOCAL_SMTP_USERNAME and LOCAL_SMTP_PASSWORD:
            client.login(LOCAL_SMTP_USERNAME, LOCAL_SMTP_PASSWORD)
        client.send_message(message)


async def send_via_brevo(payload: SendRequest) -> dict:
    sender = {
        "name": payload.from_name or DEFAULT_FROM_NAME,
        "email": payload.from_email or DEFAULT_FROM_EMAIL,
    }
    body = {
        "sender": sender,
        "to": [{"email": address} for address in payload.to],
        "subject": payload.subject,
    }
    if payload.text:
        body["textContent"] = payload.text
    if payload.html:
        body["htmlContent"] = payload.html
    if payload.reply_to or DEFAULT_REPLY_TO_EMAIL:
        body["replyTo"] = {"email": payload.reply_to or DEFAULT_REPLY_TO_EMAIL}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            BREVO_API_URL,
            headers={
                "accept": "application/json",
                "api-key": BREVO_API_KEY,
                "content-type": "application/json",
            },
            json=body,
        )
        response.raise_for_status()
        return response.json()


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/state")
def state(_: None = Depends(require_api_key)):
    return load_state()


@app.get("/v1/domains")
async def list_domains(_: None = Depends(require_api_key)):
    return {"items": await list_principals("domain")}


@app.put("/v1/domains/{domain_name}")
async def upsert_domain(domain_name: str, payload: DomainUpsertRequest, _: None = Depends(require_api_key)):
    existing = await get_principal_by_name("domain", domain_name)
    if existing is None:
        result = await stalwart_request(
            "POST",
            "/api/principal",
            {
                "type": "domain",
                "quota": 0,
                "name": domain_name,
                "description": payload.description or "Managed mail domain",
                "secrets": [],
                "emails": [],
                "urls": [],
                "memberOf": [],
                "roles": [],
                "lists": [],
                "members": [],
                "enabledPermissions": [],
                "disabledPermissions": [],
                "externalMembers": [],
            },
        )
        principal_id = result.get("data")
        return {"status": "created", "item": await fetch_principal(principal_id)}

    operations: list[dict[str, Any]] = []
    desired_description = payload.description or existing.get("description") or "Managed mail domain"
    if existing.get("description") != desired_description:
        operations.append({"action": "set", "field": "description", "value": desired_description})
    if operations:
        await patch_principal(existing["id"], operations)
        return {"status": "updated", "item": await fetch_principal(existing["id"])}
    return {"status": "unchanged", "item": await fetch_principal(existing["id"])}


@app.delete("/v1/domains/{domain_name}", status_code=204)
async def remove_domain(domain_name: str, _: None = Depends(require_api_key)):
    existing = await get_principal_by_name("domain", domain_name)
    if existing is not None:
        await delete_principal(existing["id"])
    return Response(status_code=204)


@app.get("/v1/mailboxes")
async def list_mailboxes(_: None = Depends(require_api_key)):
    return {"items": await list_principals("individual")}


@app.put("/v1/mailboxes/{localpart}")
async def upsert_mailbox(localpart: str, payload: MailboxUpsertRequest, _: None = Depends(require_api_key)):
    existing = await get_principal_by_name("individual", localpart)
    desired_emails = payload.emails if payload.emails is not None else principal_emails(existing or {})
    if existing is None:
        if not desired_emails:
            raise HTTPException(status_code=422, detail="At least one mailbox email is required")
        if not payload.password:
            raise HTTPException(status_code=422, detail="A password is required when creating a mailbox")
        result = await stalwart_request("POST", "/api/principal", mailbox_payload(localpart, payload))
        principal_id = result.get("data")
        return {"status": "created", "item": await fetch_principal(principal_id)}

    operations: list[dict[str, Any]] = []
    desired_description = payload.description or existing.get("description") or "LV3 managed mailbox"
    if existing.get("description") != desired_description:
        operations.append({"action": "set", "field": "description", "value": desired_description})

    current_emails = principal_emails(existing)
    for email in desired_emails:
        if email not in current_emails:
            operations.append({"action": "addItem", "field": "emails", "value": email})
    for email in current_emails:
        if email not in desired_emails:
            operations.append({"action": "removeItem", "field": "emails", "value": email})
    if payload.password:
        operations.append({"action": "set", "field": "secrets", "value": [payload.password]})

    if operations:
        await patch_principal(existing["id"], operations)
        return {"status": "updated", "item": await fetch_principal(existing["id"])}
    return {"status": "unchanged", "item": await fetch_principal(existing["id"])}


@app.delete("/v1/mailboxes/{localpart}", status_code=204)
async def remove_mailbox(localpart: str, _: None = Depends(require_api_key)):
    existing = await get_principal_by_name("individual", localpart)
    if existing is not None:
        await delete_principal(existing["id"])
    return Response(status_code=204)


@app.post("/webhooks/stalwart", status_code=204)
async def stalwart_webhook(request: Request):
    payload = await request.json()
    state = load_state()
    events = payload.get("events", [])
    for event in events:
        event_type = str(event.get("type", "unknown"))
        state["webhook_events_total"] += 1
        increment_counter(state["event_counters"], event_type)
    save_state(state)
    return None


@app.post("/send")
async def send_mail(payload: SendRequest, _: None = Depends(require_api_key)):
    state = load_state()
    increment_counter(state["send_counters"], "requests_total")

    local_allowed = ATTEMPT_LOCAL_FIRST and not FORCE_BREVO_FALLBACK and not payload.force_fallback
    if local_allowed:
        try:
            send_via_local_smtp(payload)
            increment_counter(state["send_counters"], "local_smtp_success_total")
            save_state(state)
            return {"status": "accepted", "channel": "local_smtp"}
        except Exception as exc:  # pragma: no cover - exercised live
            increment_counter(state["send_counters"], "local_smtp_failure_total")
            increment_counter(state["send_counters"], "fallback_total")
            save_state(state)
            local_error = str(exc)
    else:
        local_error = None

    try:
        result = await send_via_brevo(payload)
        increment_counter(state["send_counters"], "brevo_success_total")
        save_state(state)
        response = {"status": "accepted", "channel": "brevo_api", "result": result}
        if local_error:
            response["local_error"] = local_error
        return response
    except httpx.HTTPError as exc:
        increment_counter(state["send_counters"], "brevo_failure_total")
        save_state(state)
        raise HTTPException(status_code=502, detail=f"Brevo API request failed: {exc}") from exc
