#!/usr/bin/env python3
"""
Generate real secrets and masked metadata together (ADR 0480).

This script generates cryptographically secure secrets and simultaneously
creates deterministic masked versions for documentation, logs, and postmortems.

Usage:
  python3 scripts/generate_secret_with_mask.py \
    --service dbeaver \
    --type password \
    --output /path/to/.local/dbeaver/database-password.txt \
    --metadata /path/to/.local/dbeaver/.masked-secret

Returns JSON with:
  {
    "real_secret": "generated_secret_value",
    "masked_secret": "srvclaw_dbeaver_0c336f23",
    "output_file": "/path/...",
    "metadata_file": "/path/..."
  }
"""

import argparse
import json
import sys
from pathlib import Path

# Handle import from scripts directory
sys.path.insert(0, str(Path(__file__).parent))
from secret_masking_utility import generate_masked_secret, generate_real_secret


def main():
    parser = argparse.ArgumentParser(description="Generate secret with masked metadata for documentation")
    parser.add_argument("--service", required=True, help="Service identifier (e.g., dbeaver, gitea)")
    parser.add_argument(
        "--type",
        choices=["password", "api_key"],
        default="password",
        help="Secret type",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write real secret",
    )
    parser.add_argument(
        "--metadata",
        help="Path to write masked secret metadata (optional)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON (for Ansible)",
    )

    args = parser.parse_args()

    # Generate real secret with srvclaw_ prefix
    real_secret = generate_real_secret(service_name=args.service)

    # Generate masked equivalent for documentation
    masked_secret = generate_masked_secret(args.service, args.type, deterministic=True)

    # Write real secret to output file
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(real_secret + "\n")
    output_path.chmod(0o600)

    # Write masked metadata if requested
    metadata_path = None
    if args.metadata:
        metadata_path = Path(args.metadata)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(f"{masked_secret}\n")
        metadata_path.chmod(0o644)  # Metadata can be readable (it's not a secret)

    result = {
        "real_secret": real_secret,
        "masked_secret": masked_secret,
        "output_file": str(output_path),
    }
    if metadata_path:
        result["metadata_file"] = str(metadata_path)

    if args.json:
        print(json.dumps(result))
    else:
        print(f"✓ Generated secret for {args.service}")
        print(f"  Real:   {result['output_file']}")
        print(f"  Masked: {masked_secret}")
        if metadata_path:
            print(f"  Meta:   {metadata_path}")


if __name__ == "__main__":
    main()
