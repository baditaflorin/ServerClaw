#!/usr/bin/env python3
"""Bootstrap LiteLLM virtual keys from config/llm-gateway/consumer-keys.yaml.

Reads the portable consumer-keys DTO and provisions virtual keys via the
LiteLLM /key/generate API. Writes generated keys to .local/litellm/keys/.

Usage:
    python scripts/litellm_bootstrap.py \
        --base-url http://10.10.10.20:4000 \
        --master-key-file .local/litellm/master-key.txt
"""

import argparse
import sys
from pathlib import Path

try:
    import requests
    import yaml
except ImportError:
    print("ERROR: requires 'requests' and 'pyyaml'. Install with: pip install requests pyyaml", file=sys.stderr)
    sys.exit(1)


CONSUMER_KEYS_PATH = Path(__file__).parent.parent / "config" / "llm-gateway" / "consumer-keys.yaml"
OUTPUT_DIR = Path(__file__).parent.parent / ".local" / "litellm" / "keys"


def load_consumers(path: Path) -> list:
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("consumers", [])


def generate_key(base_url: str, master_key: str, consumer: dict) -> dict:
    """Generate a virtual key for a consumer via the LiteLLM API."""
    payload = {
        "key_alias": consumer["name"],
        "models": consumer.get("models", ["*"]),
        "max_budget": None,
        "duration": None,
        "metadata": {
            "description": consumer.get("description", ""),
            "source": "litellm_bootstrap.py",
        },
    }
    resp = requests.post(
        f"{base_url}/key/generate",
        json=payload,
        headers={
            "Authorization": f"Bearer {master_key}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="Bootstrap LiteLLM virtual keys")
    parser.add_argument("--base-url", required=True, help="LiteLLM proxy base URL")
    parser.add_argument("--master-key-file", required=True, help="Path to master key file")
    parser.add_argument("--consumers-file", default=str(CONSUMER_KEYS_PATH), help="Path to consumer-keys.yaml")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="Directory to write generated keys")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without making API calls")
    args = parser.parse_args()

    master_key = Path(args.master_key_file).read_text().strip()
    consumers = load_consumers(Path(args.consumers_file))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for consumer in consumers:
        name = consumer["name"]
        if args.dry_run:
            print(f"[dry-run] Would generate key for: {name}")
            continue

        print(f"Generating key for: {name} ... ", end="", flush=True)
        try:
            result = generate_key(args.base_url, master_key, consumer)
            key = result.get("key", result.get("generated_key", ""))
            key_file = output_dir / f"{name}.key"
            key_file.write_text(key + "\n")
            key_file.chmod(0o600)
            print(f"OK -> {key_file}")
        except Exception as e:
            print(f"FAILED: {e}", file=sys.stderr)
            sys.exit(1)

    print(f"\nDone. {len(consumers)} keys written to {output_dir}")


if __name__ == "__main__":
    main()
