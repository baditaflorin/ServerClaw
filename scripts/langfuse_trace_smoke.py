#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
import uuid
from pathlib import Path

import requests


def _load_observability_helpers(repo_root: Path):
    module_path = repo_root / "platform" / "llm" / "observability.py"
    spec = importlib.util.spec_from_file_location("lv3_langfuse_observability", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Langfuse observability helpers from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.dump_json, module.load_langfuse_config, module.trace_url


def _build_session(base_url: str, email: str, password: str) -> requests.Session:
    session = requests.Session()
    csrf = session.get(f"{base_url}/api/auth/csrf", timeout=30)
    csrf.raise_for_status()
    csrf_token = csrf.json()["csrfToken"]
    response = session.post(
        f"{base_url}/api/auth/callback/credentials",
        data={
            "csrfToken": csrf_token,
            "email": email,
            "password": password,
            "callbackUrl": f"{base_url}/",
            "json": "true",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("ok") is True:
        return session
    if payload.get("url") and session.cookies:
        return session
    if payload.get("url") and "authjs.session-token" in response.headers.get("set-cookie", ""):
        return session
    if payload.get("ok") is not True:
        raise RuntimeError(f"Langfuse credential sign-in failed: {payload!r}")
    return session


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit and verify one Langfuse smoke trace.")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--base-url", help="Override the Langfuse base URL.")
    parser.add_argument("--trace-id", help="Use an explicit trace id.")
    parser.add_argument("--project-id", help="Override the Langfuse project id.")
    parser.add_argument("--bootstrap-email", help="Verify the trace page through the HTML UI with this email.")
    parser.add_argument("--bootstrap-password-file", type=Path, help="Password file used for UI verification.")
    parser.add_argument("--timeout-seconds", type=int, default=60)
    args = parser.parse_args()

    try:
        dump_json, load_langfuse_config, trace_url = _load_observability_helpers(args.repo_root)
        config = load_langfuse_config(args.repo_root)
        base_url = (args.base_url or config.host).rstrip("/")
        project_id = args.project_id or config.project_id or "lv3-agent-observability"
        trace_id = args.trace_id or uuid.uuid4().hex

        try:
            from langfuse import Langfuse
        except ModuleNotFoundError as exc:  # pragma: no cover - runtime-only dependency
            raise RuntimeError("Install the langfuse package before running this smoke script.") from exc

        client = Langfuse(
            public_key=config.public_key,
            secret_key=config.secret_key,
            host=base_url,
        )
        auth_check = client.auth_check()
        if auth_check is not True:
            raise RuntimeError(f"Langfuse auth_check failed: {auth_check!r}")

        with client.start_as_current_observation(
            trace_context={"trace_id": trace_id},
            name="lv3-langfuse-smoke",
            input={"task": "smoke"},
            metadata={"source": "codex", "repo": "platform_server", "user_id": "codex"},
            as_type="span",
        ) as root:
            root.set_trace_io(
                input={"task": "smoke"},
                output={"status": "started"},
            )
            with client.start_as_current_observation(
                name="codex-generation",
                as_type="generation",
                input="verify langfuse ingestion",
                output="langfuse smoke completed",
                model="codex-smoke",
                metadata={"kind": "smoke"},
            ):
                pass
        client.flush()

        api_trace = None
        deadline = time.time() + args.timeout_seconds
        while time.time() < deadline:
            response = requests.get(
                f"{base_url}/api/public/traces/{trace_id}",
                auth=(config.public_key, config.secret_key),
                timeout=30,
            )
            if response.status_code == 200:
                api_trace = response.json()
                break
            time.sleep(3)
        if api_trace is None:
            raise RuntimeError(f"Timed out waiting for trace {trace_id} to appear in Langfuse.")

        ui_url = trace_url(base_url, project_id, trace_id)
        result = {
            "trace_id": trace_id,
            "trace_url": ui_url,
            "api_verified": api_trace.get("id") == trace_id,
            "project_id": project_id,
        }

        if args.bootstrap_email and args.bootstrap_password_file:
            session = _build_session(
                base_url=base_url,
                email=args.bootstrap_email,
                password=args.bootstrap_password_file.read_text(encoding="utf-8").strip(),
            )
            page = session.get(ui_url, timeout=30)
            page.raise_for_status()
            result["ui_verified"] = "/auth/sign-in" not in page.url
            result["ui_status_code"] = page.status_code
            if not result["ui_verified"]:
                raise RuntimeError(f"Langfuse trace UI verification did not reach the trace page: {page.url}")

        print(dump_json(result))
        return 0
    except (OSError, RuntimeError, requests.RequestException, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
