#!/usr/bin/env python3
"""
Secret Masking Utility for SrvClaw Infrastructure as Code (ADR 0480).

All real secrets now include srvclaw_ prefix for easy identification and filtering.
Enables: grep for srvclaw_ before commits, easy detection in logs/configs.

Patterns:
  - Real passwords: srvclaw_<service>_<randomsuffix> (searchable, filterable)
  - Real API keys: srvclaw_<service>_<randomsuffix> (searchable, filterable)

Usage:
  from scripts.secret_masking_utility import generate_real_secret

  # Generate a real secret with srvclaw_ prefix (use in any credential context)
  real_password = generate_real_secret(service_name='dbeaver')
  # → srvclaw_dbeaver_VvPEZNJb3A79STW9TLxHMJoYAJ3mOEMOjIm2yPqqjak

  # For Ansible roles: use in shell commands or jinja filters
  real_secret = generate_real_secret(service_name='gitea', length=32)
  # → srvclaw_gitea_<43-char-base64url>

  # Pre-commit hook catches any srvclaw_ pattern not in .local/
"""

import hashlib
import secrets
from typing import Literal


def generate_masked_secret(
    service_name: str, secret_type: Literal["password", "api_key"] = "password", deterministic: bool = True
) -> str:
    """
    Generate a masked secret with searchable prefix for commits.

    Masked secrets follow the pattern:
      password: srvclaw_<service>_<hash8>
      api_key:  srvclaw_api_<service>_<hash8>

    Args:
        service_name: Service identifier (e.g., 'dbeaver', 'gitea', 'hetzner')
        secret_type: 'password' or 'api_key'
        deterministic: If True, same service always gets same masked value

    Returns:
        Masked secret string safe for commits/documentation
    """
    if secret_type == "password":
        prefix = "srvclaw_"
    elif secret_type == "api_key":
        prefix = "srvclaw_api_"
    else:
        raise ValueError("secret_type must be 'password' or 'api_key'")

    if deterministic:
        # Create deterministic hash based on service name + type
        # Same input always produces same output for easy filtering
        hash_input = f"srvclaw.{secret_type}.{service_name}".encode()
        hash_obj = hashlib.sha256(hash_input)
        hash_suffix = hash_obj.hexdigest()[:8]
    else:
        # Use cryptographically secure random for one-offs
        hash_suffix = secrets.token_hex(4)

    return f"{prefix}{service_name}_{hash_suffix}"


def generate_real_secret(length: int = 32, service_name: str = "", with_prefix: bool = True) -> str:
    """
    Generate a real cryptographically secure secret with srvclaw_ prefix.

    Use this for actual credentials stored in .local/ directories or config.
    The srvclaw_ prefix allows easy grep/filtering of credentials before commits.
    Never commit output of this function to git.

    Args:
        length: Byte length for random portion (default 32 = 43 chars base64url)
        service_name: Service identifier for prefix (e.g., 'dbeaver', 'gitea')
        with_prefix: If True, prefix with srvclaw_<service>_ (default True)

    Returns:
        Cryptographically secure secret with srvclaw_ prefix
        Format: srvclaw_<service>_<random> or srvclaw_<random> if no service
    """
    random_part = secrets.token_urlsafe(length)

    if not with_prefix:
        return random_part

    if service_name:
        return f"srvclaw_{service_name}_{random_part}"
    return f"srvclaw_{random_part}"


def is_masked_secret(value: str) -> bool:
    """Check if a string looks like a masked secret."""
    return value.startswith("srvclaw_") or value.startswith("srvclaw_api_")


def mask_secret_in_text(text: str, preserve_masked: bool = True) -> str:
    """
    Replace suspected real secrets in text with masked versions.

    Heuristic: Replace anything that looks like a secret (>20 chars of base64-like chars)
    with appropriate masked prefix.

    Args:
        text: Input text to sanitize
        preserve_masked: If True, leave existing srvclaw_* secrets alone

    Returns:
        Text with suspected secrets replaced
    """
    import re

    # Pattern: base64-url-like strings (20+ chars, mixed case + numbers + -_)
    secret_pattern = r"[A-Za-z0-9_\-]{20,}"

    def replacer(match):
        secret = match.group(0)
        if preserve_masked and is_masked_secret(secret):
            return secret  # Leave masked secrets as-is
        # Replace with generic masked version
        return generate_masked_secret("unknown", "api_key", deterministic=False)

    return re.sub(secret_pattern, replacer, text)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        print("=== Real Secrets (with srvclaw_ prefix for easy filtering) ===")
        print(f"DBeaver password:  {generate_real_secret(service_name='dbeaver')}")
        print(f"Gitea API key:     {generate_real_secret(service_name='gitea')}")
        print(f"Hetzner token:     {generate_real_secret(service_name='hetzner')}")
        print(f"PostgreSQL pwd:    {generate_real_secret(service_name='postgres')}")
        print()
        print("=== Masked Secrets (deterministic, for documentation) ===")
        print(f"DBeaver password:  {generate_masked_secret('dbeaver', 'password')}")
        print(f"Gitea API key:     {generate_masked_secret('gitea', 'api_key')}")
        print(f"Hetzner token:     {generate_masked_secret('hetzner', 'api_key')}")
        print(f"PostgreSQL pwd:    {generate_masked_secret('postgres', 'password')}")
        print()
        print("=== Masking Test ===")
        test_text = f"API key: 6k2OLvRXjwQtxhlfiWxW3dAIphH4NiOtoMdEHmfA7oqVTBrX0WZzSSctvgrkSQPb"
        print(f"Before: {test_text}")
        print(f"After:  {mask_secret_in_text(test_text)}")
    else:
        print(__doc__)
