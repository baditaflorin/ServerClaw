#!/usr/bin/env python3
"""
Generate deployment-specific certificate-catalog.json from the identity selected for this run.

This allows switching domains (e.g., from example.com → newdomain.com) without code changes.
The template uses {{ platform_domain }} placeholders which are filled at deployment time.

ADR 0480 Phase 4: Domain-agnostic infrastructure as code (IaC)
"""

import json
import sys
from pathlib import Path
from typing import Any

from script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path(__file__)

from identity_yaml import load_identity_vars


def load_deployment_config() -> dict[str, Any]:
    """Load ``platform_domain`` through the shared deployment selector."""
    config = load_identity_vars()

    if "platform_domain" not in config:
        raise ValueError(
            "platform_domain is not set in the selected identity. Set "
            "PLATFORM_IDENTITY_OVERLAY to the intended identity overlay or configure .local/identity.yml"
        )

    return config


def substitute_domain(obj: Any, platform_domain: str) -> Any:
    """Recursively substitute deployment identity placeholders."""
    platform_config_prefix = platform_domain.split(".", 1)[0]
    if isinstance(obj, dict):
        return {k: substitute_domain(v, platform_domain) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [substitute_domain(item, platform_domain) for item in obj]
    elif isinstance(obj, str):
        return (
            obj.replace("{{ platform_domain }}", platform_domain)
            .replace("{{ platform_config_prefix }}", platform_config_prefix)
            .replace("example.com", platform_domain)
        )
    return obj


def main():
    repo_root = Path(__file__).parents[1]
    template_path = repo_root / "config/certificate-catalog.template.json"
    output_path = repo_root / "config/certificate-catalog.json"

    # Load deployment config through the explicit/shared identity selector.
    config = load_deployment_config()
    platform_domain = config["platform_domain"]

    # Load template
    if not template_path.exists():
        print(
            f"error: template not found at {template_path}. Please commit certificate-catalog.template.json",
            file=sys.stderr,
        )
        return 1

    with open(template_path) as f:
        catalog = json.load(f)

    # Substitute domains
    catalog = substitute_domain(catalog, platform_domain)

    # Write output
    with open(output_path, "w") as f:
        json.dump(catalog, f, indent=2)

    print(f"✓ Generated {output_path} for domain: {platform_domain}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
