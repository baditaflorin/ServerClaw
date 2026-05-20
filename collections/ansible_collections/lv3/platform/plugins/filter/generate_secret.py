"""Jinja2 filter for generating secrets with srvclaw_ prefix (ADR 0480)."""

import sys
from pathlib import Path

# Import shared utility from scripts/.
# Use .resolve() so this works whether loaded directly (collections/…/filter/, parents[6])
# or via the filter_plugins/ symlink (__file__ = symlink path, 2 levels deep).
# After resolving, the real path is always 7 levels deep from repo_root.
sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "scripts"))
from secret_masking_utility import generate_real_secret, generate_real_secret_hex


def secret(service_name="", length=32):
    """
    Generate a real secret with srvclaw_ prefix for use in Ansible.

    Use in any role to generate a new secret without hardcoding openssl commands.

    Args:
        service_name: Service identifier (e.g., 'dbeaver', 'gitea')
        length: Byte length of random portion (default 32)

    Returns:
        srvclaw_<service>_<random> secret

    Examples:
        {{ 'dbeaver' | secret }}
        # → srvclaw_dbeaver_VvPEZNJb3A79STW9TLxHMJoYAJ3mOEMOjIm2yPqqjak

        {{ '' | secret }}
        # → srvclaw_<random>

        {{ 'gitea' | secret(length=24) }}
        # → srvclaw_gitea_<shorter-random>
    """
    return generate_real_secret(service_name=service_name, length=length)


def secret_hex(service_name="", length=32):
    """
    Generate a hex secret with srvclaw_hex_ prefix (ADR 0403 hex_32 form).

    Use for services that require pure hex credentials (e.g., Outline SECRET_KEY).
    The value stored on disk is srvclaw_hex_<service>_<64hex>; use the
    secret_payload filter to extract just the 64-char hex portion for env vars.

    Args:
        service_name: Service identifier (e.g., 'outline')
        length: Byte length of random portion (default 32 = 64 hex chars)

    Returns:
        srvclaw_hex_<service>_<64hex> secret

    Examples:
        {{ 'outline' | secret_hex }}
        # → srvclaw_hex_outline_a3f1...  (srvclaw_hex_ prefix + 64 hex chars)

        {{ 'outline' | secret_hex | secret_payload }}
        # → a3f1...  (only the 64 hex chars, ready for Outline SECRET_KEY)
    """
    return generate_real_secret_hex(service_name=service_name, length=length)


def secret_payload(value):
    """
    Extract the raw payload from a srvclaw_-prefixed secret.

    Strips the greppable prefix (srvclaw_, srvclaw_hex_) and service tag,
    returning only the credential payload for use in env vars.

    srvclaw_hex_outline_<64hex>  →  <64hex>
    srvclaw_outline_<urlsafe>    →  <urlsafe>
    <raw-value>                  →  <raw-value>   (pass-through)

    Use this in set_fact or templates after reading a hex secret file so that
    the env var gets only the valid hex, not the full prefixed string.
    """
    import re
    # Matches srvclaw_ or srvclaw_hex_ followed by an optional service tag (word_)
    # and captures everything after the last underscore-delimited tag.
    # Pattern: srvclaw_(hex_)?(<word>_)+<payload>
    # We use a greedy split: everything after 'srvclaw_(hex_)?<service>_' is the payload.
    match = re.match(r'^srvclaw_(?:hex_)?[a-z0-9]+_(.+)$', value)
    return match.group(1) if match else value


class FilterModule:
    """Ansible filter plugin for secret generation."""

    def filters(self):
        return {
            "secret": secret,
            "secret_hex": secret_hex,
            "secret_payload": secret_payload,
        }
