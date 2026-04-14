"""
ADR 0417 — External Attack Surface Hardening: static analysis regression tests.

These tests verify that security-sensitive defaults and content remain correct.
They read files from the repo and assert properties — no network calls, no
external dependencies.

Decision 2 note: the chat-mode system prompt intentionally retains internal host
IPs (10.10.10.x) so that operators can get useful troubleshooting guidance from
the AI.  This is safe because:
  - LibreChat registration is disabled by default (Decision 1) so only
    Keycloak-provisioned accounts can log in and USE the chat.
  - RFC 1918 IPs are unreachable from the public internet regardless.
  - The /api/config endpoint leaks the prompt pre-auth, but that is low risk
    given the above constraints — and removing the IPs would make the assistant
    useless for ops investigations.
The test below therefore checks that the topology section IS present (preventing
accidental gutting) rather than checking for absence of IPs.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

LIBRECHAT_DEFAULTS = REPO_ROOT / "roles/librechat_runtime/defaults/main.yml"
CHAT_PROMPT = REPO_ROOT / "config/serverclaw/system-prompt-chat.md"


def _load_librechat_defaults() -> dict:
    """Load and parse the librechat_runtime defaults YAML."""
    text = LIBRECHAT_DEFAULTS.read_text(encoding="utf-8")
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


class TestChatPromptTopology:
    """ADR 0417 Decision 2 (revised): chat prompt must retain platform topology for ops use."""

    def test_chat_prompt_exists(self) -> None:
        """Verify the chat prompt file is present at the expected path."""
        assert CHAT_PROMPT.exists(), (
            f"Chat prompt file not found at {CHAT_PROMPT}. This file is required by the librechat_runtime role."
        )

    def test_chat_prompt_contains_platform_overview(self) -> None:
        """
        The chat-mode system prompt must contain the Platform overview section.

        Operators need the model to know host roles and IPs to get useful
        troubleshooting guidance (e.g. 'check docker-runtime at 10.10.10.20').
        Do not remove this section — the low-severity /api/config pre-auth leak
        is acceptable because registration is disabled and the IPs are RFC 1918.
        (ADR 0417 Decision 2 — see module docstring for full rationale)
        """
        content = CHAT_PROMPT.read_text(encoding="utf-8")
        assert "## Platform overview" in content, (
            f"'## Platform overview' section missing from {CHAT_PROMPT}. "
            "This section provides host topology to operators via the AI assistant — do not remove it."
        )
        assert "docker-runtime" in content, (
            f"'docker-runtime' host reference missing from {CHAT_PROMPT}. "
            "Operators need host names/roles in the prompt for useful troubleshooting guidance."
        )
