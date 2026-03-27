#!/usr/bin/env python3

import argparse
import json
from pathlib import Path


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text())


def summarize_manifest(manifest: dict) -> list[dict[str, str]]:
    docker_images = manifest.get("docker_images", [])
    return [
        {
            "component": "docker_layers",
            "status": "warm" if docker_images else "cold",
            "detail": f"{len(docker_images)} image(s)",
        },
        {
            "component": "pip_cache",
            "status": "warm" if manifest.get("pip_cache_size_mb", 0) else "cold",
            "detail": f"{manifest.get('pip_cache_size_mb', 0)} MB",
        },
        {
            "component": "packer_plugins",
            "status": "warm" if manifest.get("packer_plugins") else "cold",
            "detail": f"{len(manifest.get('packer_plugins', []))} plugin(s)",
        },
        {
            "component": "ansible_collections",
            "status": "warm" if manifest.get("ansible_collections") else "cold",
            "detail": f"{len(manifest.get('ansible_collections', []))} collection(s)",
        },
    ]


def render_summary(manifest: dict) -> str:
    rows = summarize_manifest(manifest)
    lines = ["COMPONENT            STATUS  DETAIL"]
    for row in rows:
        lines.append(f"{row['component']:<20} {row['status']:<6} {row['detail']}")
    lines.append(f"last_warmed          {manifest.get('last_warmed') or 'never'}")
    warnings = manifest.get("warnings", [])
    if warnings:
        lines.append("warnings")
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Display the build cache manifest summary.")
    parser.add_argument(
        "--manifest",
        default="config/build-cache-manifest.json",
        help="Path to config/build-cache-manifest.json",
    )
    args = parser.parse_args()

    manifest = load_manifest(Path(args.manifest))
    print(render_summary(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
