"""Private authenticated SMTP compatibility bridge for transactional delivery.

The bridge deliberately accepts mail only from callers that know the managed
platform submission credentials.  It has no host-published port: callers reach
it through the mail-platform Docker network, and accepted messages are handed
to the same Brevo API path used by the mail gateway.
"""

from __future__ import annotations

import hmac
import json
import os
import signal
import threading
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import httpx
from aiosmtpd.controller import Controller


BREVO_API_KEY = os.environ["BREVO_API_KEY"]
BREVO_API_URL = os.getenv("BREVO_API_URL", "https://api.brevo.com/v3/smtp/email")
DEFAULT_FROM_EMAIL = os.environ["DEFAULT_FROM_EMAIL"]
DEFAULT_FROM_NAME = os.getenv("DEFAULT_FROM_NAME", "LV3 Mail Gateway")
DEFAULT_REPLY_TO_EMAIL = os.getenv("DEFAULT_REPLY_TO_EMAIL", "")
SMTP_BRIDGE_HOST = os.getenv("SMTP_BRIDGE_HOST", "0.0.0.0")
SMTP_BRIDGE_PORT = int(os.getenv("SMTP_BRIDGE_PORT", "1588"))
SMTP_BRIDGE_USERNAME = os.getenv("SMTP_BRIDGE_USERNAME") or os.environ["LOCAL_SMTP_USERNAME"]
SMTP_BRIDGE_PASSWORD = os.getenv("SMTP_BRIDGE_PASSWORD") or os.environ["LOCAL_SMTP_PASSWORD"]
SMTP_BRIDGE_MAX_MESSAGE_BYTES = int(os.getenv("SMTP_BRIDGE_MAX_MESSAGE_BYTES", str(1024 * 1024)))
SMTP_BRIDGE_MAX_RECIPIENTS = int(os.getenv("SMTP_BRIDGE_MAX_RECIPIENTS", "10"))
SMTP_BRIDGE_STATE_FILE = Path(os.getenv("SMTP_BRIDGE_STATE_FILE", "/data/smtp-bridge-state.json"))

DEFAULT_STATE = {
    "accepted_total": 0,
    "auth_failure_total": 0,
    "provider_failure_total": 0,
    "provider_success_total": 0,
    "rejected_total": 0,
}
STATE_LOCK = threading.Lock()


def load_state() -> dict[str, int]:
    try:
        loaded = json.loads(SMTP_BRIDGE_STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        loaded = {}
    return {key: int(loaded.get(key, value)) for key, value in DEFAULT_STATE.items()}


def increment_state(*keys: str) -> None:
    with STATE_LOCK:
        state = load_state()
        for key in keys:
            state[key] = int(state.get(key, 0)) + 1
        SMTP_BRIDGE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(SMTP_BRIDGE_STATE_FILE.parent),
            delete=False,
        ) as handle:
            json.dump(state, handle, sort_keys=True)
            handle.write("\n")
            temporary_name = handle.name
        os.replace(temporary_name, SMTP_BRIDGE_STATE_FILE)


def normalized_address(value: str | None) -> str:
    _, address = parseaddr(value or "")
    return address.strip().casefold()


def authenticate(_: str, login: bytes, password: bytes) -> bool:
    try:
        valid = hmac.compare_digest(login.decode("utf-8"), SMTP_BRIDGE_USERNAME) and hmac.compare_digest(
            password.decode("utf-8"), SMTP_BRIDGE_PASSWORD
        )
    except UnicodeDecodeError:
        valid = False
    if not valid:
        increment_state("auth_failure_total")
    return valid


def extract_message_parts(raw_message: bytes) -> tuple[str, str | None, str | None, str]:
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    sender = normalized_address(str(message.get("From", "")))
    expected_sender = normalized_address(DEFAULT_FROM_EMAIL)
    if not sender or not hmac.compare_digest(sender, expected_sender):
        raise ValueError("message sender is not permitted")

    subject = str(message.get("Subject", "")).strip()
    if not subject:
        raise ValueError("message subject is required")

    text: str | None = None
    html: str | None = None
    for part in message.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        content = part.get_content()
        if isinstance(content, bytes):
            content = content.decode(part.get_content_charset() or "utf-8", errors="replace")
        if content_type == "text/plain" and text is None:
            text = str(content)
        if content_type == "text/html" and html is None:
            html = str(content)

    if text is None and html is None:
        raise ValueError("message must include a text or HTML body")
    return expected_sender, text, html, subject


def validated_recipients(recipients: list[str]) -> list[str]:
    if not recipients or len(recipients) > SMTP_BRIDGE_MAX_RECIPIENTS:
        raise ValueError("recipient count is not permitted")
    normalized = [normalized_address(recipient) for recipient in recipients]
    if any(not recipient or "@" not in recipient for recipient in normalized):
        raise ValueError("recipient address is invalid")
    return list(dict.fromkeys(normalized))


async def submit_to_provider(*, recipients: list[str], subject: str, text: str | None, html: str | None) -> None:
    body: dict[str, Any] = {
        "sender": {"name": DEFAULT_FROM_NAME, "email": DEFAULT_FROM_EMAIL},
        "to": [{"email": recipient} for recipient in recipients],
        "subject": subject,
    }
    if text:
        body["textContent"] = text
    if html:
        body["htmlContent"] = html
    if DEFAULT_REPLY_TO_EMAIL:
        body["replyTo"] = {"email": DEFAULT_REPLY_TO_EMAIL}

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


class TransactionalSMTPHandler:
    async def handle_DATA(self, _server, _session, envelope) -> str:
        try:
            if normalized_address(envelope.mail_from) != normalized_address(DEFAULT_FROM_EMAIL):
                raise ValueError("envelope sender is not permitted")
            recipients = validated_recipients(list(envelope.rcpt_tos))
            _, text, html, subject = extract_message_parts(bytes(envelope.content or b""))
        except (TypeError, ValueError):
            increment_state("rejected_total")
            return "550 5.7.1 Message rejected by transactional sender policy"

        try:
            await submit_to_provider(recipients=recipients, subject=subject, text=text, html=html)
        except httpx.HTTPError:
            increment_state("provider_failure_total")
            return "451 4.3.0 Transactional delivery provider is temporarily unavailable"

        increment_state("accepted_total", "provider_success_total")
        return "250 2.0.0 Message accepted for transactional delivery"


def main() -> int:
    controller = Controller(
        TransactionalSMTPHandler(),
        hostname=SMTP_BRIDGE_HOST,
        port=SMTP_BRIDGE_PORT,
        data_size_limit=SMTP_BRIDGE_MAX_MESSAGE_BYTES,
        auth_required=True,
        auth_require_tls=False,
        auth_callback=authenticate,
    )
    stop_requested = threading.Event()

    def request_stop(_signum, _frame) -> None:
        stop_requested.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    controller.start()
    try:
        stop_requested.wait()
    finally:
        controller.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
