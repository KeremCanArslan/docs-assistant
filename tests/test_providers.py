import json

import httpx
import numpy as np
import pytest
from conftest import ScriptedGenerator

from app.config import Settings
from app.providers import (
    FallbackGenerator,
    GeminiEmbedder,
    GeminiGenerator,
    OpenAICompatibleGenerator,
    ProviderError,
    build_generator,
)


def client_with(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def gemini_text(text: str) -> dict:
    return {"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "text", "text": text}]}]}


def test_gemini_moves_to_the_next_model_when_one_is_overloaded(monkeypatch):
    monkeypatch.setattr("app.providers.time.sleep", lambda _: None)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        seen.append(model)
        if model == "busy-model":
            return httpx.Response(503, json={"error": {"message": "high demand"}})
        return httpx.Response(200, json=gemini_text("Answer [1]."))

    generator = GeminiGenerator("key", ("busy-model", "free-model"), client_with(handler))
    assert generator.generate("system", "prompt") == ("Answer [1].", "free-model")
    assert seen == ["busy-model", "busy-model", "free-model"]


def test_long_retry_delay_fails_fast_instead_of_blocking_the_visitor():
    def handler(request: httpx.Request) -> httpx.Response:
        details = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "62243s"}]
        return httpx.Response(429, json={"error": {"details": details}})

    generator = GeminiGenerator("key", ("only-model",), client_with(handler))
    with pytest.raises(ProviderError, match="retry in 62243s"):
        generator.generate("system", "prompt")


def test_gemini_embeddings_are_normalized_and_use_the_task_type():
    payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        payloads.append(body)
        return httpx.Response(200, json={"embeddings": [{"values": [3.0, 4.0]} for _ in body["requests"]]})

    embedder = GeminiEmbedder("key", "embed-model", 2, client_with(handler))
    vectors = embedder.embed_documents(["a", "b"])
    np.testing.assert_allclose(vectors, [[0.6, 0.8], [0.6, 0.8]])
    assert payloads[0]["requests"][0]["taskType"] == "RETRIEVAL_DOCUMENT"
    embedder.embed_query("q")
    assert payloads[1]["requests"][0]["taskType"] == "RETRIEVAL_QUERY"


def test_openai_compatible_generator_sends_chat_messages():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": " Hi [1]. "}}]})

    generator = OpenAICompatibleGenerator("https://api.example/v1", "secret", "model-x", client_with(handler))
    assert generator.generate("rules", "question") == ("Hi [1].", "model-x")
    assert captured["url"] == "https://api.example/v1/chat/completions"
    assert captured["auth"] == "Bearer secret"
    assert [m["role"] for m in captured["body"]["messages"]] == ["system", "user"]
    assert "reasoning_effort" not in captured["body"]


def test_openai_compatible_generator_sends_reasoning_effort_when_set():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Hi [1]."}}]})

    generator = OpenAICompatibleGenerator(
        "https://api.example/v1", "secret", "model-x", client_with(handler), reasoning_effort="low"
    )
    generator.generate("rules", "question")
    assert captured["body"]["reasoning_effort"] == "low"


def test_fallback_generator_uses_the_next_provider():
    first = ScriptedGenerator(ProviderError("HTTP 429"))
    second = ScriptedGenerator("From the second provider [1].")
    assert FallbackGenerator([first, second]).generate("s", "p") == ("From the second provider [1].", "scripted-model")


def test_fallback_generator_reports_all_failures():
    failing = [ScriptedGenerator(ProviderError("A down")), ScriptedGenerator(ProviderError("B down"))]
    generator = FallbackGenerator(failing)
    with pytest.raises(ProviderError, match="A down; B down"):
        generator.generate("s", "p")


def test_generator_chain_is_built_from_settings():
    settings = Settings(generators=("openai", "gemini"), openai_model="m", gemini_api_key="k")
    generator = build_generator(settings)
    assert isinstance(generator, FallbackGenerator)
    assert [type(g).__name__ for g in generator.generators] == ["OpenAICompatibleGenerator", "GeminiGenerator"]


def test_missing_key_is_a_clear_error():
    with pytest.raises(ProviderError, match="GEMINI_API_KEY"):
        build_generator(Settings(generators=("gemini",)))


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>gateway page</html>"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json=["not", "an", "object"]),
    ],
)
def test_malformed_answer_is_a_provider_error_so_the_fallback_runs(response):
    generator = OpenAICompatibleGenerator("https://api.example/v1", "k", "m", client_with(lambda request: response))
    fallback = FallbackGenerator([generator, ScriptedGenerator("Backup [1].")])
    assert fallback.generate("s", "p") == ("Backup [1].", "scripted-model")


def test_error_body_with_a_plain_string_is_handled(monkeypatch):
    monkeypatch.setattr("app.providers.time.sleep", lambda _: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    generator = OpenAICompatibleGenerator("https://api.example/v1", "k", "m", client_with(handler))
    with pytest.raises(ProviderError, match="HTTP 429"):
        generator.generate("s", "p")


def test_malformed_embedding_response_is_a_provider_error():
    embedder = GeminiEmbedder("k", "e", 2, client_with(lambda request: httpx.Response(200, json={"oops": 1})))
    with pytest.raises(ProviderError):
        embedder.embed_query("q")
