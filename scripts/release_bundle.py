#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from secrets import token_urlsafe
from typing import Any

from script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path(__file__)

from platform.datetime_compat import UTC, datetime
from controller_automation_toolkit import emit_cli_error, repo_path, run_command
from platform.retry import MaxRetriesExceeded, PlatformRetryError, RetryClass, RetryPolicy, with_retry


REPO_ROOT = repo_path()
CANONICAL_CONTROLLER_ROOT = Path(
    os.environ.get("LV3_CONTROLLER_REPO_ROOT", "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server")
)
DEFAULT_PRIVATE_KEY_PATH = CANONICAL_CONTROLLER_ROOT / ".local" / "gitea" / "release-bundle-cosign.key"
DEFAULT_PASSWORD_PATH = CANONICAL_CONTROLLER_ROOT / ".local" / "gitea" / "release-bundle-cosign.password.txt"
DEFAULT_OUTPUT_DIR = CANONICAL_CONTROLLER_ROOT / ".local" / "gitea" / "release-bundles"
DEFAULT_PUBLIC_KEY_PATH = REPO_ROOT / "keys" / "gitea-release-bundle-cosign.pub"
DEFAULT_COSIGN_DOCKER_IMAGE = "ghcr.io/sigstore/cosign/cosign:v3.0.2"
DEFAULT_BUNDLE_PREFIX = "lv3-control-bundle"
DEFAULT_INCLUDE_PATHS = [
    ".config-locations.yaml",
    ".gitea/workflows",
    ".repo-structure.yaml",
    "AGENTS.md",
    "Makefile",
    "README.md",
    "RELEASE.md",
    "VERSION",
    "ansible.cfg",
    "collections/ansible_collections/lv3/platform",
    "config",
    "docs/adr",
    "docs/runbooks",
    "docs/schema",
    "docs/workstreams",
    "inventory",
    "keys/gitea-release-bundle-cosign.pub",
    "playbooks",
    "pyproject.toml",
    "scripts",
    "workstreams.yaml",
]
DEFAULT_EXCLUDE_GLOBS = [
    "*.pyc",
    ".local/**",
    ".venv/**",
    ".worktrees/**",
    "__pycache__/**",
]
MANIFEST_FILENAME = "release-bundle-manifest.json"
SHA256_SUFFIX = ".sha256"
SIGNATURE_SUFFIX = ".sig"
SIGSTORE_BUNDLE_SUFFIX = ".sigstore.json"
ASSET_CONTENT_TYPE = "application/octet-stream"
SEMVER_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
DEFAULT_HTTP_TIMEOUT_SECONDS = 30.0
DEFAULT_ASSET_DOWNLOAD_WAIT_SECONDS = 600.0
TRANSIENT_DOWNLOAD_STATUS_CODES = {404, 408, 409, 423, 425, 429, 500, 502, 503, 504}
DEFAULT_RELEASE_BUNDLE_RETAIN_COUNT = 10


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    path: Path


@dataclass(frozen=True)
class ReleaseIdentity:
    asset_basename: str
    release_tag: str
    release_name: str
    prerelease: bool


def sanitize_ref_name(ref_name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", ref_name.strip().lower()).strip("-")
    return sanitized or "unknown-ref"


def resolve_input_path(path: Path) -> Path:
    return path if path.is_absolute() else (REPO_ROOT / path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_excluded(path: str, exclude_globs: list[str]) -> bool:
    pure_path = PurePosixPath(path)
    return any(pure_path.match(pattern) for pattern in exclude_globs)


def resolve_tracked_bundle_files(
    *,
    include_paths: list[str] | None = None,
    exclude_globs: list[str] | None = None,
) -> list[Path]:
    include_paths = list(include_paths or DEFAULT_INCLUDE_PATHS)
    exclude_globs = list(exclude_globs or DEFAULT_EXCLUDE_GLOBS)
    missing = [path for path in include_paths if not (REPO_ROOT / path).exists()]
    if missing:
        raise FileNotFoundError(f"missing bundle include path(s): {', '.join(sorted(missing))}")
    result = run_command(["git", "ls-files", "-z", "--", *include_paths], cwd=REPO_ROOT)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "failed to enumerate tracked bundle files")
    files: list[Path] = []
    seen: set[str] = set()
    for raw_path in result.stdout.split("\0"):
        if not raw_path:
            continue
        relative = raw_path.replace(os.sep, "/")
        if relative in seen or is_excluded(relative, exclude_globs):
            continue
        candidate = REPO_ROOT / raw_path
        if candidate.is_file():
            files.append(candidate)
            seen.add(relative)
    if not files:
        raise ValueError("bundle selection resolved to zero tracked files")
    return sorted(files)


def determine_release_identity(*, ref_name: str, ref_type: str, commit: str) -> ReleaseIdentity:
    short_commit = commit[:12]
    safe_ref = sanitize_ref_name(ref_name)
    safe_type = "tag" if ref_type == "tag" else "branch"
    asset_basename = f"{DEFAULT_BUNDLE_PREFIX}-{safe_type}-{safe_ref}-{short_commit}"
    release_tag = f"bundle-{safe_type}-{safe_ref}-{short_commit}"
    release_name = f"Signed control bundle for {ref_type} {ref_name} @ {short_commit}"
    prerelease = not (ref_type == "tag" or (ref_type == "branch" and ref_name == "main"))
    return ReleaseIdentity(
        asset_basename=asset_basename,
        release_tag=release_tag,
        release_name=release_name,
        prerelease=prerelease,
    )


def build_manifest(
    *,
    repository: str,
    ref_name: str,
    ref_type: str,
    commit: str,
    identity: ReleaseIdentity,
    files: list[Path],
    public_key_path: Path,
) -> dict[str, Any]:
    version_value = ""
    version_path = REPO_ROOT / "VERSION"
    if version_path.exists():
        version_value = version_path.read_text().strip()
    manifest_files = [
        {
            "path": str(file_path.relative_to(REPO_ROOT)).replace(os.sep, "/"),
            "sha256": sha256_file(file_path),
            "size_bytes": file_path.stat().st_size,
        }
        for file_path in files
    ]
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "repository": repository,
        "source": {
            "ref_name": ref_name,
            "ref_type": ref_type,
            "commit": commit,
            "repo_version": version_value if SEMVER_PATTERN.match(version_value) else "",
        },
        "bundle": {
            "asset_basename": identity.asset_basename,
            "release_tag": identity.release_tag,
            "release_name": identity.release_name,
            "prerelease": identity.prerelease,
            "optional_detached_signature_asset": f"{identity.asset_basename}.tar.gz{SIGNATURE_SUFFIX}",
            "sigstore_bundle_asset": f"{identity.asset_basename}.tar.gz{SIGSTORE_BUNDLE_SUFFIX}",
            "sha256_asset": f"{identity.asset_basename}.tar.gz{SHA256_SUFFIX}",
            "verification_public_key": str(public_key_path.relative_to(REPO_ROOT)).replace(os.sep, "/"),
        },
        "contents": {
            "file_count": len(manifest_files),
            "files": manifest_files,
        },
    }


def _tarinfo_for_path(relative_path: str, size: int, *, executable: bool) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name=relative_path)
    info.size = size
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mode = 0o755 if executable else 0o644
    return info


def write_bundle_archive(bundle_path: Path, *, files: list[Path], manifest: dict[str, Any]) -> None:
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with tarfile.open(bundle_path, "w:gz") as archive:
        for file_path in files:
            relative_path = str(file_path.relative_to(REPO_ROOT)).replace(os.sep, "/")
            file_bytes = file_path.read_bytes()
            executable = bool(file_path.stat().st_mode & 0o111)
            archive.addfile(
                _tarinfo_for_path(relative_path, len(file_bytes), executable=executable),
                io.BytesIO(file_bytes),
            )
        archive.addfile(
            _tarinfo_for_path(MANIFEST_FILENAME, len(manifest_bytes), executable=False),
            io.BytesIO(manifest_bytes),
        )


def write_sha256_sidecar(bundle_path: Path) -> Path:
    sha_path = bundle_path.with_name(f"{bundle_path.name}{SHA256_SUFFIX}")
    sha_path.write_text(f"{sha256_file(bundle_path)}  {bundle_path.name}\n")
    return sha_path


def load_api_token(explicit_token: str | None) -> str:
    if explicit_token:
        return explicit_token
    for env_name in ("GITEA_TOKEN", "GITHUB_TOKEN", "LV3_GITEA_TOKEN"):
        token = os.environ.get(env_name, "").strip()
        if token:
            return token
    raise ValueError("missing API token; pass --api-token or set GITEA_TOKEN")


def api_request(
    method: str,
    url: str,
    *,
    token: str | None,
    json_payload: dict[str, Any] | None = None,
    binary_payload: bytes | None = None,
    content_type: str = "application/json",
    accepted_statuses: tuple[int, ...] = (200, 201, 204),
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> tuple[int, bytes]:
    headers = {}
    if token:
        headers["Authorization"] = f"token {token}"
    payload = None
    if json_payload is not None:
        payload = json.dumps(json_payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif binary_payload is not None:
        payload = binary_payload
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=payload, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            body = response.read()
            status = response.getcode()
    except urllib.error.HTTPError as exc:
        body = exc.read()
        status = exc.code
        if status not in accepted_statuses:
            detail = body.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"{method} {url} failed with HTTP {status}: {detail}") from exc
        return status, body
    if status not in accepted_statuses:
        detail = body.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"{method} {url} failed with HTTP {status}: {detail}")
    return status, body


def repo_api_path(gitea_url: str, repository: str, suffix: str) -> str:
    owner, repo = repository.split("/", 1)
    return (
        f"{gitea_url.rstrip('/')}/api/v1/repos/"
        f"{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(repo, safe='')}/{suffix.lstrip('/')}"
    )


def fetch_release_by_tag(gitea_url: str, repository: str, token: str, release_tag: str) -> dict[str, Any] | None:
    status, payload = api_request(
        "GET",
        repo_api_path(
            gitea_url,
            repository,
            f"releases/tags/{urllib.parse.quote(release_tag, safe='')}",
        ),
        token=token,
        accepted_statuses=(200, 404),
    )
    if status == 404:
        return None
    return json.loads(payload.decode("utf-8"))


def fetch_release_asset_detail(
    *,
    gitea_url: str,
    repository: str,
    token: str,
    release_id: int,
    attachment_id: int,
) -> dict[str, Any]:
    _status, payload = api_request(
        "GET",
        repo_api_path(gitea_url, repository, f"releases/{release_id}/assets/{attachment_id}"),
        token=token,
    )
    return json.loads(payload.decode("utf-8"))


def parse_release_timestamp(release: dict[str, Any]) -> datetime:
    for field in ("published_at", "created_at"):
        value = release.get(field)
        if not value:
            continue
        try:
            if isinstance(value, str) and value.endswith("Z"):
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            if isinstance(value, str):
                return datetime.fromisoformat(value)
        except ValueError:
            continue
    return datetime.min.replace(tzinfo=UTC)


def list_releases(
    *,
    gitea_url: str,
    repository: str,
    token: str,
    page: int,
    limit: int,
) -> list[dict[str, Any]]:
    url = repo_api_path(gitea_url, repository, f"releases?limit={limit}&page={page}")
    _status, payload = api_request("GET", url, token=token, accepted_statuses=(200,))
    return json.loads(payload.decode("utf-8"))


def fetch_all_releases(*, gitea_url: str, repository: str, token: str) -> list[dict[str, Any]]:
    releases: list[dict[str, Any]] = []
    page = 1
    limit = 50
    while True:
        batch = list_releases(gitea_url=gitea_url, repository=repository, token=token, page=page, limit=limit)
        if not batch:
            break
        releases.extend(batch)
        if len(batch) < limit:
            break
        page += 1
    return releases


def delete_release(
    *,
    gitea_url: str,
    repository: str,
    token: str,
    release_id: int,
) -> None:
    api_request(
        "DELETE",
        repo_api_path(gitea_url, repository, f"releases/{release_id}"),
        token=token,
        accepted_statuses=(204, 200),
    )


def prune_release_bundles(
    *,
    gitea_url: str,
    repository: str,
    token: str,
    retain_count: int,
    exclude_tags: set[str],
) -> list[str]:
    if retain_count < 1:
        return []
    releases = fetch_all_releases(gitea_url=gitea_url, repository=repository, token=token)
    bundle_releases = [
        release for release in releases if str(release.get("tag_name", "")).startswith("bundle-")
    ]
    bundle_releases.sort(key=parse_release_timestamp, reverse=True)
    preserved = []
    removed = []
    for release in bundle_releases:
        tag_name = str(release.get("tag_name", ""))
        if tag_name in exclude_tags:
            preserved.append(tag_name)
            continue
        if len(preserved) < retain_count:
            preserved.append(tag_name)
            continue
        delete_release(
            gitea_url=gitea_url,
            repository=repository,
            token=token,
            release_id=int(release["id"]),
        )
        removed.append(tag_name)
    return removed


def ensure_release(
    *,
    gitea_url: str,
    repository: str,
    token: str,
    identity: ReleaseIdentity,
    target_commit: str,
    body: str,
) -> dict[str, Any]:
    release = fetch_release_by_tag(gitea_url, repository, token, identity.release_tag)
    if release is not None:
        return release
    _status, payload = api_request(
        "POST",
        repo_api_path(gitea_url, repository, "releases"),
        token=token,
        json_payload={
            "tag_name": identity.release_tag,
            "target_commitish": target_commit,
            "name": identity.release_name,
            "body": body,
            "draft": False,
            "prerelease": identity.prerelease,
        },
        accepted_statuses=(201,),
    )
    return json.loads(payload.decode("utf-8"))


def delete_release_asset(
    *,
    gitea_url: str,
    repository: str,
    token: str,
    release_id: int,
    attachment_id: int,
) -> None:
    api_request(
        "DELETE",
        repo_api_path(gitea_url, repository, f"releases/{release_id}/assets/{attachment_id}"),
        token=token,
    )


def upload_release_asset(
    *,
    gitea_url: str,
    repository: str,
    token: str,
    release_id: int,
    asset: ReleaseAsset,
) -> dict[str, Any]:
    upload_url = (
        repo_api_path(gitea_url, repository, f"releases/{release_id}/assets")
        + f"?name={urllib.parse.quote(asset.name, safe='')}"
    )
    _status, payload = api_request(
        "POST",
        upload_url,
        token=token,
        binary_payload=asset.path.read_bytes(),
        content_type=ASSET_CONTENT_TYPE,
        accepted_statuses=(201,),
    )
    return json.loads(payload.decode("utf-8"))


def publish_assets(
    *,
    gitea_url: str,
    repository: str,
    token: str,
    release: dict[str, Any],
    assets: list[ReleaseAsset],
) -> list[dict[str, Any]]:
    existing_assets = {asset["name"]: asset for asset in release.get("assets", [])}
    release_id = int(release["id"])
    for asset in assets:
        existing = existing_assets.get(asset.name)
        if existing is not None:
            delete_release_asset(
                gitea_url=gitea_url,
                repository=repository,
                token=token,
                release_id=release_id,
                attachment_id=int(existing["id"]),
            )
    uploaded = [
        upload_release_asset(
            gitea_url=gitea_url,
            repository=repository,
            token=token,
            release_id=release_id,
            asset=asset,
        )
        for asset in assets
    ]
    return uploaded


def ensure_cosign_installed(cosign_path: str) -> None:
    if shutil.which(cosign_path) is None:
        raise FileNotFoundError(f"cosign binary '{cosign_path}' was not found in PATH")


def sign_bundle(
    *,
    bundle_path: Path,
    signature_path: Path,
    sigstore_bundle_path: Path,
    private_key_path: Path,
    password_file: Path,
    cosign_path: str,
) -> None:
    ensure_cosign_installed(cosign_path)
    env = os.environ.copy()
    env["COSIGN_PASSWORD"] = password_file.read_text().strip()
    result = subprocess.run(  # noqa: S603
        [
            cosign_path,
            "sign-blob",
            "--key",
            str(private_key_path),
            "--output-signature",
            str(signature_path),
            "--bundle",
            str(sigstore_bundle_path),
            "--tlog-upload=false",
            str(bundle_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "cosign sign-blob failed")
    if not sigstore_bundle_path.exists():
        raise FileNotFoundError(f"cosign did not materialize the Sigstore bundle at {sigstore_bundle_path}")
    if not signature_path.exists():
        signature_stdout = result.stdout.strip()
        if signature_stdout:
            signature_path.write_text(signature_stdout + "\n")


def verify_bundle(
    *,
    bundle_path: Path,
    public_key_path: Path,
    cosign_path: str,
    signature_path: Path | None = None,
    sigstore_bundle_path: Path | None = None,
) -> None:
    ensure_cosign_installed(cosign_path)
    command = [
        cosign_path,
        "verify-blob",
        "--key",
        str(public_key_path),
    ]
    if sigstore_bundle_path is not None and sigstore_bundle_path.exists():
        command.extend(["--bundle", str(sigstore_bundle_path)])
    elif signature_path is not None and signature_path.exists():
        command.extend(["--signature", str(signature_path)])
    else:
        raise FileNotFoundError("missing Cosign verification material; expected a Sigstore bundle or detached signature")
    command.append(str(bundle_path))
    result = subprocess.run(  # noqa: S603
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "cosign verify-blob failed")


def extract_manifest(bundle_path: Path) -> dict[str, Any]:
    with tarfile.open(bundle_path, "r:gz") as archive:
        manifest_file = archive.extractfile(MANIFEST_FILENAME)
        if manifest_file is None:
            raise FileNotFoundError(f"{MANIFEST_FILENAME} was not found inside {bundle_path.name}")
        return json.loads(manifest_file.read().decode("utf-8"))


def is_retryable_download_error(error: RuntimeError) -> bool:
    status_match = re.search(r"HTTP (\d+)", str(error))
    status_code = int(status_match.group(1)) if status_match else None
    return status_code in TRANSIENT_DOWNLOAD_STATUS_CODES


def asset_download_urls(*, asset: dict[str, Any], asset_detail: dict[str, Any], gitea_url: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for source in (asset_detail, asset):
        for key in ("browser_download_url", "url"):
            value = source.get(key)
            if not isinstance(value, str) or not value:
                continue
            candidate = normalize_asset_url(value, gitea_url=gitea_url)
            path = urllib.parse.urlsplit(candidate).path
            if "/attachments/" not in path and "/releases/download/" not in path:
                continue
            if candidate in seen:
                continue
            candidates.append(candidate)
            seen.add(candidate)
    if not candidates:
        raise ValueError(f"release asset '{asset.get('name', 'unknown')}' does not expose a download URL")
    return candidates


def asset_download_retry_policy(max_wait_seconds: float) -> RetryPolicy:
    attempts = 1
    delay_seconds = 1.0
    elapsed_seconds = 0.0
    while elapsed_seconds < max_wait_seconds:
        attempts += 1
        elapsed_seconds += delay_seconds
        delay_seconds = min(delay_seconds * 2, 30.0)
    return RetryPolicy(
        max_attempts=attempts,
        base_delay_s=1.0,
        max_delay_s=30.0,
        multiplier=2.0,
        jitter=False,
        transient_max=0,
    )


def _download_asset_candidates_once(urls: list[str], *, token: str, destination: Path) -> None:
    last_error: Exception | None = None
    for url in urls:
        try:
            _status, payload = api_request("GET", url, token=token)
            destination.write_bytes(payload)
            return
        except urllib.error.URLError as exc:
            last_error = exc
        except RuntimeError as exc:
            if not is_retryable_download_error(exc):
                raise
            status_match = re.search(r"HTTP (\d+)", str(exc))
            status_code = int(status_match.group(1)) if status_match else 503
            last_error = PlatformRetryError(
                str(exc),
                code=f"http:{status_code}",
                retry_class=RetryClass.BACKOFF,
            )
            last_error.__cause__ = exc
    if last_error is None:
        raise RuntimeError("release asset download failed without reporting an error")
    raise last_error


def download_asset_candidates(
    urls: list[str],
    *,
    token: str,
    destination: Path,
    max_wait_seconds: float = DEFAULT_ASSET_DOWNLOAD_WAIT_SECONDS,
) -> None:
    if not urls:
        raise ValueError("expected at least one asset download URL")
    try:
        with_retry(
            lambda: _download_asset_candidates_once(urls, token=token, destination=destination),
            policy=asset_download_retry_policy(max_wait_seconds),
            error_context="release asset download",
            sleep_fn=time.sleep,
        )
    except MaxRetriesExceeded as exc:
        if exc.last_error is None:
            raise RuntimeError("release asset download failed without reporting an error") from exc
        if isinstance(exc.last_error, PlatformRetryError) and exc.last_error.__cause__ is not None:
            raise exc.last_error.__cause__ from exc.last_error.__cause__
        raise exc.last_error


def download_asset(
    url: str,
    *,
    token: str,
    destination: Path,
    max_wait_seconds: float = DEFAULT_ASSET_DOWNLOAD_WAIT_SECONDS,
) -> None:
    download_asset_candidates(
        [url],
        token=token,
        destination=destination,
        max_wait_seconds=max_wait_seconds,
    )


def normalize_asset_url(asset_url: str, *, gitea_url: str) -> str:
    parsed_asset = urllib.parse.urlsplit(asset_url)
    parsed_base = urllib.parse.urlsplit(gitea_url.rstrip("/"))
    if not parsed_asset.scheme or not parsed_asset.netloc:
        return asset_url
    if not parsed_base.scheme or not parsed_base.netloc:
        return asset_url
    if parsed_asset.scheme == parsed_base.scheme and parsed_asset.netloc == parsed_base.netloc:
        return asset_url
    return urllib.parse.urlunsplit(
        (parsed_base.scheme, parsed_base.netloc, parsed_asset.path, parsed_asset.query, parsed_asset.fragment)
    )


def fetch_release_assets_by_tag(
    *,
    gitea_url: str,
    repository: str,
    token: str,
    release_tag: str,
    destination_dir: Path,
) -> tuple[dict[str, Any], dict[str, Path]]:
    release = fetch_release_by_tag(gitea_url, repository, token, release_tag)
    if release is None:
        raise FileNotFoundError(f"release tag '{release_tag}' was not found in {repository}")
    release_id = int(release["id"])
    assets = release.get("assets", [])
    bundle_assets = [asset for asset in assets if str(asset.get("name", "")).endswith(".tar.gz")]
    if len(bundle_assets) != 1:
        raise ValueError(f"expected exactly one .tar.gz asset on release '{release_tag}', found {len(bundle_assets)}")
    bundle_asset = bundle_assets[0]
    bundle_name = str(bundle_asset["name"])
    required_names = {
        "bundle": bundle_name,
        "sha256": f"{bundle_name}{SHA256_SUFFIX}",
    }
    optional_names = {
        "signature": f"{bundle_name}{SIGNATURE_SUFFIX}",
        "sigstore_bundle": f"{bundle_name}{SIGSTORE_BUNDLE_SUFFIX}",
    }
    by_name = {str(asset["name"]): asset for asset in assets}
    missing = [name for name in required_names.values() if name not in by_name]
    if missing:
        raise FileNotFoundError(f"release '{release_tag}' is missing asset(s): {', '.join(missing)}")
    destination_dir.mkdir(parents=True, exist_ok=True)
    downloaded: dict[str, Path] = {}
    for label, asset_name in required_names.items():
        asset = by_name[asset_name]
        asset_detail = asset
        attachment_id = asset.get("id")
        if attachment_id is not None:
            asset_detail = fetch_release_asset_detail(
                gitea_url=gitea_url,
                repository=repository,
                token=token,
                release_id=release_id,
                attachment_id=int(attachment_id),
            )
        asset_path = destination_dir / asset_name
        download_asset_candidates(
            asset_download_urls(asset=asset, asset_detail=asset_detail, gitea_url=gitea_url),
            token=token,
            destination=asset_path,
        )
        downloaded[label] = asset_path
    for label, asset_name in optional_names.items():
        asset = by_name.get(asset_name)
        if asset is None:
            continue
        asset_detail = asset
        attachment_id = asset.get("id")
        if attachment_id is not None:
            asset_detail = fetch_release_asset_detail(
                gitea_url=gitea_url,
                repository=repository,
                token=token,
                release_id=release_id,
                attachment_id=int(attachment_id),
            )
        asset_path = destination_dir / asset_name
        download_asset_candidates(
            asset_download_urls(asset=asset, asset_detail=asset_detail, gitea_url=gitea_url),
            token=token,
            destination=asset_path,
        )
        downloaded[label] = asset_path
    if "sigstore_bundle" not in downloaded and "signature" not in downloaded:
        raise FileNotFoundError(
            f"release '{release_tag}' is missing verification material: expected {bundle_name}{SIGSTORE_BUNDLE_SUFFIX}"
            f" or {bundle_name}{SIGNATURE_SUFFIX}"
        )
    return release, downloaded


def init_signing_material(
    *,
    private_key_path: Path,
    password_path: Path,
    public_key_path: Path,
    cosign_docker_image: str,
    force: bool,
) -> dict[str, str]:
    for target in (private_key_path, password_path, public_key_path):
        if target.exists() and not force:
            raise FileExistsError(f"{target} already exists; pass --force to rotate the signing material")
    if shutil.which("docker") is None:
        raise FileNotFoundError("docker is required to bootstrap Cosign signing material")
    private_key_path.parent.mkdir(parents=True, exist_ok=True)
    password_path.parent.mkdir(parents=True, exist_ok=True)
    public_key_path.parent.mkdir(parents=True, exist_ok=True)
    password = token_urlsafe(32)
    with tempfile.TemporaryDirectory(prefix="lv3-cosign-init-") as temp_dir:
        env = os.environ.copy()
        env["COSIGN_PASSWORD"] = password
        temp_path = Path(temp_dir)
        command = [
            "docker",
            "run",
            "--rm",
            "-e",
            "COSIGN_PASSWORD",
            "-v",
            f"{temp_path}:/out",
            cosign_docker_image,
            "generate-key-pair",
            "--output-key-prefix",
            "/out/cosign",
        ]
        result = subprocess.run(  # noqa: S603
            command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "failed to generate Cosign key pair")
        generated_private_key = temp_path / "cosign.key"
        generated_public_key = temp_path / "cosign.pub"
        if not generated_private_key.exists() or not generated_public_key.exists():
            raise FileNotFoundError("cosign did not produce the expected key pair files")
        shutil.copyfile(generated_private_key, private_key_path)
        shutil.copyfile(generated_public_key, public_key_path)
    password_path.write_text(password + "\n")
    private_key_path.chmod(0o600)
    password_path.chmod(0o600)
    public_key_path.chmod(0o644)
    return {
        "private_key": str(private_key_path),
        "password_file": str(password_path),
        "public_key": str(public_key_path),
        "cosign_image": cosign_docker_image,
    }


def command_validate(args: argparse.Namespace) -> int:
    public_key_path = resolve_input_path(args.public_key_path)
    if not public_key_path.exists():
        raise FileNotFoundError(public_key_path)
    files = resolve_tracked_bundle_files()
    payload = {
        "status": "ok",
        "file_count": len(files),
        "public_key": str(public_key_path.relative_to(REPO_ROOT)).replace(os.sep, "/"),
        "includes": DEFAULT_INCLUDE_PATHS,
    }
    print(json.dumps(payload, indent=2))
    return 0


def command_init_signing(args: argparse.Namespace) -> int:
    payload = init_signing_material(
        private_key_path=resolve_input_path(args.private_key_path),
        password_path=resolve_input_path(args.password_file),
        public_key_path=resolve_input_path(args.public_key_path),
        cosign_docker_image=args.cosign_docker_image,
        force=args.force,
    )
    print(json.dumps(payload, indent=2))
    return 0


def build_release_bundle(args: argparse.Namespace) -> tuple[Path, Path, Path, Path, dict[str, Any], ReleaseIdentity]:
    public_key_path = resolve_input_path(args.public_key_path)
    private_key_path = resolve_input_path(args.private_key_path)
    password_file = resolve_input_path(args.password_file)
    identity = determine_release_identity(ref_name=args.ref_name, ref_type=args.ref_type, commit=args.commit)
    bundle_output_dir = resolve_input_path(args.output_dir)
    files = resolve_tracked_bundle_files()
    manifest = build_manifest(
        repository=args.repository,
        ref_name=args.ref_name,
        ref_type=args.ref_type,
        commit=args.commit,
        identity=identity,
        files=files,
        public_key_path=public_key_path,
    )
    bundle_path = bundle_output_dir / f"{identity.asset_basename}.tar.gz"
    signature_path = bundle_output_dir / f"{bundle_path.name}{SIGNATURE_SUFFIX}"
    sigstore_bundle_path = bundle_output_dir / f"{bundle_path.name}{SIGSTORE_BUNDLE_SUFFIX}"
    write_bundle_archive(bundle_path, files=files, manifest=manifest)
    sha256_path = write_sha256_sidecar(bundle_path)
    if args.sign:
        sign_bundle(
            bundle_path=bundle_path,
            signature_path=signature_path,
            sigstore_bundle_path=sigstore_bundle_path,
            private_key_path=private_key_path,
            password_file=password_file,
            cosign_path=args.cosign_path,
        )
    return bundle_path, signature_path, sigstore_bundle_path, sha256_path, manifest, identity


def command_build(args: argparse.Namespace) -> int:
    bundle_path, signature_path, sigstore_bundle_path, sha256_path, manifest, identity = build_release_bundle(args)
    payload = {
        "release_tag": identity.release_tag,
        "bundle_path": str(bundle_path),
        "signature_path": str(signature_path) if signature_path.exists() else "",
        "sigstore_bundle_path": str(sigstore_bundle_path) if sigstore_bundle_path.exists() else "",
        "sha256_path": str(sha256_path),
        "manifest_path": MANIFEST_FILENAME,
        "file_count": manifest["contents"]["file_count"],
    }
    print(json.dumps(payload, indent=2))
    return 0


def command_publish(args: argparse.Namespace) -> int:
    token = load_api_token(args.api_token)
    identity = determine_release_identity(ref_name=args.ref_name, ref_type=args.ref_type, commit=args.commit)
    removed_tags = prune_release_bundles(
        gitea_url=args.gitea_url,
        repository=args.repository,
        token=token,
        retain_count=args.retain_count,
        exclude_tags={identity.release_tag},
    )
    if removed_tags:
        print(json.dumps({"pruned_bundle_releases": removed_tags}, indent=2))
    bundle_path, signature_path, sigstore_bundle_path, sha256_path, manifest, identity = build_release_bundle(args)
    if not sigstore_bundle_path.exists():
        raise FileNotFoundError(f"missing Sigstore bundle at {sigstore_bundle_path}")
    release_body = (
        f"Signed control bundle for `{args.ref_type}` `{args.ref_name}` from commit `{args.commit[:12]}`.\n\n"
        f"- Repository: `{args.repository}`\n"
        f"- Bundle asset: `{bundle_path.name}`\n"
        f"- Sigstore bundle asset: `{sigstore_bundle_path.name}`\n"
        f"- Detached signature asset: `{signature_path.name}` when emitted by Cosign\n"
        f"- Verification key: `{manifest['bundle']['verification_public_key']}`\n"
        f"- File count: `{manifest['contents']['file_count']}`\n"
    )
    release = ensure_release(
        gitea_url=args.gitea_url,
        repository=args.repository,
        token=token,
        identity=identity,
        target_commit=args.commit,
        body=release_body,
    )
    uploaded_assets = publish_assets(
        gitea_url=args.gitea_url,
        repository=args.repository,
        token=token,
        release=release,
        assets=[
            ReleaseAsset(name=bundle_path.name, path=bundle_path),
            ReleaseAsset(name=sigstore_bundle_path.name, path=sigstore_bundle_path),
            ReleaseAsset(name=sha256_path.name, path=sha256_path),
        ]
        + ([ReleaseAsset(name=signature_path.name, path=signature_path)] if signature_path.exists() else []),
    )
    payload = {
        "release_tag": identity.release_tag,
        "release_name": identity.release_name,
        "prerelease": identity.prerelease,
        "bundle_path": str(bundle_path),
        "signature_path": str(signature_path) if signature_path.exists() else "",
        "sigstore_bundle_path": str(sigstore_bundle_path),
        "sha256_path": str(sha256_path),
        "release_url": release.get("html_url"),
        "uploaded_assets": [asset["name"] for asset in uploaded_assets],
    }
    print(json.dumps(payload, indent=2))
    return 0


def command_verify_release(args: argparse.Namespace) -> int:
    token = load_api_token(args.api_token)
    release, assets = fetch_release_assets_by_tag(
        gitea_url=args.gitea_url,
        repository=args.repository,
        token=token,
        release_tag=args.release_tag,
        destination_dir=resolve_input_path(args.output_dir),
    )
    verify_bundle(
        bundle_path=assets["bundle"],
        public_key_path=resolve_input_path(args.public_key_path),
        cosign_path=args.cosign_path,
        signature_path=assets.get("signature"),
        sigstore_bundle_path=assets.get("sigstore_bundle"),
    )
    recorded_sha = assets["sha256"].read_text().strip().split()[0]
    actual_sha = sha256_file(assets["bundle"])
    if recorded_sha != actual_sha:
        raise ValueError(
            f"bundle sha256 mismatch for {assets['bundle'].name}: expected {recorded_sha}, observed {actual_sha}"
        )
    manifest = extract_manifest(assets["bundle"])
    payload = {
        "release_tag": args.release_tag,
        "release_url": release.get("html_url"),
        "bundle_path": str(assets["bundle"]),
        "signature_path": str(assets["signature"]) if "signature" in assets else "",
        "sigstore_bundle_path": str(assets["sigstore_bundle"]) if "sigstore_bundle" in assets else "",
        "sha256_path": str(assets["sha256"]),
        "bundle_sha256": actual_sha,
        "manifest": {
            "repository": manifest["repository"],
            "ref_name": manifest["source"]["ref_name"],
            "ref_type": manifest["source"]["ref_type"],
            "commit": manifest["source"]["commit"],
            "file_count": manifest["contents"]["file_count"],
        },
    }
    print(json.dumps(payload, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build, sign, publish, and verify ADR 0233 signed release bundles."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate the bundle selection and signing inputs.")
    validate_parser.add_argument(
        "--public-key-path",
        type=Path,
        default=DEFAULT_PUBLIC_KEY_PATH,
    )
    validate_parser.set_defaults(func=command_validate)

    init_parser = subparsers.add_parser(
        "init-signing",
        help="Generate the local Cosign key pair and password, and write the public key into the repo.",
    )
    init_parser.add_argument("--private-key-path", type=Path, default=DEFAULT_PRIVATE_KEY_PATH)
    init_parser.add_argument("--password-file", type=Path, default=DEFAULT_PASSWORD_PATH)
    init_parser.add_argument("--public-key-path", type=Path, default=DEFAULT_PUBLIC_KEY_PATH)
    init_parser.add_argument("--cosign-docker-image", default=DEFAULT_COSIGN_DOCKER_IMAGE)
    init_parser.add_argument("--force", action="store_true", help="Rotate existing signing material in place.")
    init_parser.set_defaults(func=command_init_signing)

    for name, help_text, func in (
        ("build", "Build a bundle locally, with optional signing.", command_build),
        ("publish", "Build, sign, and publish a bundle to a Gitea Release.", command_publish),
    ):
        command_parser = subparsers.add_parser(name, help=help_text)
        command_parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "ops/proxmox_florin_server"))
        command_parser.add_argument("--ref-name", default=os.environ.get("GITHUB_REF_NAME", "main"))
        command_parser.add_argument("--ref-type", default=os.environ.get("GITHUB_REF_TYPE", "branch"))
        command_parser.add_argument("--commit", default=os.environ.get("GITHUB_SHA", "unknown"))
        command_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
        command_parser.add_argument("--public-key-path", type=Path, default=DEFAULT_PUBLIC_KEY_PATH)
        command_parser.add_argument("--private-key-path", type=Path, default=DEFAULT_PRIVATE_KEY_PATH)
        command_parser.add_argument("--password-file", type=Path, default=DEFAULT_PASSWORD_PATH)
        command_parser.add_argument("--cosign-path", default="cosign")
        if name == "build":
            command_parser.add_argument("--sign", action="store_true")
            command_parser.set_defaults(sign=False)
        else:
            command_parser.set_defaults(sign=True)
        if name == "publish":
            command_parser.add_argument("--gitea-url", default=os.environ.get("GITHUB_SERVER_URL", "http://100.64.0.1:3009"))
            command_parser.add_argument("--api-token")
            command_parser.add_argument("--retain-count", type=int, default=DEFAULT_RELEASE_BUNDLE_RETAIN_COUNT)
        command_parser.set_defaults(func=func)

    verify_parser = subparsers.add_parser(
        "verify-release",
        help="Download a published bundle release from Gitea and verify it with Cosign.",
    )
    verify_parser.add_argument("--gitea-url", default=os.environ.get("GITHUB_SERVER_URL", "http://100.64.0.1:3009"))
    verify_parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "ops/proxmox_florin_server"))
    verify_parser.add_argument("--release-tag", required=True)
    verify_parser.add_argument("--api-token")
    verify_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    verify_parser.add_argument("--public-key-path", type=Path, default=DEFAULT_PUBLIC_KEY_PATH)
    verify_parser.add_argument("--cosign-path", default="cosign")
    verify_parser.set_defaults(func=command_verify_release)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("release-bundle", exc)


if __name__ == "__main__":
    raise SystemExit(main())
