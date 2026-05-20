"""Jinja2 filter for generating secrets with srvclaw_ prefix (ADR 0480)."""

import sys
from pathlib import Path

# Import shared utility from scripts/.
# Use .resolve() so this works whether loaded directly (collections/…/filter/, parents[6])
# or via the filter_plugins/ symlink (__file__ = symlink path, 2 levels deep).
# After resolving, the real path is always 7 levels deep from repo_root.
sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "scripts"))
from secret_masking_utility import generate_real_secret


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


class FilterModule:
    """Ansible filter plugin for secret generation."""

    def filters(self):
        return {"secret": secret}
