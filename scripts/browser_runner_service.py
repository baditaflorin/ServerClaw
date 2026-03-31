#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("BROWSER_RUNNER_DEFAULT_TIMEOUT_SECONDS", "45"))
MAX_TIMEOUT_SECONDS = int(os.environ.get("BROWSER_RUNNER_MAX_TIMEOUT_SECONDS", "180"))
ALLOWED_WAIT_UNTIL = {"load", "domcontentloaded", "networkidle", "commit"}
ALLOWED_SELECTOR_STATES = {"attached", "detached", "hidden", "visible"}
ALLOWED_STEP_ACTIONS = {
    "goto",
    "click",
    "fill",
    "press",
    "select_option",
    "wait_for_selector",
    "wait_for_timeout",
    "screenshot",
    "pdf",
}


class SessionStep(BaseModel):
    action: str
    selector: str = ""
    url: str = ""
    value: str = ""
    key: str = ""
    attribute: str = ""
    wait_until: str = "domcontentloaded"
    state: str = "visible"
    full_page: bool = True
    name: str = ""
    timeout_seconds: int = Field(default=DEFAULT_TIMEOUT_SECONDS, ge=1)
    milliseconds: int = Field(default=0, ge=0)
    values: list[str] = Field(default_factory=list)


class SelectorQuery(BaseModel):
    name: str
    selector: str
    attribute: str = ""


class BrowserRunRequest(BaseModel):
    url: str
    steps: list[SessionStep] = Field(default_factory=list)
    selectors: list[SelectorQuery] = Field(default_factory=list)
    capture_screenshot: bool = True
    capture_pdf: bool = False
    timeout_seconds: int = Field(default=DEFAULT_TIMEOUT_SECONDS, ge=1)
    wait_until: str = "domcontentloaded"
    viewport_width: int = Field(default=1440, ge=320)
    viewport_height: int = Field(default=900, ge=200)


class BrowserRunnerError(RuntimeError):
    """Raised when the runtime cannot complete a browser session."""


def resolve_artifact_root() -> Path:
    return Path(os.environ.get("BROWSER_RUNNER_ARTIFACT_ROOT", "/data/artifacts")).expanduser()


def load_playwright_async_api():
    try:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        from playwright.async_api import async_playwright
    except ModuleNotFoundError as exc:  # pragma: no cover - direct runtime guard
        raise RuntimeError(
            "Playwright is not installed. Build the browser runner image or run via "
            "'uv run --with-requirements requirements/browser-runner.txt ...'."
        ) from exc
    return async_playwright, PlaywrightTimeoutError


def ensure_timeout_seconds(value: int, label: str) -> int:
    if value < 1 or value > MAX_TIMEOUT_SECONDS:
        raise ValueError(f"{label} must be between 1 and {MAX_TIMEOUT_SECONDS} seconds")
    return value


def validate_request(request: BrowserRunRequest) -> None:
    if request.wait_until not in ALLOWED_WAIT_UNTIL:
        raise ValueError(f"wait_until must be one of {sorted(ALLOWED_WAIT_UNTIL)}")
    ensure_timeout_seconds(request.timeout_seconds, "timeout_seconds")
    for index, step in enumerate(request.steps, start=1):
        validate_step(step, index=index)


def validate_step(step: SessionStep, *, index: int) -> None:
    if step.action not in ALLOWED_STEP_ACTIONS:
        raise ValueError(f"steps[{index}].action must be one of {sorted(ALLOWED_STEP_ACTIONS)}")
    ensure_timeout_seconds(step.timeout_seconds, f"steps[{index}].timeout_seconds")
    if step.wait_until not in ALLOWED_WAIT_UNTIL:
        raise ValueError(f"steps[{index}].wait_until must be one of {sorted(ALLOWED_WAIT_UNTIL)}")
    if step.state not in ALLOWED_SELECTOR_STATES:
        raise ValueError(f"steps[{index}].state must be one of {sorted(ALLOWED_SELECTOR_STATES)}")

    if step.action in {"click", "fill", "press", "select_option", "wait_for_selector"} and not step.selector:
        raise ValueError(f"steps[{index}].selector is required for action '{step.action}'")
    if step.action == "goto" and not step.url:
        raise ValueError(f"steps[{index}].url is required for action 'goto'")
    if step.action == "fill" and not step.value:
        raise ValueError(f"steps[{index}].value is required for action 'fill'")
    if step.action == "press" and not step.key:
        raise ValueError(f"steps[{index}].key is required for action 'press'")
    if step.action == "select_option" and not (step.value or step.values):
        raise ValueError(f"steps[{index}].value or steps[{index}].values is required for action 'select_option'")
    if step.action == "wait_for_timeout" and step.milliseconds <= 0:
        raise ValueError(f"steps[{index}].milliseconds must be greater than 0 for action 'wait_for_timeout'")


def normalize_text(value: str | None, *, limit: int = 500) -> str:
    if not value:
        return ""
    collapsed = re.sub(r"\s+", " ", value).strip()
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 3].rstrip() + "..."


def slugify(value: str) -> str:
    collapsed = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return collapsed or "artifact"


def describe_artifact(path: Path, *, artifact_root: Path, kind: str, content_type: str | None = None) -> dict[str, Any]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    relative_to = artifact_root.parent if path.is_relative_to(artifact_root) else artifact_root
    guessed_type = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return {
        "kind": kind,
        "path": str(path.relative_to(relative_to)),
        "sha256": digest,
        "size_bytes": path.stat().st_size,
        "content_type": guessed_type,
    }


async def capture_screenshot(page: Any, artifact_root: Path, run_dir: Path, *, name: str, full_page: bool) -> dict[str, Any]:
    target = run_dir / f"{slugify(name)}.png"
    await page.screenshot(path=str(target), full_page=full_page)
    return describe_artifact(target, artifact_root=artifact_root, kind="screenshot", content_type="image/png")


async def capture_pdf(page: Any, artifact_root: Path, run_dir: Path, *, name: str) -> dict[str, Any]:
    target = run_dir / f"{slugify(name)}.pdf"
    await page.pdf(path=str(target), print_background=True)
    return describe_artifact(target, artifact_root=artifact_root, kind="pdf", content_type="application/pdf")


async def persist_download(download: Any, artifact_root: Path, run_dir: Path, *, index: int) -> dict[str, Any]:
    suggested = slugify(getattr(download, "suggested_filename", "") or f"download-{index}")
    target = run_dir / f"{index:02d}-{suggested}"
    await download.save_as(str(target))
    return describe_artifact(target, artifact_root=artifact_root, kind="download")


def build_action_log_entry(index: int, action: str, detail: str) -> dict[str, Any]:
    return {
        "index": index,
        "action": action,
        "detail": detail,
    }


async def extract_selector(page: Any, selector: SelectorQuery) -> dict[str, Any]:
    locator = page.locator(selector.selector)
    count = await locator.count()
    exists = count > 0
    text_value = ""
    attribute_value = ""
    if exists:
        handle = locator.first
        if selector.attribute:
            attribute_value = (await handle.get_attribute(selector.attribute)) or ""
        text_value = normalize_text(await handle.text_content())
    return {
        "name": selector.name,
        "selector": selector.selector,
        "attribute": selector.attribute,
        "exists": exists,
        "count": count,
        "text": text_value,
        "attribute_value": attribute_value,
    }


async def apply_step(
    page: Any,
    step: SessionStep,
    *,
    artifact_root: Path,
    run_dir: Path,
) -> tuple[str, dict[str, Any] | None]:
    timeout_ms = step.timeout_seconds * 1000
    if step.action == "goto":
        await page.goto(step.url, wait_until=step.wait_until, timeout=timeout_ms)
        return f"navigated to {step.url}", None

    if step.action == "click":
        await page.locator(step.selector).first.click(timeout=timeout_ms)
        return f"clicked {step.selector}", None

    if step.action == "fill":
        await page.locator(step.selector).first.fill(step.value, timeout=timeout_ms)
        return f"filled {step.selector}", None

    if step.action == "press":
        await page.locator(step.selector).first.press(step.key, timeout=timeout_ms)
        return f"pressed {step.key} on {step.selector}", None

    if step.action == "select_option":
        values: str | list[str] = step.values or step.value
        await page.locator(step.selector).first.select_option(values, timeout=timeout_ms)
        return f"selected option on {step.selector}", None

    if step.action == "wait_for_selector":
        await page.wait_for_selector(step.selector, state=step.state, timeout=timeout_ms)
        return f"waited for {step.selector} ({step.state})", None

    if step.action == "wait_for_timeout":
        await page.wait_for_timeout(step.milliseconds)
        return f"waited for {step.milliseconds}ms", None

    if step.action == "screenshot":
        name = step.name or f"step-{step.action}"
        artifact = await capture_screenshot(
            page,
            artifact_root,
            run_dir,
            name=name,
            full_page=step.full_page,
        )
        return f"captured screenshot {artifact['path']}", artifact

    if step.action == "pdf":
        name = step.name or f"step-{step.action}"
        artifact = await capture_pdf(page, artifact_root, run_dir, name=name)
        return f"captured pdf {artifact['path']}", artifact

    raise BrowserRunnerError(f"unsupported action '{step.action}'")


async def run_browser_session(
    request: BrowserRunRequest,
    *,
    artifact_root: Path | None = None,
    playwright_loader=load_playwright_async_api,
) -> dict[str, Any]:
    validate_request(request)
    artifact_root = artifact_root or resolve_artifact_root()
    run_id = uuid.uuid4().hex
    run_dir = artifact_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    async_playwright, playwright_timeout_error = playwright_loader()
    action_log: list[dict[str, Any]] = []
    selector_results: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    warnings: list[str] = []
    downloads: list[Any] = []

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(
                accept_downloads=True,
                viewport={"width": request.viewport_width, "height": request.viewport_height},
            )
            try:
                page = await context.new_page()
                page.on("download", lambda download: downloads.append(download))
                await page.goto(
                    request.url,
                    wait_until=request.wait_until,
                    timeout=request.timeout_seconds * 1000,
                )
                action_log.append(build_action_log_entry(0, "goto", f"loaded {request.url}"))

                for index, step in enumerate(request.steps, start=1):
                    detail, artifact = await apply_step(
                        page,
                        step,
                        artifact_root=artifact_root,
                        run_dir=run_dir,
                    )
                    action_log.append(build_action_log_entry(index, step.action, detail))
                    if artifact is not None:
                        artifacts.append(artifact)

                for selector in request.selectors:
                    selector_results.append(await extract_selector(page, selector))

                if request.capture_screenshot:
                    artifacts.append(
                        await capture_screenshot(
                            page,
                            artifact_root,
                            run_dir,
                            name="final-page",
                            full_page=True,
                        )
                    )

                if request.capture_pdf:
                    try:
                        artifacts.append(await capture_pdf(page, artifact_root, run_dir, name="final-page"))
                    except Exception as exc:  # noqa: BLE001
                        warnings.append(f"pdf capture skipped: {exc}")

                for index, download in enumerate(downloads, start=1):
                    artifacts.append(await persist_download(download, artifact_root, run_dir, index=index))

                final_url = page.url
                title = normalize_text(await page.title(), limit=200)
                text_excerpt = normalize_text(await page.text_content("body"))
            finally:
                await context.close()
                await browser.close()
    except playwright_timeout_error as exc:
        raise BrowserRunnerError(f"browser session timed out: {exc}") from exc
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise BrowserRunnerError(f"browser session failed: {exc}") from exc

    return {
        "run_id": run_id,
        "requested_url": request.url,
        "final_url": final_url,
        "title": title,
        "navigation_status": "completed",
        "text_excerpt": text_excerpt,
        "selector_results": selector_results,
        "artifacts": artifacts,
        "action_log": action_log,
        "warnings": warnings,
    }


app = FastAPI(title="LV3 Browser Runner", version="1.0.0")


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {
        "status": "ok",
        "artifact_root": str(resolve_artifact_root()),
    }


@app.post("/sessions")
async def create_session(request: BrowserRunRequest) -> dict[str, Any]:
    try:
        return await run_browser_session(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BrowserRunnerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
