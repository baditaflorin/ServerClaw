import json
import shlex
import subprocess
from pathlib import Path


RUNNERS = {
    "ansible": {
        "image": "registry.lv3.org/check-runner/ansible:2.17.10",
        "context": "docker/check-runners/ansible",
    },
    "python": {
        "image": "registry.lv3.org/check-runner/python:3.12.10",
        "context": "docker/check-runners/python",
    },
    "infra": {
        "image": "registry.lv3.org/check-runner/infra:2026.03.23",
        "context": "docker/check-runners/infra",
    },
    "security": {
        "image": "registry.lv3.org/check-runner/security:2026.03.23",
        "context": "docker/check-runners/security",
    },
}


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def build_and_push(repo_root: Path, image: str, context: str) -> dict[str, object]:
    cache_ref = f"{image}:cache"
    command = [
        "docker",
        "buildx",
        "build",
        "--platform",
        "linux/amd64",
        "--push",
        "--build-arg",
        "BUILDKIT_INLINE_CACHE=1",
        "--cache-from",
        f"type=registry,ref={cache_ref}",
        "--cache-to",
        f"type=registry,ref={cache_ref},mode=max",
        "--tag",
        image,
        context,
    ]
    result = run(command, repo_root)
    return {
        "command": " ".join(shlex.quote(part) for part in command),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def inspect_digest(repo_root: Path, image: str) -> str:
    result = run(["docker", "buildx", "imagetools", "inspect", image], repo_root)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"failed to inspect {image}")

    for line in result.stdout.splitlines():
        if line.strip().startswith("Digest:"):
            return line.split(":", 1)[1].strip()
    raise RuntimeError(f"no digest found for {image}")


def update_manifest(manifest_path: Path, digests: dict[str, str]) -> None:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    for config in payload.values():
        image = config.get("image", "")
        for digest_image, digest in digests.items():
            if image == digest_image:
                config["digest"] = digest
                break
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def maybe_commit(repo_root: Path, manifest_path: Path) -> subprocess.CompletedProcess[str] | None:
    status = run(["git", "status", "--short", str(manifest_path.relative_to(repo_root))], repo_root)
    if not status.stdout.strip():
        return None

    run(["git", "add", str(manifest_path.relative_to(repo_root))], repo_root)
    return run(
        ["git", "commit", "-m", "Update check runner manifest digests"],
        repo_root,
    )


def main(repo_path: str = "/srv/proxmox_florin_server"):
    repo_root = Path(repo_path)
    manifest_path = repo_root / "config/check-runner-manifest.json"
    build_results = {}
    digests = {}

    for name, runner in RUNNERS.items():
        build_results[name] = build_and_push(
            repo_root,
            runner["image"],
            runner["context"],
        )
        if build_results[name]["returncode"] != 0:
            return {
                "status": "error",
                "phase": "build",
                "runner": name,
                "result": build_results[name],
            }
        digests[runner["image"]] = inspect_digest(repo_root, runner["image"])

    update_manifest(manifest_path, digests)
    commit = maybe_commit(repo_root, manifest_path)

    return {
        "status": "ok",
        "manifest": str(manifest_path),
        "digests": digests,
        "build_results": build_results,
        "commit": None
        if commit is None
        else {
            "returncode": commit.returncode,
            "stdout": commit.stdout.strip(),
            "stderr": commit.stderr.strip(),
        },
    }
