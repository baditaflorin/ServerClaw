from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


def main(
    repo_path: str = "/srv/proxmox_florin_server",
    dsn: str | None = None,
    publish_nats: bool = True,
):
    repo_root = Path(repo_path)
    try:
        import yaml  # noqa: F401
    except ModuleNotFoundError:
        script_path = repo_root / "config" / "windmill" / "scripts" / "world-state" / "refresh-service-health.py"
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            output_path = Path(handle.name)
        command = [
            "uv",
            "run",
            "--with",
            "pyyaml",
            "--with",
            "nats-py",
            "python",
            str(script_path),
            "--repo-path",
            str(repo_root),
            "--output-file",
            str(output_path),
        ]
        if dsn:
            command.extend(["--dsn", dsn])
        if not publish_nats:
            command.append("--no-publish-nats")
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{repo_root}:{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(repo_root)
        result = subprocess.run(command, cwd=repo_root, env=env, text=True, capture_output=True, check=False)
        output = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else result.stdout.strip()
        output_path.unlink(missing_ok=True)
        if result.returncode != 0:
            return {
                "status": "error",
                "command": " ".join(shlex.quote(part) for part in command),
                "returncode": result.returncode,
                "stdout": output,
                "stderr": result.stderr.strip(),
            }
        if not output:
            return {
                "status": "error",
                "reason": "fallback subprocess produced no JSON output",
                "command": " ".join(shlex.quote(part) for part in command),
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        return json.loads(output)

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
        del sys.modules["platform"]

    from platform.world_state.workers import run_worker

    return run_worker("service_health", repo_path=repo_path, dsn=dsn, publish_nats=publish_nats)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh the world-state service_health surface.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    parser.add_argument("--dsn")
    parser.add_argument("--output-file", type=Path, help="Optional JSON output file for fallback execution.")
    parser.add_argument("--no-publish-nats", action="store_true")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    result = main(
        repo_path=args.repo_path,
        dsn=args.dsn,
        publish_nats=not args.no_publish_nats,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output_file:
        args.output_file.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
