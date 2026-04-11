from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from scripts import browser_runner_service


class FakeTimeoutError(RuntimeError):
    pass


class FakeLocator:
    def __init__(self, page: "FakePage", selector: str):
        self.page = page
        self.selector = selector

    @property
    def first(self) -> "FakeLocator":
        return self

    async def count(self) -> int:
        return 1 if self.selector in self.page.known_selectors else 0

    async def click(self, timeout: int) -> None:  # noqa: ARG002
        if self.selector == "#apply":
            self.page.elements["#result"] = self.page.inputs.get("#name", "").upper()

    async def fill(self, value: str, timeout: int) -> None:  # noqa: ARG002
        self.page.inputs[self.selector] = value

    async def press(self, key: str, timeout: int) -> None:  # noqa: ARG002
        self.page.inputs[f"pressed:{self.selector}"] = key

    async def select_option(self, value, timeout: int) -> None:  # noqa: ANN001, ARG002
        if isinstance(value, list):
            self.page.inputs[self.selector] = ",".join(value)
        else:
            self.page.inputs[self.selector] = str(value)

    async def text_content(self) -> str:
        if self.selector in self.page.inputs:
            return self.page.inputs[self.selector]
        return self.page.elements.get(self.selector, "")

    async def get_attribute(self, name: str) -> str | None:
        return self.page.attributes.get((self.selector, name))


class FakePage:
    def __init__(self):
        self.url = "about:blank"
        self.inputs: dict[str, str] = {}
        self.elements: dict[str, str] = {
            "h1": "LV3 Browser Runner Smoke",
            "#result": "PENDING",
        }
        self.attributes = {("h1", "id"): "heading"}
        self.download_handler = None

    @property
    def known_selectors(self) -> set[str]:
        return {"h1", "#name", "#apply", "#result"}

    def on(self, event: str, handler) -> None:  # noqa: ANN001
        if event == "download":
            self.download_handler = handler

    async def goto(self, url: str, wait_until: str, timeout: int) -> None:  # noqa: ARG002
        self.url = url

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self, selector)

    async def wait_for_selector(self, selector: str, state: str, timeout: int) -> None:  # noqa: ARG002
        if selector not in self.known_selectors:
            raise RuntimeError(f"selector not found: {selector}")
        if state == "visible" and not self.elements.get(selector, self.inputs.get(selector, "")):
            raise RuntimeError(f"selector not visible: {selector}")

    async def wait_for_timeout(self, milliseconds: int) -> None:  # noqa: ARG002
        return None

    async def screenshot(self, path: str, full_page: bool) -> None:  # noqa: ARG002
        Path(path).write_bytes(b"png")

    async def pdf(self, path: str, print_background: bool) -> None:  # noqa: ARG002
        Path(path).write_bytes(b"pdf")

    async def title(self) -> str:
        return self.elements["h1"]

    async def text_content(self, selector: str) -> str:
        if selector == "body":
            return f"{self.elements['h1']} {self.inputs.get('#name', '')} {self.elements['#result']}".strip()
        if selector in self.inputs:
            return self.inputs[selector]
        return self.elements.get(selector, "")


class FakeContext:
    def __init__(self):
        self.page = FakePage()

    async def new_page(self) -> FakePage:
        return self.page

    async def close(self) -> None:
        return None


class FakeBrowser:
    def __init__(self):
        self.context = FakeContext()

    async def new_context(self, accept_downloads: bool, viewport: dict[str, int]) -> FakeContext:  # noqa: ARG002
        return self.context

    async def close(self) -> None:
        return None


class FakeChromium:
    async def launch(self, headless: bool, args: list[str]) -> FakeBrowser:  # noqa: ARG002
        return FakeBrowser()


class FakePlaywright:
    chromium = FakeChromium()


class FakePlaywrightContextManager:
    async def __aenter__(self) -> FakePlaywright:
        return FakePlaywright()

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None


def fake_playwright_loader():
    def async_playwright():
        return FakePlaywrightContextManager()

    return async_playwright, FakeTimeoutError


def test_run_browser_session_executes_steps_and_writes_artifacts(tmp_path: Path) -> None:
    payload = browser_runner_service.BrowserRunRequest(
        url="data:text/html,<html></html>",
        steps=[
            browser_runner_service.SessionStep(action="fill", selector="#name", value="browser runner"),
            browser_runner_service.SessionStep(action="click", selector="#apply"),
            browser_runner_service.SessionStep(action="wait_for_selector", selector="#result"),
        ],
        selectors=[
            browser_runner_service.SelectorQuery(name="heading", selector="h1"),
            browser_runner_service.SelectorQuery(name="result", selector="#result"),
        ],
        capture_screenshot=True,
        capture_pdf=True,
    )

    result = asyncio.run(
        browser_runner_service.run_browser_session(
            payload,
            artifact_root=tmp_path / "artifacts",
            playwright_loader=fake_playwright_loader,
        )
    )

    assert result["title"] == "LV3 Browser Runner Smoke"
    assert result["selector_results"][0]["text"] == "LV3 Browser Runner Smoke"
    assert result["selector_results"][1]["text"] == "BROWSER RUNNER"
    assert [entry["action"] for entry in result["action_log"]] == ["goto", "fill", "click", "wait_for_selector"]
    assert {artifact["kind"] for artifact in result["artifacts"]} == {"screenshot", "pdf"}
    assert all(
        (tmp_path / artifact["path"]).exists() or artifact["path"].startswith("artifacts/")
        for artifact in result["artifacts"]
    )


def test_health_endpoint_reports_ok(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BROWSER_RUNNER_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    client = TestClient(browser_runner_service.app)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["artifact_root"] == str(tmp_path / "artifacts")


def test_session_endpoint_maps_validation_errors_to_http_400() -> None:
    client = TestClient(browser_runner_service.app)

    response = client.post(
        "/sessions",
        json={
            "url": "https://example.com",
            "steps": [
                {
                    "action": "wait_for_timeout",
                    "milliseconds": 0,
                }
            ],
        },
    )

    assert response.status_code == 400
    assert "milliseconds" in response.json()["detail"]
