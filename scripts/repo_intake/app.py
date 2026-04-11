"""Repo Intake - Self-service repository deployment interface (ADR 0224).

Provides authenticated intake surfaces for self-service repo deployment:
- Web form at /
- JSON API at /api/v1/repo-intake
- Form actions at /actions/repo-intake/*
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware


UTC = UTC


def utc_now() -> datetime:
    """Return current UTC time without microseconds."""
    return datetime.now(UTC).replace(microsecond=0)


def isoformat(value: datetime) -> str:
    """Format datetime as ISO 8601 with Z suffix."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _load_repo_deploy_catalog() -> list[dict[str, Any]]:
    """Load repo deployment profiles from config/repo-deploy-catalog.json."""
    try:
        catalog_path = Path(__file__).resolve().parents[2] / "config" / "repo-deploy-catalog.json"
        if catalog_path.exists():
            with open(catalog_path) as f:
                data = json.load(f)
            return data.get("profiles", []) if isinstance(data, dict) else []
    except Exception:
        pass
    return []


def create_app() -> FastAPI:
    """Create and configure the repo_intake FastAPI application."""
    app = FastAPI(
        title="Repo Intake",
        description="Self-service repository deployment interface (ADR 0224)",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # Session middleware for authentication state
    app.add_middleware(SessionMiddleware, secret_key=__import__("os").environ.get("SESSION_SECRET", "dev-secret-key"))

    # Static files and templates
    template_dir = Path(__file__).parent / "templates"
    static_dir = Path(__file__).parent / "static"
    if template_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
        templates = Jinja2Templates(directory=template_dir)

    # Root endpoint
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        """Render the repo intake interface."""
        context = {
            "request": request,
            "catalog_profiles": _load_repo_deploy_catalog(),
        }
        return templates.TemplateResponse(request=request, name="index.html", context=context)

    # Form endpoints
    @app.post("/actions/repo-intake/profile/{profile_id}", response_class=HTMLResponse)
    async def deploy_profile(request: Request, profile_id: str) -> HTMLResponse:
        """Deploy a repository using a catalog profile."""
        profiles = _load_repo_deploy_catalog()
        profile = next((p for p in profiles if str(p.get("id", "")) == profile_id), None)
        if profile is None:
            return HTMLResponse(
                f'<div class="alert alert-danger">Profile "{profile_id}" not found.</div>',
                status_code=404,
            )

        try:
            repo_root = Path(__file__).resolve().parents[2]
            args = [
                "python3",
                "-m",
                "scripts.lv3_cli",
                "deploy-repo-profile",
                "--profile-id",
                profile_id,
            ]
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(repo_root),
            )
            if result.returncode == 0:
                status = "queued"
                detail = result.stdout.strip() or f"Profile '{profile_id}' deploy queued."
                tone = "ok"
            else:
                status = "failed"
                detail = result.stderr.strip() or "Deploy failed."
                tone = "danger"
        except Exception as exc:
            status = "failed"
            detail = str(exc)
            tone = "danger"

        html = f"""
        <div class="alert alert-{tone}">
            <strong>{profile.get("app_name", profile_id)}</strong><br>
            <small>{detail}</small>
        </div>
        """
        return HTMLResponse(html)

    @app.post("/actions/repo-intake/custom", response_class=HTMLResponse)
    async def deploy_custom(
        request: Request,
        repo: str = Form(default=""),
        branch: str = Form(default="main"),
        app_name: str = Form(default=""),
        project: str = Form(default="LV3 Apps"),
        environment: str = Form(default="production"),
        build_pack: str = Form(default="dockercompose"),
        source: str = Form(default="auto"),
        domain: str = Form(default=""),
        ports: str = Form(default="80"),
        llm_assistance: str = Form(default="prohibited"),
        docker_compose_location: str = Form(default=""),
    ) -> HTMLResponse:
        """Deploy a custom repository."""
        errors = []
        repo = repo.strip()
        app_name = app_name.strip()

        if not repo:
            errors.append("Repository URL is required.")
        if not app_name:
            errors.append("Application name is required.")
        if source not in {"auto", "public", "private-deploy-key"}:
            errors.append("Invalid source.")
        if build_pack not in {"nixpacks", "static", "dockerfile", "dockercompose"}:
            errors.append("Invalid build pack.")

        if errors:
            html = f'<div class="alert alert-danger">{"<br>".join(errors)}</div>'
            return HTMLResponse(html)

        try:
            repo_root = Path(__file__).resolve().parents[2]
            args = [
                "python3",
                "-m",
                "scripts.lv3_cli",
                "deploy-repo",
                "--repo",
                repo,
                "--branch",
                branch or "main",
                "--source",
                source,
                "--app-name",
                app_name,
                "--project",
                project or "LV3 Apps",
                "--environment",
                environment or "production",
                "--build-pack",
                build_pack,
                "--ports",
                ports or "80",
            ]
            if domain.strip():
                args.extend(["--domain", domain.strip()])
            if docker_compose_location.strip():
                args.extend(["--docker-compose-location", docker_compose_location.strip()])

            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(repo_root),
            )
            if result.returncode == 0:
                status = "ok"
                detail = result.stdout.strip() or f"Repository '{app_name}' deploy queued."
                tone = "success"
            else:
                status = "failed"
                detail = result.stderr.strip() or "Deploy failed."
                tone = "danger"
        except Exception as exc:
            status = "failed"
            detail = str(exc)
            tone = "danger"

        html = f"""
        <div class="alert alert-{tone}">
            <strong>{app_name}</strong><br>
            <small>{detail}</small>
        </div>
        """
        return HTMLResponse(html)

    # JSON API endpoint
    @app.post("/api/v1/repo-intake", response_class=JSONResponse)
    async def api_repo_intake(request: Request) -> JSONResponse:
        """Secure JSON API for programmatic repo intake (ADR 0224)."""
        auth_header = request.headers.get("Authorization", "")
        bearer_token: str | None = None
        if auth_header.lower().startswith("bearer "):
            bearer_token = auth_header[7:].strip()

        static_token = __import__("os").environ.get("REPO_INTAKE_STATIC_API_TOKEN")
        if not bearer_token and not static_token:
            return JSONResponse({"ok": False, "error": "Authentication required."}, status_code=401)

        if bearer_token and static_token and bearer_token != static_token:
            return JSONResponse({"ok": False, "error": "Invalid token."}, status_code=403)

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "Request body must be valid JSON."}, status_code=400)

        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "error": "Request body must be a JSON object."}, status_code=400)

        repo = str(body.get("repo", "")).strip()
        app_name = str(body.get("app_name", "")).strip()
        profile_id = str(body.get("profile_id", "")).strip()

        # Profile-based shortcut
        if profile_id:
            profiles = _load_repo_deploy_catalog()
            profile = next((p for p in profiles if str(p.get("id", "")) == profile_id), None)
            if profile is None:
                return JSONResponse({"ok": False, "error": f"Profile '{profile_id}' not found."}, status_code=404)
            try:
                repo_root = Path(__file__).resolve().parents[2]
                args = ["python3", "-m", "scripts.lv3_cli", "deploy-repo-profile", "--profile-id", profile_id]
                result = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=str(repo_root),
                )
                if result.returncode == 0:
                    return JSONResponse(
                        {
                            "ok": True,
                            "status": "queued",
                            "detail": result.stdout.strip() or "Deploy queued.",
                        }
                    )
                return JSONResponse(
                    {"ok": False, "status": "failed", "detail": result.stderr.strip() or "Deploy failed."},
                    status_code=502,
                )
            except Exception as exc:
                return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

        # Custom repo
        branch = str(body.get("branch", "main")).strip() or "main"
        project = str(body.get("project", "LV3 Apps")).strip() or "LV3 Apps"
        environment = str(body.get("environment", "production")).strip() or "production"
        build_pack = str(body.get("build_pack", "dockercompose")).strip()
        source = str(body.get("source", "auto")).strip()
        domain = str(body.get("domain", "")).strip()
        ports = str(body.get("ports", "80")).strip() or "80"
        docker_compose_location = str(body.get("docker_compose_location", "")).strip()

        errors = []
        if not repo:
            errors.append("'repo' is required.")
        if not app_name:
            errors.append("'app_name' is required.")
        if source not in {"auto", "public", "private-deploy-key"}:
            errors.append("'source' must be one of {'auto', 'public', 'private-deploy-key'}.")
        if build_pack not in {"nixpacks", "static", "dockerfile", "dockercompose"}:
            errors.append("'build_pack' must be one of {'nixpacks', 'static', 'dockerfile', 'dockercompose'}.")

        if errors:
            return JSONResponse({"ok": False, "error": " ".join(errors)}, status_code=422)

        try:
            repo_root = Path(__file__).resolve().parents[2]
            args = [
                "python3",
                "-m",
                "scripts.lv3_cli",
                "deploy-repo",
                "--repo",
                repo,
                "--branch",
                branch,
                "--source",
                source,
                "--app-name",
                app_name,
                "--project",
                project,
                "--environment",
                environment,
                "--build-pack",
                build_pack,
                "--ports",
                ports,
            ]
            if domain:
                args.extend(["--domain", domain])
            if docker_compose_location:
                args.extend(["--docker-compose-location", docker_compose_location])

            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(repo_root),
            )
            if result.returncode == 0:
                return JSONResponse(
                    {
                        "ok": True,
                        "status": "queued",
                        "detail": result.stdout.strip() or "Deploy queued.",
                    }
                )
            return JSONResponse(
                {"ok": False, "status": "failed", "detail": result.stderr.strip() or "Deploy failed."},
                status_code=502,
            )
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    # Health check
    @app.get("/health")
    async def health() -> JSONResponse:
        """Health check endpoint."""
        return JSONResponse({"status": "ok"})

    return app


if __name__ == "__main__":
    import uvicorn

    app = create_app()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(__import__("os").environ.get("PORT", "8096")),
        log_level="info",
    )
