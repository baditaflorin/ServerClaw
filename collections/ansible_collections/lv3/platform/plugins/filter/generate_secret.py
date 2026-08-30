"""Jinja2 filter for generating secrets with srvclaw_ prefix (ADR 0480)."""

import sys
from pathlib import Path

# Import the shared utility whether Ansible loads this hard-linked plugin from
# the repository root or through its collection path.
plugin_path = Path(__file__).resolve()
repo_root = next(
    parent
    for parent in plugin_path.parents
    if (parent / "scripts" / "secret_masking_utility.py").is_file()
)
sys.path.insert(0, str(repo_root / "scripts"))
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
