"""
ADR 0417 — External Attack Surface Hardening: static analysis regression tests.

These tests verify that security-sensitive defaults and content remain correct.
They read files from the repo and assert properties — no network calls, no
external dependencies.
"""

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

LIBRECHAT_DEFAULTS = REPO_ROOT / "roles/librechat_runtime/defaults/main.yml"
CHAT_PROMPT = REPO_ROOT / "config/serverclaw/system-prompt-chat.md"

# RFC 1918 IP pattern — matches 10.x.x.x, 172.16-31.x.x, 192.168.x.x
RFC_1918_PATTERN = re.compile(
    r"""
    (?:
        10\.\d{1,3}\.\d{1,3}\.\d{1,3}          |  # 10.0.0.0/8
        172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}  |  # 172.16.0.0/12
        192\.168\.\d{1,3}\.\d{1,3}              # 192.168.0.0/16
    )
    """,
    re.VERBOSE,
)


def _load_librechat_defaults() -> dict:
    """Load and parse the librechat_runtime defaults YAML."""
    text = LIBRECHAT_DEFAULTS.read_text(encoding="utf-8")
    # Strip the leading comment block before the YAML document separator
    return yaml.safe_load(text)


class TestLibrechatRegistrationDefaults:
    """ADR 0417 Decision 1: registration defaults to false (secure by default)."""

    def test_allow_registration_default_is_false(self) -> None:
        """ALLOW_REGISTRATION must default to false to prevent anonymous account creation."""
        defaults = _load_librechat_defaults()
        value = defaults.get("librechat_allow_registration")
        assert value is not None, (
            f"librechat_allow_registration is missing from {LIBRECHAT_DEFAULTS} — it must be explicitly set to false"
        )
        assert value is False, (
            f"librechat_allow_registration default is {value!r}; "
            "expected False — open registration allows anonymous API key consumption. "
            "Set to true only in an inventory overlay when intentional."
        )

    def test_allow_social_registration_default_is_false(self) -> None:
        """ALLOW_SOCIAL_REGISTRATION must default to false to prevent self-registration via OIDC."""
        defaults = _load_librechat_defaults()
        value = defaults.get("librechat_allow_social_registration")
        assert value is not None, (
            "librechat_allow_social_registration is missing from "
            f"{LIBRECHAT_DEFAULTS} — it must be explicitly set to false"
        )
        assert value is False, (
            f"librechat_allow_social_registration default is {value!r}; "
            "expected False — social registration via OIDC auto-creates accounts "
            "for anyone who can authenticate with the IdP. "
            "Set to true only in an inventory overlay when intentional."
        )

    def test_allow_social_login_default_is_true(self) -> None:
        """ALLOW_SOCIAL_LOGIN must remain true: Keycloak OIDC is the primary auth path."""
        defaults = _load_librechat_defaults()
        value = defaults.get("librechat_allow_social_login")
        assert value is not None, (
            f"librechat_allow_social_login is missing from {LIBRECHAT_DEFAULTS} — it must be explicitly set"
        )
        assert value is True, (
            f"librechat_allow_social_login default is {value!r}; "
            "expected True — Keycloak OIDC login must remain enabled for SSO to work."
        )


class TestChatPromptNoInternalIPs:
    """ADR 0417 Decision 2: chat-mode system prompt must not contain RFC 1918 IPs."""

    def test_chat_prompt_exists(self) -> None:
        """Verify the chat prompt file is present at the expected path."""
        assert CHAT_PROMPT.exists(), (
            f"Chat prompt file not found at {CHAT_PROMPT}. This file is required by the librechat_runtime role."
        )

    def test_chat_prompt_contains_no_rfc1918_ips(self) -> None:
        """
        RFC 1918 IPs must not appear in the chat-mode system prompt.

        LibreChat exposes GET /api/config without authentication.  The response
        includes modelSpecs.preset.promptPrefix (i.e. this file's content).
        Embedding internal IPs in a publicly-readable endpoint aids reconnaissance.
        """
        content = CHAT_PROMPT.read_text(encoding="utf-8")
        matches = RFC_1918_PATTERN.findall(content)
        assert not matches, (
            f"RFC 1918 IP addresses found in {CHAT_PROMPT}: {matches}\n"
            "The chat-mode system prompt is exposed unauthenticated via "
            "GET /api/config — remove internal IPs and use role names only. "
            "(ADR 0417 Decision 2)"
        )
