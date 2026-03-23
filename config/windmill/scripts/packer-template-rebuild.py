import hashlib
import json
import os
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


TEMPLATE_ORDER = [
    "lv3-debian-base",
    "lv3-docker-host",
    "lv3-postgres-host",
    "lv3-ops-base",
]


def run_command(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text())


def resolve_repo_root(repo_path: str) -> Path:
    repo_root = Path(repo_path).resolve()
    if not repo_root.exists():
        raise FileNotFoundError(f"repo root does not exist: {repo_root}")
    return repo_root


def resolve_openbao_credentials() -> dict[str, str]:
    token_id = os.environ.get("PKR_VAR_proxmox_api_token_id") or os.environ.get("PROXMOX_API_TOKEN_ID", "")
    token_secret = os.environ.get("PKR_VAR_proxmox_api_token_secret") or os.environ.get("PROXMOX_API_TOKEN_SECRET", "")
    if token_id and token_secret:
        return {
            "PKR_VAR_proxmox_api_token_id": token_id,
            "PKR_VAR_proxmox_api_token_secret": token_secret,
        }

    openbao_addr = os.environ.get("OPENBAO_ADDR", "")
    openbao_token = os.environ.get("OPENBAO_TOKEN", "")
    if not openbao_addr or not openbao_token:
        raise RuntimeError("missing Proxmox token environment and no OpenBao session is available")

    openbao_bin = os.environ.get("OPENBAO_BIN", shutil.which("vault") or "vault")
    secret_path = os.environ.get("OPENBAO_SECRET_PATH", "secret/build-server/proxmox-api-token")
    result = run_command(
        [openbao_bin, "kv", "get", "-format=json", secret_path],
        cwd=Path.cwd(),
        env={
            **os.environ,
            "VAULT_ADDR": openbao_addr,
            "VAULT_TOKEN": openbao_token,
        },
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "OpenBao lookup failed")

    payload = json.loads(result.stdout)
    data = payload.get("data", {}).get("data", {})
    token_id = data.get("token_id") or data.get("id")
    token_secret = data.get("token_secret") or data.get("secret")
    if not token_id or not token_secret:
        raise RuntimeError("OpenBao secret payload is missing token_id/token_secret fields")

    return {
        "PKR_VAR_proxmox_api_token_id": str(token_id),
        "PKR_VAR_proxmox_api_token_secret": str(token_secret),
    }


def calculate_template_digest(repo_root: Path, image: str) -> str:
    digest = hashlib.sha256()
    inputs = [
        repo_root / "packer" / "variables" / "common.pkrvars.hcl",
        repo_root / "packer" / "variables" / f"{image}.pkrvars.hcl",
        repo_root / "packer" / "variables" / "build-server.pkrvars.hcl",
        repo_root / "packer" / "templates" / f"{image}.pkr.hcl",
    ]
    inputs.extend(sorted((repo_root / "packer" / "scripts").glob("*.sh")))

    for path in inputs:
        digest.update(path.relative_to(repo_root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def update_manifest(repo_root: Path, manifest: dict, image: str) -> None:
    version = (repo_root / "VERSION").read_text().strip()
    commit = run_command(["git", "rev-parse", "HEAD"], cwd=repo_root)
    if commit.returncode != 0:
        raise RuntimeError(commit.stderr.strip() or "failed to resolve git HEAD")

    manifest["templates"][image].update(
        {
            "build_date": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "version": version,
            "digest": calculate_template_digest(repo_root, image),
            "packer_commit": commit.stdout.strip(),
        }
    )


def rebuild_template(repo_root: Path, image: str, env: dict[str, str]) -> dict[str, object]:
    command = ["make", "remote-packer-build", f"IMAGE={image}"]
    result = run_command(command, cwd=repo_root, env={**os.environ, **env})
    return {
        "image": image,
        "command": " ".join(shlex.quote(part) for part in command),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def maybe_commit_manifest(repo_root: Path, manifest_path: Path) -> subprocess.CompletedProcess[str] | None:
    status = run_command(["git", "status", "--short", str(manifest_path.relative_to(repo_root))], cwd=repo_root)
    if not status.stdout.strip():
        return None

    run_command(["git", "add", str(manifest_path.relative_to(repo_root))], cwd=repo_root)
    return run_command(["git", "commit", "-m", "Update VM template manifest after Packer rebuild"], cwd=repo_root)


def main(repo_path: str = "/srv/proxmox_florin_server") -> dict[str, object]:
    repo_root = resolve_repo_root(repo_path)
    manifest_path = repo_root / "config" / "vm-template-manifest.json"
    manifest = load_manifest(manifest_path)
    credentials = resolve_openbao_credentials()

    results = []
    for image in TEMPLATE_ORDER:
        result = rebuild_template(repo_root, image, credentials)
        results.append(result)
        if result["returncode"] != 0:
            return {
                "status": "error",
                "failed_image": image,
                "results": results,
            }
        update_manifest(repo_root, manifest, image)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    commit = maybe_commit_manifest(repo_root, manifest_path)
    return {
        "status": "ok",
        "manifest": str(manifest_path),
        "results": results,
        "commit": None
        if commit is None
        else {
            "returncode": commit.returncode,
            "stdout": commit.stdout.strip(),
            "stderr": commit.stderr.strip(),
        },
    }


if __name__ == "__main__":
    print(json.dumps(main()))
