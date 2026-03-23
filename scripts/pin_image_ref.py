#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys

from container_image_policy import resolve_remote_digest


def split_image_reference(image: str) -> tuple[str, str]:
    image = image.strip()
    if not image:
        raise ValueError("image reference must be non-empty")
    if "@" in image:
        raise ValueError("image reference must omit a digest")

    tag = "latest"
    last_colon = image.rfind(":")
    last_slash = image.rfind("/")
    if last_colon > last_slash:
        image, tag = image[:last_colon], image[last_colon + 1 :]
    if not image or not tag:
        raise ValueError("image reference must use registry/repository:tag")
    return image, tag


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve an image reference to a digest-pinned ref.")
    parser.add_argument("--image", required=True)
    parser.add_argument("--platform", default="linux/amd64")
    args = parser.parse_args(argv)

    try:
        registry_ref, tag = split_image_reference(args.image)
        digest = resolve_remote_digest(registry_ref, tag, args.platform)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"{registry_ref}:{tag}@{digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
