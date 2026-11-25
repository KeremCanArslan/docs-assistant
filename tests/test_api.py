import logging

import pytest
from conftest import ScriptedGenerator
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import Services, create_app
from app.providers import ProviderError
from app.ratelimit import RateLimiter


@pytest.fixture
def client_factory(small_index):
    index, embedder = small_index

    def make(*answers, per_minute: int = 10, per_day: int = 100) -> TestClient:
        services = Services(
            Settings(max_question_chars=100),
            index,
            embedder,
            ScriptedGenerator(*answers),
            RateLimiter(per_minute, per_day),
        )
        return TestClient(create_app(lambda: services))

    return make


def test_health_and_document_list(client_factory):
    with client_factory() as client:
        assert client.get("/healthz").json() == {"ok": True, "documents": 1, "chunks": 4}
        documents = client.get("/api/documents").json()
        assert documents == [{"document": "prices.pdf", "title": "Prices", "pages": 1, "url": "/documents/prices.pdf"}]


def test_ask_returns_answer_with_page_link(client_factory):
    with client_factory("Annual maintenance costs 189 euro net [1].") as client:
        response = client.post("/api/ask", json={"question": "Annual maintenance price for the LW 9?"})
    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["citations"][0]["url"] == "/documents/prices.pdf#page=1"
    assert body["citations"][0]["location"] == "p. 1"


@pytest.mark.parametrize("question", ["", "   ", "x" * 101])
def test_empty_or_too_long_question_is_rejected(client_factory, question):
    with client_factory() as client:
        response = client.post("/api/ask", json={"question": question})
    assert response.status_code == 422
    assert isinstance(response.json()["error"], str)


@pytest.mark.parametrize("body", [{}, {"question": 5}, ["question"]])
def test_malformed_request_gets_the_same_error_format(client_factory, body):
    with client_factory() as client:
        response = client.post("/api/ask", json=body)
    assert response.status_code == 422
    assert response.json() == {"error": 'Send JSON like {"question": "..."}.'}


def test_oversized_request_is_rejected_before_parsing(client_factory):
    with client_factory() as client:
        response = client.post("/api/ask", content=b"x" * 20_000, headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert "error" in response.json()


def test_rate_limit_returns_429(client_factory):
    with client_factory("A [1].", "B [1].", per_minute=1) as client:
        assert client.post("/api/ask", json={"question": "maintenance"}).status_code == 200
        response = client.post("/api/ask", json={"question": "maintenance"})
    assert response.status_code == 429
    assert "minute" in response.json()["error"]


def test_provider_failure_returns_503(client_factory):
    with client_factory(ProviderError("HTTP 503")) as client:
        response = client.post("/api/ask", json={"question": "maintenance"})
    assert response.status_code == 503


def test_question_text_is_not_logged(client_factory, caplog):
    secret_question = "my private address is Example Street 5"
    with caplog.at_level(logging.DEBUG), client_factory("NOT_FOUND\nNo.") as client:
        client.post("/api/ask", json={"question": secret_question})
    assert secret_question not in caplog.text
    assert "/api/ask" in caplog.text
