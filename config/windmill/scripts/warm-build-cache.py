import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


def _run_command(argv: list[str], cwd: Path | None = None) -> CommandResult:
    try:
        result = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return CommandResult(
            argv=argv,
            returncode=127,
            stdout="",
            stderr=str(exc),
        )

    return CommandResult(
        argv=argv,
        returncode=result.returncode,
        stdout=result.stdout.strip(),
        stderr=result.stderr.strip(),
    )


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text())


def collect_check_runner_images(manifest: dict[str, Any]) -> list[str]:
    images = {
        entry.get("image", "").strip()
        for entry in manifest.values()
        if isinstance(entry, dict) and entry.get("image")
    }
    return sorted(image for image in images if image)


def collect_requested_collections(requirements_text: str) -> list[str]:
    matches = re.findall(r"^\s*-\s+name:\s+([A-Za-z0-9_.-]+)\s*$", requirements_text, flags=re.MULTILINE)
    return sorted(dict.fromkeys(matches))


def find_packer_templates(repo_root: Path) -> list[Path]:
    return sorted(repo_root.rglob("*.pkr.hcl"))


def find_cached_packer_plugins(cache_root: Path) -> list[str]:
    if not cache_root.exists():
        return []
    plugins = {
        path.parent.name
        for path in cache_root.rglob("*")
        if path.is_file() and path.name.startswith("packer-plugin-")
    }
    return sorted(plugin for plugin in plugins if plugin)


def path_size_mb(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return max(1, path.stat().st_size // (1024 * 1024)) if path.stat().st_size else 0

    total_bytes = 0
    for candidate in path.rglob("*"):
        if candidate.is_file():
            total_bytes += candidate.stat().st_size
    return total_bytes // (1024 * 1024)


def docker_volume_size_mb(volume_name: str) -> int:
    inspect = _run_command(["docker", "volume", "inspect", volume_name])
    if inspect.returncode != 0:
        return 0

    payload = json.loads(inspect.stdout)
    mountpoint = payload[0].get("Mountpoint", "")
    return path_size_mb(Path(mountpoint)) if mountpoint else 0


def inspect_docker_image(image: str) -> dict[str, Any]:
    inspect = _run_command(
        [
            "docker",
            "image",
            "inspect",
            image,
            "--format",
            "{{json .RepoDigests}}|{{.Size}}",
        ]
    )
    if inspect.returncode != 0:
        return {"image": image, "digest": "", "size_mb": 0}

    digests_raw, _, size_raw = inspect.stdout.partition("|")
    digests = json.loads(digests_raw) if digests_raw else []
    size_mb = int(size_raw) // (1024 * 1024) if size_raw else 0
    return {
        "image": image,
        "digest": digests[0] if digests else "",
        "size_mb": size_mb,
    }


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def maybe_commit_manifest(repo_root: Path, manifest_path: Path, message: str) -> CommandResult | None:
    if not shutil.which("git"):
        return None

    relative_manifest = manifest_path.relative_to(repo_root)
    add_result = _run_command(["git", "add", str(relative_manifest)], cwd=repo_root)
    if add_result.returncode != 0:
        return add_result
    return _run_command(["git", "commit", "-m", message], cwd=repo_root)


def main(
    repo_path: str = "/srv/proxmox_florin_server",
    manifest_path: str = "config/build-cache-manifest.json",
    check_runner_manifest_path: str = "config/check-runner-manifest.json",
    collection_requirements_path: str = "collections/requirements.yml",
    pip_cache_volume: str = "pip-cache",
    pip_requirements_paths: list[str] | None = None,
    packer_cache_dir: str = "/opt/builds/.packer.d",
    ansible_collection_cache: str = "/opt/builds/.ansible/collections",
    commit_manifest: bool = False,
):
    repo_root = Path(repo_path)
    if pip_requirements_paths is None:
        pip_requirements_paths = [
            "requirements/platform-context-api.txt",
            "requirements/uptime-kuma-client.txt",
        ]

    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    warnings: list[str] = []
    image_manifest = _load_json(repo_root / check_runner_manifest_path, {})
    image_refs = collect_check_runner_images(image_manifest)
    if not image_refs:
        warnings.append("check-runner manifest missing or empty; Docker layer warming skipped")

    for image in image_refs:
        pull_result = _run_command(["docker", "pull", image])
        if pull_result.returncode != 0:
            warnings.append(f"docker pull failed for {image}: {pull_result.stderr or pull_result.stdout}")

    resolved_requirements = [
        Path(candidate)
        for candidate in pip_requirements_paths
        if (repo_root / candidate).exists()
    ]
    if not resolved_requirements:
        warnings.append("no pip requirements files found for cache warming")

    for requirement in resolved_requirements:
        pip_result = _run_command(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{pip_cache_volume}:/root/.cache/pip",
                "-v",
                f"{repo_root}:/workspace",
                "-w",
                "/workspace",
                "python:3.12-slim",
                "pip",
                "install",
                "--cache-dir",
                "/root/.cache/pip",
                "-r",
                str(requirement),
            ]
        )
        if pip_result.returncode != 0:
            warnings.append(f"pip cache warm failed for {requirement}: {pip_result.stderr or pip_result.stdout}")

    packer_templates = [template.relative_to(repo_root) for template in find_packer_templates(repo_root)]
    for template in packer_templates:
        packer_result = _run_command(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{repo_root}:/workspace",
                "-v",
                f"{packer_cache_dir}:/root/.packer.d",
                "-w",
                "/workspace",
                "hashicorp/packer:latest",
                "init",
                str(template),
            ]
        )
        if packer_result.returncode != 0:
            warnings.append(f"packer init failed for {template}: {packer_result.stderr or packer_result.stdout}")

    collection_requirements = repo_root / collection_requirements_path
    requested_collections = (
        collect_requested_collections(collection_requirements.read_text())
        if collection_requirements.exists()
        else []
    )
    if collection_requirements.exists():
        galaxy_result = _run_command(
            [
                "ansible-galaxy",
                "collection",
                "install",
                "-r",
                str(collection_requirements),
                "-p",
                ansible_collection_cache,
            ],
            cwd=repo_root,
        )
        if galaxy_result.returncode != 0:
            warnings.append(f"ansible-galaxy install failed: {galaxy_result.stderr or galaxy_result.stdout}")
    else:
        warnings.append("collections/requirements.yml is missing; Galaxy cache warm skipped")

    warmed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    manifest = _load_json(repo_root / manifest_path, {})
    manifest.update(
        {
            "docker_images": [
                {
                    **inspect_docker_image(image),
                    "last_pulled": warmed_at,
                }
                for image in image_refs
            ],
            "pip_cache_size_mb": docker_volume_size_mb(pip_cache_volume),
            "packer_plugins": find_cached_packer_plugins(Path(packer_cache_dir)),
            "ansible_collections": requested_collections,
            "last_warmed": warmed_at,
            "warnings": warnings,
        }
    )

    output_path = repo_root / manifest_path
    write_manifest(output_path, manifest)

    commit_result = None
    if commit_manifest:
        commit_result = maybe_commit_manifest(
            repo_root,
            output_path,
            "Refresh build cache manifest",
        )

    return {
        "status": "ok" if not warnings else "warning",
        "repo_path": str(repo_root),
        "manifest_path": str(output_path),
        "docker_images": manifest["docker_images"],
        "pip_cache_size_mb": manifest["pip_cache_size_mb"],
        "packer_plugins": manifest["packer_plugins"],
        "ansible_collections": manifest["ansible_collections"],
        "last_warmed": warmed_at,
        "warnings": warnings,
        "commit_result": None
        if commit_result is None
        else {
            "returncode": commit_result.returncode,
            "stdout": commit_result.stdout,
            "stderr": commit_result.stderr,
        },
    }


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, sort_keys=True))
