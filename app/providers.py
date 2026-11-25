"""Embedding and text-generation clients.

Two providers are implemented: Google Gemini and any OpenAI-compatible API
(OpenAI, Azure OpenAI, Ollama, vLLM, LM Studio ...). The rest of the app only
uses the Embedder and Generator protocols, so adding a provider means adding
one class here.
"""

from __future__ import annotations

import logging
import time
from typing import Protocol

import httpx
import numpy as np

from app.config import Settings

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


class ProviderError(RuntimeError):
    """The provider could not produce a result (all retries and fallback models failed)."""


class Embedder(Protocol):
    name: str

    def embed_documents(self, texts: list[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


class Generator(Protocol):
    def generate(self, system: str, prompt: str) -> tuple[str, str]:
        """Returns (text, model name that answered)."""
        ...


def normalize(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def _retry_after(response: httpx.Response) -> float | None:
    """Seconds the server asks us to wait (Retry-After header or Google's RetryInfo detail)."""
    header = response.headers.get("retry-after", "")
    if header.isdigit():
        return float(header)
    try:
        error = response.json().get("error", {})
    except (ValueError, AttributeError):
        return None
    details = error.get("details", []) if isinstance(error, dict) else []
    for detail in details:
        delay = str(detail.get("retryDelay", "")) if isinstance(detail, dict) else ""
        if delay.endswith("s"):
            try:
                return float(delay[:-1])
            except ValueError:
                return None
    return None


def _post(
    client: httpx.Client, url: str, payload: dict, headers: dict, attempts: int = 3, max_wait: float = 8.0
) -> dict:
    """POST with retries on network errors, rate limits and server errors.

    Interactive requests keep max_wait short so a visitor is not kept waiting;
    batch jobs such as indexing pass a longer max_wait to sit out a per-minute quota.
    """
    delay = 1.0
    for attempt in range(1, attempts + 1):
        wait = delay
        try:
            response = client.post(url, json=payload, headers=headers)
        except httpx.TransportError as exc:
            if attempt == attempts:
                raise ProviderError(f"network error: {exc.__class__.__name__}") from exc
        else:
            if response.status_code < 400:
                try:
                    data = response.json()
                except ValueError as exc:
                    raise ProviderError("response is not JSON") from exc
                if not isinstance(data, dict):
                    raise ProviderError("unexpected response")
                return data
            if response.status_code not in RETRY_STATUS or attempt == attempts:
                raise ProviderError(f"HTTP {response.status_code}")
            wait = max(delay, _retry_after(response) or 0.0)
            if wait > max_wait:
                raise ProviderError(f"HTTP {response.status_code}, retry in {wait:.0f}s")
        time.sleep(wait)
        delay *= 2
    raise ProviderError("no response")


class GeminiEmbedder:
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"
    BATCH = 100

    def __init__(self, api_key: str, model: str, dim: int, client: httpx.Client | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.dim = dim
        self.name = f"gemini/{model}/{dim}"
        self.client = client or httpx.Client(timeout=60)

    def _embed(self, texts: list[str], task: str) -> np.ndarray:
        batch_job = len(texts) > 1
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.BATCH):
            batch = texts[start : start + self.BATCH]
            payload = {
                "requests": [
                    {
                        "model": f"models/{self.model}",
                        "content": {"parts": [{"text": text}]},
                        "taskType": task,
                        "outputDimensionality": self.dim,
                    }
                    for text in batch
                ]
            }
            data = _post(
                self.client,
                self.URL.format(model=self.model),
                payload,
                {"x-goog-api-key": self.api_key},
                attempts=6 if batch_job else 3,
                max_wait=90.0 if batch_job else 8.0,
            )
            try:
                vectors.extend(item["values"] for item in data["embeddings"])
            except (KeyError, TypeError) as exc:
                raise ProviderError("unexpected embedding response") from exc
        # Normalized here, so a dot product is the cosine similarity whatever the output size.
        return normalize(np.array(vectors))

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([text], "RETRIEVAL_QUERY")[0]


class GeminiGenerator:
    """Gemini Interactions API. Tries the next model when one is overloaded."""

    URL = "https://generativelanguage.googleapis.com/v1beta/interactions"

    def __init__(self, api_key: str, models: tuple[str, ...], client: httpx.Client | None = None) -> None:
        self.api_key = api_key
        self.models = models
        self.client = client or httpx.Client(timeout=60)

    @staticmethod
    def _text(data: dict) -> str:
        parts = [
            content.get("text", "")
            for step in data.get("steps", [])
            if step.get("type") == "model_output"
            for content in step.get("content", [])
            if content.get("type") == "text"
        ]
        return "".join(parts).strip()

    def generate(self, system: str, prompt: str) -> tuple[str, str]:
        problems = []
        for model in self.models:
            payload = {
                "model": model,
                "system_instruction": system,
                "input": prompt,
                "store": False,
                "generation_config": {"max_output_tokens": 2048, "temperature": 0.1},
            }
            try:
                data = _post(self.client, self.URL, payload, {"x-goog-api-key": self.api_key}, attempts=2)
            except ProviderError as exc:
                problems.append(f"{model}: {exc}")
                continue
            try:
                text = self._text(data)
            except (TypeError, AttributeError):
                problems.append(f"{model}: unexpected response")
                continue
            if text:
                return text, model
            problems.append(f"{model}: empty answer ({data.get('status')})")
        log.warning("generation failed: %s", "; ".join(problems))
        raise ProviderError("; ".join(problems))


class OpenAICompatibleEmbedder:
    def __init__(self, base_url: str, api_key: str, model: str, client: httpx.Client | None = None) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.name = f"openai/{model}"
        self.client = client or httpx.Client(timeout=60)

    def _embed(self, texts: list[str]) -> np.ndarray:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        data = _post(self.client, f"{self.base_url}/embeddings", {"model": self.model, "input": texts}, headers)
        try:
            rows = sorted(data["data"], key=lambda item: item["index"])
            vectors = [row["embedding"] for row in rows]
        except (KeyError, TypeError) as exc:
            raise ProviderError("unexpected embedding response") from exc
        return normalize(np.array(vectors))

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.vstack([self._embed(texts[i : i + 100]) for i in range(0, len(texts), 100)])

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([text])[0]


class OpenAICompatibleGenerator:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.Client | None = None,
        reasoning_effort: str = "",
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.client = client or httpx.Client(timeout=60)
        # Only for reasoning models that accept it (for example gpt-oss on Groq: low, medium, high).
        self.reasoning_effort = reasoning_effort

    def generate(self, system: str, prompt: str) -> tuple[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload: dict = {
            "model": self.model,
            "temperature": 0.1,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        data = _post(self.client, f"{self.base_url}/chat/completions", payload, headers)
        try:
            text = (data["choices"][0]["message"].get("content") or "").strip()
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ProviderError("unexpected answer response") from exc
        if not text:
            raise ProviderError("empty answer")
        return text, self.model


class FallbackGenerator:
    """Asks each generator in turn and returns the first answer."""

    def __init__(self, generators: list[Generator]) -> None:
        if not generators:
            raise ProviderError("no answer provider configured")
        self.generators = generators

    def generate(self, system: str, prompt: str) -> tuple[str, str]:
        problems = []
        for generator in self.generators:
            try:
                return generator.generate(system, prompt)
            except ProviderError as exc:
                problems.append(str(exc))
                log.warning("answer provider failed, trying the next one: %s", exc)
        raise ProviderError("; ".join(problems))


def _require(value: str, name: str) -> str:
    if not value:
        raise ProviderError(f"{name} is not set")
    return value


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedding_provider == "gemini":
        key = _require(settings.gemini_api_key, "GEMINI_API_KEY")
        return GeminiEmbedder(key, settings.gemini_embedding_model, settings.embedding_dim)
    if settings.embedding_provider == "openai":
        model = _require(settings.openai_embedding_model, "OPENAI_EMBEDDING_MODEL")
        return OpenAICompatibleEmbedder(settings.openai_base_url, settings.openai_api_key, model)
    raise ProviderError(f"Unknown EMBEDDING_PROVIDER: {settings.embedding_provider}")


def build_generator(settings: Settings) -> Generator:
    generators: list[Generator] = []
    for name in settings.generators:
        if name == "gemini":
            key = _require(settings.gemini_api_key, "GEMINI_API_KEY")
            generators.append(GeminiGenerator(key, settings.gemini_models))
        elif name == "openai":
            model = _require(settings.openai_model, "OPENAI_MODEL")
            generators.append(
                OpenAICompatibleGenerator(
                    settings.openai_base_url,
                    settings.openai_api_key,
                    model,
                    reasoning_effort=settings.openai_reasoning_effort,
                )
            )
        else:
            raise ProviderError(f"Unknown answer provider in GENERATORS: {name}")
    return generators[0] if len(generators) == 1 else FallbackGenerator(generators)


def build_providers(settings: Settings) -> tuple[Embedder, Generator]:
    return build_embedder(settings), build_generator(settings)
