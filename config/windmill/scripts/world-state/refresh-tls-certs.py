from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from platform.world_state.windmill_entrypoint import maybe_run_via_uv, render_result


def main(
    repo_path: str = "/srv/proxmox_florin_server",
    dsn: str | None = None,
    publish_nats: bool = True,
):
    fallback = maybe_run_via_uv(
        script_path=Path(__file__),
        repo_path=repo_path,
        dsn=dsn,
        publish_nats=publish_nats,
    )
    if fallback is not None:
        return fallback
    from platform.world_state.workers import run_worker

    return run_worker("tls_cert_expiry", repo_path=repo_path, dsn=dsn, publish_nats=publish_nats)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh the world-state tls_cert_expiry surface.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    parser.add_argument("--dsn")
    parser.add_argument("--output-file", type=Path, help="Optional JSON output file for fallback execution.")
    parser.add_argument("--no-publish-nats", action="store_true")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    render_result(
        main(
            repo_path=args.repo_path,
            dsn=args.dsn,
            publish_nats=not args.no_publish_nats,
        ),
        output_file=args.output_file,
    )
