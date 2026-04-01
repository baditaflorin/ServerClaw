#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8").strip()


def write_secret(path: str, value: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{value}\n", encoding="utf-8")
    target.chmod(0o600)


def request_json(
    *,
    base_url: str,
    path: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: Any | None = None,
    expected_status: tuple[int, ...] = (200,),
    timeout: int = 30,
) -> tuple[int, dict[str, str], Any]:
    url = base_url.rstrip("/") + path
    payload = None
    request_headers = dict(headers or {})
    if body is not None:
      payload = json.dumps(body).encode("utf-8")
      request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=payload, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            data = json.loads(raw.decode("utf-8")) if raw else None
            status = response.status
            headers_out = {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        data = json.loads(raw.decode("utf-8")) if raw else None
        status = exc.code
        headers_out = {key.lower(): value for key, value in exc.headers.items()}
        if status not in expected_status:
            raise RuntimeError(f"{method} {url} returned {status}: {raw.decode('utf-8', errors='replace')}") from exc
        return status, headers_out, data
    if status not in expected_status:
        raise RuntimeError(f"{method} {url} returned unexpected status {status}")
    return status, headers_out, data


def basic_headers(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def bearer_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def apikey_headers(api_key: str) -> dict[str, str]:
    return {"X-SFTPGO-API-KEY": api_key}


def get_token(base_url: str, username: str, password: str) -> str:
    _, _, payload = request_json(
        base_url=base_url,
        path="/api/v2/token",
        headers=basic_headers(username, password),
        expected_status=(200,),
    )
    if not isinstance(payload, dict) or "access_token" not in payload:
        raise RuntimeError("SFTPGo token response did not include access_token")
    return str(payload["access_token"])


def get_optional_json(base_url: str, path: str, headers: dict[str, str]) -> Any | None:
    status, _, payload = request_json(
        base_url=base_url,
        path=path,
        headers=headers,
        expected_status=(200, 404),
    )
    return None if status == 404 else payload


def normalize_permissions(value: dict[str, list[str]] | None) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    return {key: sorted(str(item) for item in items) for key, items in value.items()}


def ensure_allow_api_key_auth(base_url: str, token: str) -> bool:
    headers = bearer_headers(token)
    _, _, profile = request_json(base_url=base_url, path="/api/v2/admin/profile", headers=headers)
    if not isinstance(profile, dict):
        raise RuntimeError("SFTPGo admin profile response must be an object")
    if profile.get("allow_api_key_auth") is True:
        return False
    profile["allow_api_key_auth"] = True
    request_json(
        base_url=base_url,
        path="/api/v2/admin/profile",
        method="PUT",
        headers=headers,
        body=profile,
        expected_status=(200,),
    )
    return True


def ensure_admin(
    *,
    base_url: str,
    token: str,
    username: str,
    password: str,
    email: str,
    description: str,
) -> bool:
    headers = bearer_headers(token)
    payload = {
        "status": 1,
        "username": username,
        "password": password,
        "email": email,
        "description": description,
        "permissions": ["*"],
    }
    existing = get_optional_json(
        base_url,
        f"/api/v2/admins/{urllib.parse.quote(username, safe='')}",
        headers,
    )
    if existing is None:
        request_json(
            base_url=base_url,
            path="/api/v2/admins",
            method="POST",
            headers=headers,
            body=payload,
            expected_status=(201,),
        )
        return True
    if not isinstance(existing, dict):
        raise RuntimeError("SFTPGo admin lookup response must be an object")
    desired_fields = {
        "status": 1,
        "email": email,
        "description": description,
        "permissions": ["*"],
    }
    current_fields = {
        "status": existing.get("status"),
        "email": existing.get("email", ""),
        "description": existing.get("description", ""),
        "permissions": sorted(existing.get("permissions", [])),
    }
    if current_fields == desired_fields:
        return False
    request_json(
        base_url=base_url,
        path=f"/api/v2/admins/{urllib.parse.quote(username, safe='')}",
        method="PUT",
        headers=headers,
        body=payload,
        expected_status=(200,),
    )
    return True


def ensure_api_key(
    *,
    base_url: str,
    token: str,
    key_name: str,
    api_key_file: str,
    admin_username: str,
    description: str,
) -> tuple[str, bool]:
    headers = bearer_headers(token)
    _, _, keys = request_json(base_url=base_url, path="/api/v2/apikeys", headers=headers)
    if not isinstance(keys, list):
        raise RuntimeError("SFTPGo API key list must be an array")

    matching = [
        key
        for key in keys
        if isinstance(key, dict)
        and key.get("name") == key_name
        and key.get("admin") == admin_username
        and key.get("scope") == 1
    ]
    local_key_path = Path(api_key_file)
    local_key = local_key_path.read_text(encoding="utf-8").strip() if local_key_path.exists() else ""

    recreate = False
    if len(matching) > 1:
        recreate = True
    elif matching and not local_key:
        recreate = True
    elif not matching:
        recreate = True

    if recreate:
        for item in matching:
            request_json(
                base_url=base_url,
                path=f"/api/v2/apikeys/{urllib.parse.quote(str(item['id']), safe='')}",
                method="DELETE",
                headers=headers,
                expected_status=(200,),
            )
        _, _, created = request_json(
            base_url=base_url,
            path="/api/v2/apikeys",
            method="POST",
            headers=headers,
            body={
                "name": key_name,
                "scope": 1,
                "admin": admin_username,
                "description": description,
            },
            expected_status=(201,),
        )
        if not isinstance(created, dict) or "key" not in created:
            raise RuntimeError("SFTPGo API key creation response did not include the generated key")
        generated_key = str(created["key"])
        write_secret(api_key_file, generated_key)
        return generated_key, True

    return local_key, False


def ensure_user(
    *,
    base_url: str,
    api_key: str,
    username: str,
    password: str,
    public_key: str,
    home_dir: str,
    quota_size: int,
    quota_files: int,
    description: str,
) -> bool:
    headers = apikey_headers(api_key)
    payload = {
        "status": 1,
        "username": username,
        "password": password,
        "public_keys": [public_key],
        "home_dir": home_dir,
        "permissions": {"/": ["*"]},
        "quota_size": quota_size,
        "quota_files": quota_files,
        "description": description,
    }
    existing = get_optional_json(
        base_url,
        f"/api/v2/users/{urllib.parse.quote(username, safe='')}",
        headers,
    )
    if existing is None:
        request_json(
            base_url=base_url,
            path="/api/v2/users",
            method="POST",
            headers=headers,
            body=payload,
            expected_status=(201,),
        )
        return True
    if not isinstance(existing, dict):
        raise RuntimeError("SFTPGo user lookup response must be an object")

    desired_fields = {
        "status": 1,
        "home_dir": home_dir,
        "quota_size": quota_size,
        "quota_files": quota_files,
        "description": description,
        "public_keys": sorted([public_key]),
        "permissions": {"/": ["*"]},
    }
    current_fields = {
        "status": existing.get("status"),
        "home_dir": existing.get("home_dir", ""),
        "quota_size": existing.get("quota_size"),
        "quota_files": existing.get("quota_files"),
        "description": existing.get("description", ""),
        "public_keys": sorted(existing.get("public_keys", [])),
        "permissions": normalize_permissions(existing.get("permissions")),
    }
    if current_fields == desired_fields:
        return False

    request_json(
        base_url=base_url,
        path=f"/api/v2/users/{urllib.parse.quote(username, safe='')}",
        method="PUT",
        headers=headers,
        body=payload,
        expected_status=(200,),
    )
    return True


def command_bootstrap(args: argparse.Namespace) -> int:
    bootstrap_password = read_text(args.bootstrap_admin_password_file)
    oidc_admin_password = read_text(args.oidc_admin_password_file)
    smoke_user_password = read_text(args.smoke_user_password_file)
    smoke_user_public_key = read_text(args.smoke_user_public_key_file)

    token = get_token(args.base_url, args.bootstrap_admin_username, bootstrap_password)
    profile_changed = ensure_allow_api_key_auth(args.base_url, token)
    oidc_admin_changed = ensure_admin(
        base_url=args.base_url,
        token=token,
        username=args.oidc_admin_username,
        password=oidc_admin_password,
        email=args.oidc_admin_email,
        description="Repo-managed Keycloak-backed SFTPGo administrator",
    )
    api_key_value, api_key_changed = ensure_api_key(
        base_url=args.base_url,
        token=token,
        key_name=args.api_key_name,
        api_key_file=args.api_key_file,
        admin_username=args.bootstrap_admin_username,
        description="Repo-managed SFTPGo REST provisioning key",
    )
    smoke_user_changed = ensure_user(
        base_url=args.base_url,
        api_key=api_key_value,
        username=args.smoke_user_username,
        password=smoke_user_password,
        public_key=smoke_user_public_key,
        home_dir=args.smoke_user_home_dir,
        quota_size=args.smoke_user_quota_bytes,
        quota_files=args.smoke_user_quota_files,
        description="Repo-managed smoke file-transfer identity",
    )
    report = {
        "changed": any([profile_changed, oidc_admin_changed, api_key_changed, smoke_user_changed]),
        "profile_changed": profile_changed,
        "oidc_admin_changed": oidc_admin_changed,
        "api_key_changed": api_key_changed,
        "smoke_user_changed": smoke_user_changed,
        "bootstrap_admin_username": args.bootstrap_admin_username,
        "oidc_admin_username": args.oidc_admin_username,
        "api_key_name": args.api_key_name,
        "smoke_user_username": args.smoke_user_username,
    }
    if args.report_file:
        Path(args.report_file).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    json.dump(report, sys.stdout)
    sys.stdout.write("\n")
    return 0


def command_verify(args: argparse.Namespace) -> int:
    api_key = read_text(args.api_key_file)
    headers = apikey_headers(api_key)
    admin = get_optional_json(
        args.base_url,
        f"/api/v2/admins/{urllib.parse.quote(args.expected_admin, safe='')}",
        headers,
    )
    user = get_optional_json(
        args.base_url,
        f"/api/v2/users/{urllib.parse.quote(args.expected_user, safe='')}",
        headers,
    )
    if admin is None:
        raise RuntimeError(f"Expected admin {args.expected_admin!r} was not found")
    if user is None:
        raise RuntimeError(f"Expected user {args.expected_user!r} was not found")
    report = {
        "changed": False,
        "api_key_authenticated": True,
        "admin": args.expected_admin,
        "user": args.expected_user,
    }
    json.dump(report, sys.stdout)
    sys.stdout.write("\n")
    return 0


def command_smoke_webdav(args: argparse.Namespace) -> int:
    password = read_text(args.password_file)
    auth = base64.b64encode(f"{args.username}:{password}".encode("utf-8")).decode("ascii")
    headers = {"Authorization": f"Basic {auth}"}
    remote_path = "/" + args.remote_path.lstrip("/")
    remote_url = args.base_url.rstrip("/") + urllib.parse.quote(remote_path)
    request_headers = dict(headers)
    request_headers["Content-Type"] = "application/octet-stream"
    put_request = urllib.request.Request(
        remote_url,
        data=args.content.encode("utf-8"),
        headers=request_headers,
        method="PUT",
    )
    try:
        with urllib.request.urlopen(put_request, timeout=30) as response:
            if response.status not in (200, 201, 204):
                raise RuntimeError(f"WebDAV PUT returned {response.status}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"WebDAV PUT failed with {exc.code}: {exc.read().decode('utf-8', errors='replace')}") from exc

    get_request = urllib.request.Request(remote_url, headers=headers, method="GET")
    with urllib.request.urlopen(get_request, timeout=30) as response:
        downloaded = response.read().decode("utf-8")
    if downloaded != args.content:
        raise RuntimeError("Downloaded WebDAV content did not match the uploaded payload")

    delete_request = urllib.request.Request(remote_url, headers=headers, method="DELETE")
    with urllib.request.urlopen(delete_request, timeout=30) as response:
        if response.status not in (200, 202, 204):
            raise RuntimeError(f"WebDAV DELETE returned {response.status}")

    json.dump(
        {
            "changed": False,
            "protocol": "webdav",
            "remote_path": remote_path,
            "bytes": len(args.content.encode("utf-8")),
        },
        sys.stdout,
    )
    sys.stdout.write("\n")
    return 0


def command_smoke_sftp(args: argparse.Namespace) -> int:
    content = args.content
    with tempfile.TemporaryDirectory(prefix="sftpgo-smoke-") as tmpdir:
        temp_dir = Path(tmpdir)
        upload_path = temp_dir / "upload.txt"
        download_path = temp_dir / "download.txt"
        upload_path.write_text(content, encoding="utf-8")
        batch = "\n".join(
            [
                f"put {upload_path} {args.remote_path}",
                f"get {args.remote_path} {download_path}",
                f"rm {args.remote_path}",
                "",
            ]
        )
        command = [
            "sftp",
            "-b",
            "-",
            "-oBatchMode=yes",
            "-oIdentitiesOnly=yes",
            "-oStrictHostKeyChecking=no",
            "-oUserKnownHostsFile=/dev/null",
            "-P",
            str(args.port),
            "-i",
            args.identity_file,
            f"{args.username}@{args.host}",
        ]
        subprocess.run(
            command,
            input=batch,
            text=True,
            check=True,
            capture_output=True,
        )
        downloaded = download_path.read_text(encoding="utf-8")
        if downloaded != content:
            raise RuntimeError("Downloaded SFTP content did not match the uploaded payload")

    json.dump(
        {
            "changed": False,
            "protocol": "sftp",
            "remote_path": args.remote_path,
            "bytes": len(content.encode("utf-8")),
        },
        sys.stdout,
    )
    sys.stdout.write("\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap and verify the repo-managed SFTPGo control plane.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap")
    bootstrap.add_argument("--base-url", required=True)
    bootstrap.add_argument("--bootstrap-admin-username", required=True)
    bootstrap.add_argument("--bootstrap-admin-password-file", required=True)
    bootstrap.add_argument("--api-key-name", required=True)
    bootstrap.add_argument("--api-key-file", required=True)
    bootstrap.add_argument("--oidc-admin-username", required=True)
    bootstrap.add_argument("--oidc-admin-email", required=True)
    bootstrap.add_argument("--oidc-admin-password-file", required=True)
    bootstrap.add_argument("--smoke-user-username", required=True)
    bootstrap.add_argument("--smoke-user-password-file", required=True)
    bootstrap.add_argument("--smoke-user-public-key-file", required=True)
    bootstrap.add_argument("--smoke-user-home-dir", required=True)
    bootstrap.add_argument("--smoke-user-quota-bytes", required=True, type=int)
    bootstrap.add_argument("--smoke-user-quota-files", required=True, type=int)
    bootstrap.add_argument("--report-file")
    bootstrap.set_defaults(func=command_bootstrap)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--base-url", required=True)
    verify.add_argument("--api-key-file", required=True)
    verify.add_argument("--expected-admin", required=True)
    verify.add_argument("--expected-user", required=True)
    verify.set_defaults(func=command_verify)

    smoke_webdav = subparsers.add_parser("smoke-webdav")
    smoke_webdav.add_argument("--base-url", required=True)
    smoke_webdav.add_argument("--username", required=True)
    smoke_webdav.add_argument("--password-file", required=True)
    smoke_webdav.add_argument("--remote-path", required=True)
    smoke_webdav.add_argument("--content", required=True)
    smoke_webdav.set_defaults(func=command_smoke_webdav)

    smoke_sftp = subparsers.add_parser("smoke-sftp")
    smoke_sftp.add_argument("--host", required=True)
    smoke_sftp.add_argument("--port", required=True, type=int)
    smoke_sftp.add_argument("--username", required=True)
    smoke_sftp.add_argument("--identity-file", required=True)
    smoke_sftp.add_argument("--remote-path", required=True)
    smoke_sftp.add_argument("--content", required=True)
    smoke_sftp.set_defaults(func=command_smoke_sftp)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
