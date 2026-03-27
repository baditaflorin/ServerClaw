from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from platform.circuit import CircuitOpenError, CircuitRegistry


RequestJson = Callable[[str, str, dict[str, Any] | None, dict[str, str] | None, float], dict[str, Any]]


@dataclass(frozen=True)
class ModelDefinition:
    name: str
    provider: str
    use_cases: tuple[str, ...]
    max_context: int
    ram_requirement_gb: int
    pull_on_startup: bool


@dataclass(frozen=True)
class CompletionResult:
    text: str
    prompt_tokens: int
    completion_tokens: int


class LLMUnavailableError(RuntimeError):
    pass


class PlatformLLMClient:
    def __init__(
        self,
        repo_root: Path | str,
        *,
        ollama_base_url: str | None = None,
        model_catalog_path: Path | str | None = None,
        fallback_base_url: str | None = None,
        fallback_model: str | None = None,
        fallback_api_key: str | None = None,
        timeout_seconds: float = 5.0,
        ledger_writer: Any | None = None,
        actor: str = "service:platform-llm-client",
        request_json: RequestJson | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        circuit_registry: CircuitRegistry | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        default_catalog = self.repo_root / "config" / "ollama-models.yaml"
        self.model_catalog_path = Path(model_catalog_path) if model_catalog_path else default_catalog
        self.ollama_base_url = (ollama_base_url or os.environ.get("LV3_OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
        self.fallback_base_url = (fallback_base_url or os.environ.get("LV3_LLM_FALLBACK_BASE_URL", "")).rstrip("/")
        self.fallback_model = fallback_model or os.environ.get("LV3_LLM_FALLBACK_MODEL", "").strip()
        self.fallback_api_key = fallback_api_key or os.environ.get("LV3_LLM_FALLBACK_API_KEY", "").strip()
        self.timeout_seconds = timeout_seconds
        self.actor = actor
        self._request_json = request_json or self._default_request_json
        self._monotonic = monotonic
        self.model_catalog = self._load_model_catalog()
        self.ledger_writer = ledger_writer or self._build_default_ledger_writer()
        self._circuit_registry = circuit_registry or CircuitRegistry(self.repo_root)
        self._ollama_circuit = (
            self._circuit_registry.sync_breaker("ollama")
            if self._circuit_registry.has_policy("ollama")
            else None
        )
        self._fallback_circuit = (
            self._circuit_registry.sync_breaker("anthropic_api")
            if self._circuit_registry.has_policy("anthropic_api")
            else None
        )

    def complete(
        self,
        prompt: str,
        *,
        use_case: str,
        max_tokens: int = 128,
        temperature: float = 0.0,
    ) -> str:
        model = self._route(use_case)
        started = self._monotonic()
        if model.provider == "ollama":
            result = self._ollama_complete(prompt, model.name, max_tokens=max_tokens, temperature=temperature)
            target_id = "ollama"
        elif model.provider == "openai_compatible":
            result = self._fallback_complete(prompt, model.name, max_tokens=max_tokens, temperature=temperature)
            target_id = "external-llm"
        else:
            raise LLMUnavailableError(f"unsupported LLM provider: {model.provider}")

        latency_ms = int((self._monotonic() - started) * 1000)
        self._write_ledger_event(
            provider=model.provider,
            model=model.name,
            use_case=use_case,
            latency_ms=latency_ms,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            target_id=target_id,
        )
        return result.text.strip()

    def available_models(self) -> set[str]:
        def fetch_tags() -> dict[str, Any]:
            return self._request_json(
                "GET",
                f"{self.ollama_base_url}/api/tags",
                None,
                None,
                self.timeout_seconds,
            )

        if self._ollama_circuit is not None:
            payload = self._ollama_circuit.call(fetch_tags)
        else:
            payload = fetch_tags()
        models = payload.get("models", [])
        if not isinstance(models, list):
            return set()
        available = set()
        for item in models:
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                if name:
                    available.add(name)
        return available

    def _load_model_catalog(self) -> list[ModelDefinition]:
        payload = yaml.safe_load(self.model_catalog_path.read_text(encoding="utf-8")) or {}
        models = payload.get("models", [])
        if not isinstance(models, list):
            raise ValueError(f"{self.model_catalog_path} must define a models list")
        catalog: list[ModelDefinition] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            catalog.append(
                ModelDefinition(
                    name=str(item["name"]).strip(),
                    provider=str(item.get("provider", "ollama")).strip() or "ollama",
                    use_cases=tuple(str(value).strip() for value in item.get("use_cases", []) if str(value).strip()),
                    max_context=int(item.get("max_context", 4096)),
                    ram_requirement_gb=int(item.get("ram_requirement_gb", 0)),
                    pull_on_startup=bool(item.get("pull_on_startup", False)),
                )
            )
        return catalog

    def _route(self, use_case: str) -> ModelDefinition:
        available = self._safe_available_models()
        for model in self.model_catalog:
            if model.provider != "ollama":
                continue
            if use_case in model.use_cases and model.name in available:
                return model
        if self.fallback_base_url and self.fallback_model:
            return ModelDefinition(
                name=self.fallback_model,
                provider="openai_compatible",
                use_cases=(use_case,),
                max_context=8192,
                ram_requirement_gb=0,
                pull_on_startup=False,
            )
        raise LLMUnavailableError(f"no available model for use case '{use_case}'")

    def _safe_available_models(self) -> set[str]:
        try:
            return self.available_models()
        except CircuitOpenError as exc:
            if self.fallback_base_url and self.fallback_model:
                return set()
            raise LLMUnavailableError(f"Ollama circuit is open for {exc.retry_after}s") from exc
        except Exception as exc:  # noqa: BLE001
            if self.fallback_base_url and self.fallback_model:
                return set()
            raise LLMUnavailableError(f"Ollama is unavailable at {self.ollama_base_url}: {exc}") from exc

    def _ollama_complete(
        self,
        prompt: str,
        model_name: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> CompletionResult:
        def generate() -> dict[str, Any]:
            return self._request_json(
                "POST",
                f"{self.ollama_base_url}/api/generate",
                {
                    "model": model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature,
                    },
                },
                None,
                self.timeout_seconds,
            )

        if self._ollama_circuit is not None:
            payload = self._ollama_circuit.call(generate)
        else:
            payload = generate()
        return CompletionResult(
            text=str(payload.get("response", "")).strip(),
            prompt_tokens=int(payload.get("prompt_eval_count", 0) or 0),
            completion_tokens=int(payload.get("eval_count", 0) or 0),
        )

    def _fallback_complete(
        self,
        prompt: str,
        model_name: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> CompletionResult:
        headers = {"Content-Type": "application/json"}
        if self.fallback_api_key:
            headers["Authorization"] = f"Bearer {self.fallback_api_key}"

        def complete() -> dict[str, Any]:
            return self._request_json(
                "POST",
                f"{self.fallback_base_url}/chat/completions",
                {
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                headers,
                self.timeout_seconds,
            )

        if self._fallback_circuit is not None:
            payload = self._fallback_circuit.call(complete)
        else:
            payload = complete()
        choices = payload.get("choices", [])
        message = choices[0].get("message", {}) if isinstance(choices, list) and choices else {}
        usage = payload.get("usage", {}) if isinstance(payload.get("usage"), dict) else {}
        return CompletionResult(
            text=str(message.get("content", "")).strip(),
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
        )

    def _write_ledger_event(
        self,
        *,
        provider: str,
        model: str,
        use_case: str,
        latency_ms: int,
        prompt_tokens: int,
        completion_tokens: int,
        target_id: str,
    ) -> None:
        if self.ledger_writer is None:
            return
        self.ledger_writer.write(
            event_type="llm.inference",
            actor=self.actor,
            target_kind="service",
            target_id=target_id,
            metadata={
                "provider": provider,
                "model": model,
                "use_case": use_case,
                "latency_ms": latency_ms,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
        )

    def _build_default_ledger_writer(self) -> Any | None:
        if not os.environ.get("LV3_LEDGER_DSN") and not os.environ.get("LV3_LEDGER_FILE"):
            return None
        from platform.ledger import LedgerWriter

        return LedgerWriter()

    @staticmethod
    def _default_request_json(
        method: str,
        url: str,
        payload: dict[str, Any] | None,
        headers: dict[str, str] | None,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        body = None
        request_headers = dict(headers or {})
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(url, method=method, data=body, headers=request_headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - exercised through caller behavior
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {urllib.parse.urlsplit(url).path} returned HTTP {exc.code}: {detail}") from exc
