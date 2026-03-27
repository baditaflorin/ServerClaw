import argparse
import json
import os
import shlex
import subprocess
from pathlib import Path


def run_command(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def load_build_server_config(repo_root: Path) -> dict:
    return json.loads((repo_root / "config" / "build-server.json").read_text())


def load_collection_metadata(galaxy_path: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in galaxy_path.read_text().splitlines():
        if ":" not in line or line.lstrip().startswith("- "):
            continue
        key, value = line.split(":", 1)
        if key.strip() in {"namespace", "name", "version"}:
            metadata[key.strip()] = value.strip()
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and optionally publish the lv3.platform collection.")
    parser.add_argument("--repo-root", default="/srv/proxmox_florin_server")
    parser.add_argument("--server", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    config = load_build_server_config(repo_root)
    collection_root = repo_root / config.get("collection_root", "collections/ansible_collections/lv3/platform")
    galaxy_path = collection_root / "galaxy.yml"
    build_dir = repo_root / "build" / "collections"
    ansible_galaxy = os.environ.get("ANSIBLE_GALAXY_BIN", "ansible-galaxy")
    server_name = args.server or config.get("galaxy_server_name", "internal_galaxy")
    token = os.environ.get("ANSIBLE_GALAXY_SERVER_TOKEN", "")

    if not collection_root.exists():
        print(json.dumps({"status": "blocked", "reason": "collection root missing", "collection_root": str(collection_root)}))
        return 1
    if not galaxy_path.exists():
        print(json.dumps({"status": "blocked", "reason": "galaxy.yml missing", "galaxy_path": str(galaxy_path)}))
        return 1

    build_dir.mkdir(parents=True, exist_ok=True)
    metadata = load_collection_metadata(galaxy_path)
    version = metadata.get("version", "0.0.0")
    tarball = build_dir / f"{metadata.get('namespace', 'lv3')}-{metadata.get('name', 'platform')}-{version}.tar.gz"

    build_command = [ansible_galaxy, "collection", "build", str(collection_root), "--output-path", str(build_dir), "--force"]
    publish_command = [ansible_galaxy, "collection", "publish", str(tarball), "--server", server_name]
    if token:
        publish_command.extend(["--token", token])

    payload = {
        "status": "ok",
        "collection_root": str(collection_root),
        "server": server_name,
        "build_command": " ".join(shlex.quote(part) for part in build_command),
        "publish_command": " ".join(shlex.quote(part) for part in publish_command),
        "dry_run": args.dry_run,
        "galaxy_server_url": config.get("galaxy_server_url", ""),
    }

    build_result = run_command(build_command, cwd=repo_root)
    payload["build_returncode"] = build_result.returncode
    payload["build_stdout"] = build_result.stdout.strip()
    payload["build_stderr"] = build_result.stderr.strip()
    if build_result.returncode != 0:
        payload["status"] = "error"
        print(json.dumps(payload))
        return build_result.returncode

    if args.dry_run:
        print(json.dumps(payload))
        return 0

    if not token:
        payload["status"] = "blocked"
        payload["reason"] = "ANSIBLE_GALAXY_SERVER_TOKEN is not set"
        print(json.dumps(payload))
        return 1

    publish_result = run_command(publish_command, cwd=repo_root)
    payload["publish_returncode"] = publish_result.returncode
    payload["publish_stdout"] = publish_result.stdout.strip()
    payload["publish_stderr"] = publish_result.stderr.strip()
    payload["status"] = "ok" if publish_result.returncode == 0 else "error"
    print(json.dumps(payload))
    return publish_result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
