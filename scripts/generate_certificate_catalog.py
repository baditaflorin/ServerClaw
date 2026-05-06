#!/usr/bin/env python3
"""
Generate deployment-specific certificate-catalog.json from template and .local/identity.yml.

This allows switching domains (e.g., from lv3.org → newdomain.com) without code changes.
The template uses {{ platform_domain }} placeholders which are filled at deployment time.

ADR 0480 Phase 4: Domain-agnostic infrastructure as code (IaC)
"""

import json
import sys
from pathlib import Path
from typing import Any

import yaml


def load_deployment_config() -> dict[str, Any]:
    """Load platform_domain from .local/identity.yml."""
    identity_path = Path(".local/identity.yml")
    if not identity_path.exists():
        raise FileNotFoundError(
            f".local/identity.yml not found. Create it with: "
            f"mkdir -p .local && echo 'platform_domain: yourdomain.com' > .local/identity.yml"
        )

    with open(identity_path) as f:
        config = yaml.safe_load(f) or {}

    if "platform_domain" not in config:
        raise ValueError("platform_domain not set in .local/identity.yml. Add: platform_domain: yourdomain.com")

    return config


def substitute_domain(obj: Any, platform_domain: str) -> Any:
    """Recursively substitute {{ platform_domain }} with actual domain."""
    if isinstance(obj, dict):
        return {k: substitute_domain(v, platform_domain) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [substitute_domain(item, platform_domain) for item in obj]
    elif isinstance(obj, str):
        return obj.replace("{{ platform_domain }}", platform_domain).replace("example.com", platform_domain)
    return obj


def main():
    repo_root = Path(__file__).parents[1]
    template_path = repo_root / "config/certificate-catalog.template.json"
    output_path = repo_root / "config/certificate-catalog.json"

    # Load deployment config
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
