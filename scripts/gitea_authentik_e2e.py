#!/usr/bin/env python3
"""Provision a local-only test password or verify Gitea's Authentik OIDC flow."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
existing_platform = sys.modules.get("platform")
if existing_platform is not None and not hasattr(existing_platform, "__path__"):
    del sys.modules["platform"]

from platform.repo import local_overlay_root


DEFAULT_LOCAL_ROOT = local_overlay_root(REPO_ROOT)
DEFAULT_USERNAME = "gitea-e2e"
DEFAULT_PASSWORD_FILE = DEFAULT_LOCAL_ROOT / "authentik" / "gitea-e2e-initial-password.txt"
DEFAULT_CA_FILE = DEFAULT_LOCAL_ROOT / "step-ca" / "certs" / "root_ca.crt"
PROVIDER_SOURCE = "Authentik"


class VerificationError(RuntimeError):
    """Raised when safe password or browser verification cannot continue."""


def read_private_file(path: Path, *, label: str) -> str:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        raise VerificationError(f"{label} file is missing") from None
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise VerificationError(f"{label} must be a regular file, not a symlink")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise VerificationError(f"{label} file permissions must exclude group and other access")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise VerificationError(f"{label} file is empty")
    return value


def prepare_password_file(path: Path = DEFAULT_PASSWORD_FILE) -> bool:
    """Create an initial password once; never reveal or replace an existing one."""
    parent = path.parent
    if parent.exists() and (not parent.is_dir() or parent.is_symlink()):
        raise VerificationError("test-password parent must be a real directory")
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    password = secrets.token_urlsafe(36)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        read_private_file(path, label="test password")
        return False
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(password + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return True


def authenticated_user(page: Any, *, username: str) -> dict[str, Any]:
    """Verify the visible browser identity and read the public profile's admin flag.

    Gitea does not accept its browser cookie on ``/api/v1/user``. The signed-in
    account is therefore read from the visible user-menu label, while the public
    user endpoint supplies the minimal profile fields needed for the admin check.
    """
    result = page.evaluate(
        """async (expectedLogin) => {
          const identityLabels = Array.from(document.querySelectorAll('.gt-ellipsis'))
            .filter((node) => node.getClientRects().length > 0
              && node.textContent.trim() === expectedLogin);
          const sessionLogin = identityLabels.length === 1
            ? identityLabels[0].textContent.trim()
            : '';
          if (!sessionLogin) return { status: 401 };
          const response = await fetch(`/api/v1/users/${encodeURIComponent(sessionLogin)}`, {
            credentials: 'same-origin'
          });
          if (!response.ok) return { status: response.status, session_login: sessionLogin };
          const user = await response.json();
          return {
            status: response.status,
            login: user.login,
            is_admin: user.is_admin,
            session_login: sessionLogin
          };
        }""",
        username,
    )
    if not isinstance(result, dict):
        raise VerificationError("Gitea did not return a valid current-user response")
    if result.get("status") != 200:
        raise VerificationError("Gitea browser session is not authenticated")
    return result


def verify_authenticated_user(page: Any, *, username: str) -> None:
    # The OIDC callback can finish before Gitea's client-side header has rendered.
    # Wait for the exact expected visible identity before checking its profile.
    try:
        page.wait_for_function(
            """expectedLogin => Array.from(document.querySelectorAll('.gt-ellipsis'))
              .filter((node) => node.getClientRects().length > 0
                && node.textContent.trim() === expectedLogin).length === 1""",
            arg=username,
            timeout=10_000,
        )
    except Exception as exc:
        current = urlparse(page.url)
        title = str(page.title() or "")[:100]
        login_controls = page.locator('form[action*="/user/login"], input[name="user_name"]').count()
        expected_label_visible = page.evaluate(
            """expectedLogin => Array.from(document.querySelectorAll('.gt-ellipsis'))
              .some((node) => node.getClientRects().length > 0
                && node.textContent.trim() === expectedLogin)""",
            username,
        )
        raise VerificationError(
            "Gitea did not display an authenticated user menu "
            f"(path={current.path or '/'}, title={title!r}, login_controls={login_controls > 0}, "
            f"expected_label_visible={expected_label_visible}, wait_error={type(exc).__name__})"
        ) from None
    result = authenticated_user(page, username=username)
    if result.get("session_login") != username:
        raise VerificationError("Gitea browser session is not authenticated as the requested account")
    if result.get("login") != username:
        raise VerificationError("Gitea authenticated a different account than the requested test identity")
    if result.get("is_admin") is not False:
        raise VerificationError("Gitea test identity is not confirmed as a non-admin account")


def _import_ca(profile: Path, ca_file: Path) -> None:
    if not ca_file.is_file() or ca_file.is_symlink():
        raise VerificationError("explicit internal CA root must be a regular non-symlink file")
    certutil = shutil.which("certutil")
    if not certutil:
        raise VerificationError("NSS certutil is required to trust the internal CA in a temporary Firefox profile")
    database = f"sql:{profile}"
    try:
        subprocess.run(
            [certutil, "-N", "--empty-password", "-d", database],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
        subprocess.run(
            [
                certutil,
                "-A",
                "-n",
                "ServerClaw Gitea E2E CA",
                "-t",
                "C,,",
                "-i",
                str(ca_file),
                "-d",
                database,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        raise VerificationError("internal CA could not be installed into the temporary browser profile") from None


def _playwright_api():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise VerificationError("Install Playwright with `uv run --with playwright`") from exc
    return sync_playwright, PlaywrightTimeoutError


def complete_authentik_login(
    page: Any,
    *,
    username: str,
    password: str,
    timeout_ms: int,
    playwright_timeout_error: type[BaseException],
) -> None:
    from session_logout_verify import authenticate_authentik_session

    try:
        authenticate_authentik_session(
            page,
            username=username,
            password=password,
            timeout_milliseconds=timeout_ms,
            playwright_timeout_error=playwright_timeout_error,
        )
    except Exception:
        # The shared helper includes the current URL in some failures; that URL
        # may contain OAuth state or authorization codes.
        raise VerificationError(
            "Authentik browser login or callback failed; detailed diagnostics were redacted"
        ) from None


def verify_oidc_flow(
    *,
    platform_domain: str,
    username: str,
    password: str,
    root_ca_file: Path | None,
    timeout_ms: int = 30_000,
    headless: bool = True,
) -> dict[str, Any]:
    """Complete Authentik sign-in in a fresh browser and prove Gitea grants no admin role."""
    gitea_url = f"https://git.{platform_domain}"
    identity_url = f"https://id.{platform_domain}"
    parsed_gitea = urlparse(gitea_url)
    parsed_identity = urlparse(identity_url)
    if parsed_gitea.scheme != "https" or parsed_identity.scheme != "https":
        raise VerificationError("the Gitea and Authentik browser endpoints must use HTTPS")

    sync_playwright, playwright_timeout_error = _playwright_api()
    temporary_profile: tempfile.TemporaryDirectory[str] | None = None
    browser = None
    context = None
    try:
        with sync_playwright() as playwright:
            if root_ca_file is None:
                browser = playwright.chromium.launch(headless=headless)
                context = browser.new_context()
                ca_scope = "system trust store"
            else:
                temporary_profile = tempfile.TemporaryDirectory(prefix="gitea-authentik-e2e-")
                profile = Path(temporary_profile.name) / "firefox-profile"
                profile.mkdir(mode=0o700)
                _import_ca(profile, root_ca_file)
                context = playwright.firefox.launch_persistent_context(
                    user_data_dir=str(profile),
                    headless=headless,
                )
                ca_scope = "temporary Firefox profile"

            page = context.new_page()
            try:
                page.goto(
                    f"{gitea_url}/user/oauth2/{PROVIDER_SOURCE}",
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
                current_host = (urlparse(page.url).hostname or "").lower()
                if current_host != parsed_identity.hostname:
                    raise VerificationError("Gitea did not direct a fresh session to Authentik")

                complete_authentik_login(
                    page,
                    username=username,
                    password=password,
                    timeout_ms=timeout_ms,
                    playwright_timeout_error=playwright_timeout_error,
                )
                if (urlparse(page.url).hostname or "").lower() != parsed_gitea.hostname:
                    raise VerificationError("Authentik did not return the browser to Gitea")
                verify_authenticated_user(page, username=username)
            except VerificationError:
                raise
            except Exception:
                # Browser error text can contain OAuth state, authorization codes,
                # or user input. Keep diagnostics deliberately non-sensitive.
                raise VerificationError(
                    "browser OIDC verification failed; detailed browser diagnostics were redacted"
                ) from None

            return {
                "status": "ok",
                "service": "gitea",
                "provider": PROVIDER_SOURCE,
                "username": username,
                "is_admin": False,
                "tls_validation": "enabled",
                "ca_trust_scope": ca_scope,
            }
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if temporary_profile is not None:
            temporary_profile.cleanup()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare-password", help="create a local-only test password once")
    prepare.add_argument("--password-file", type=Path, default=DEFAULT_PASSWORD_FILE)

    verify = subparsers.add_parser("verify", help="complete a browser OIDC login and assert non-admin access")
    verify.add_argument("--platform-domain", required=True)
    verify.add_argument("--username", default=DEFAULT_USERNAME)
    verify.add_argument("--password-file", type=Path, default=DEFAULT_PASSWORD_FILE)
    verify.add_argument(
        "--root-ca-file",
        type=Path,
        default=DEFAULT_CA_FILE if DEFAULT_CA_FILE.is_file() else None,
        help="optional private root CA; trusted only in a temporary Firefox profile",
    )
    verify.add_argument("--timeout-ms", type=int, default=30_000)
    headless = verify.add_mutually_exclusive_group()
    headless.add_argument("--headed", action="store_false", dest="headless", default=True)
    headless.add_argument("--headless", action="store_true", dest="headless")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "prepare-password":
            created = prepare_password_file(args.password_file)
            print(json.dumps({"status": "ready", "created": created, "secret_printed": False}, sort_keys=True))
            return 0

        password = read_private_file(args.password_file, label="test password")
        if args.timeout_ms < 1_000:
            raise VerificationError("timeout must be at least 1000 milliseconds")
        result = verify_oidc_flow(
            platform_domain=args.platform_domain,
            username=args.username,
            password=password,
            root_ca_file=args.root_ca_file,
            timeout_ms=args.timeout_ms,
            headless=args.headless,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, VerificationError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
