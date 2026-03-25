from __future__ import annotations

from pathlib import Path

import yaml

from repo_package_loader import load_repo_package


LLM_MODULE = load_repo_package(
    "lv3_platform_llm_test",
    Path(__file__).resolve().parents[1] / "platform" / "llm",
)
PlatformLLMClient = LLM_MODULE.PlatformLLMClient


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class RecordingLedger:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def write(self, **kwargs):
        self.events.append(kwargs)
        return kwargs


def test_client_routes_to_available_ollama_model_and_records_ledger_event(tmp_path: Path) -> None:
    write(
        tmp_path / "config" / "ollama-models.yaml",
        yaml.safe_dump(
            {
                "schema_version": "1.0.0",
                "models": [
                    {
                        "name": "llama3.2:3b",
                        "provider": "ollama",
                        "use_cases": ["goal_compiler_normalisation"],
                        "max_context": 8192,
                        "ram_requirement_gb": 4,
                        "pull_on_startup": True,
                    }
                ],
            }
        ),
    )
    calls: list[tuple[str, str]] = []

    def fake_request(method: str, url: str, payload, headers, timeout):
        calls.append((method, url))
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama3.2:3b"}]}
        if url.endswith("/api/generate"):
            return {"response": "deploy netbox", "prompt_eval_count": 12, "eval_count": 4}
        raise AssertionError(url)

    monotonic_values = iter([10.0, 10.2])
    ledger = RecordingLedger()
    client = PlatformLLMClient(
        tmp_path,
        request_json=fake_request,
        ledger_writer=ledger,
        monotonic=lambda: next(monotonic_values),
    )

    response = client.complete("normalize this", use_case="goal_compiler_normalisation", max_tokens=32)

    assert response == "deploy netbox"
    assert calls == [
        ("GET", "http://127.0.0.1:11434/api/tags"),
        ("POST", "http://127.0.0.1:11434/api/generate"),
    ]
    assert ledger.events[0]["event_type"] == "llm.inference"
    assert ledger.events[0]["metadata"]["provider"] == "ollama"
    assert ledger.events[0]["metadata"]["latency_ms"] == 199


def test_client_falls_back_to_openai_compatible_endpoint_when_ollama_is_unavailable(tmp_path: Path) -> None:
    write(
        tmp_path / "config" / "ollama-models.yaml",
        yaml.safe_dump(
            {
                "schema_version": "1.0.0",
                "models": [
                    {
                        "name": "llama3.2:3b",
                        "provider": "ollama",
                        "use_cases": ["goal_compiler_normalisation"],
                        "max_context": 8192,
                        "ram_requirement_gb": 4,
                        "pull_on_startup": True,
                    }
                ],
            }
        ),
    )

    def fake_request(method: str, url: str, payload, headers, timeout):
        if url.endswith("/api/tags"):
            raise RuntimeError("ollama unavailable")
        if url.endswith("/chat/completions"):
            return {
                "choices": [{"message": {"content": "deploy netbox"}}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 3},
            }
        raise AssertionError(url)

    client = PlatformLLMClient(
        tmp_path,
        request_json=fake_request,
        fallback_base_url="https://llm.example.test/v1",
        fallback_model="gpt-4o-mini",
        fallback_api_key="test-token",
    )

    response = client.complete("normalize this", use_case="goal_compiler_normalisation", max_tokens=16)

    assert response == "deploy netbox"
