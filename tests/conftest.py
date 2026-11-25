"""Test doubles: a deterministic embedder and a scripted generator, so no test needs network or an API key."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from app.bm25 import tokenize
from app.chunking import Chunk
from app.index import Index
from app.providers import ProviderError, normalize

ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS = ROOT / "documents"


class FakeEmbedder:
    """Hashed bag of words: texts that share words get similar vectors."""

    name = "fake/hash/64"

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim
        self.calls = 0

    def _vector(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dim, dtype=np.float32)
        for token in tokenize(text):
            digest = hashlib.md5(token.encode()).digest()
            vector[digest[0] % self.dim] += 1.0
        return vector

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        self.calls += 1
        return normalize(np.array([self._vector(t) for t in texts]))

    def embed_query(self, text: str) -> np.ndarray:
        self.calls += 1
        return normalize(self._vector(text)[None, :])[0]


class ScriptedGenerator:
    """Returns the given answers in order and records the prompts it received."""

    def __init__(self, *answers: str | Exception) -> None:
        self.answers = list(answers)
        self.prompts: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> tuple[str, str]:
        self.prompts.append((system, prompt))
        answer = self.answers.pop(0) if self.answers else "NOT_FOUND\nNo answer."
        if isinstance(answer, Exception):
            raise answer
        return answer, "scripted-model"


def make_chunk(n: int, text: str, doc: str = "manual.pdf", page: int | None = 1, heading: str | None = None) -> Chunk:
    return Chunk(f"{doc}#{n}", doc, doc.rsplit(".", 1)[0].title(), text, page, heading)


@pytest.fixture
def small_index() -> tuple[Index, FakeEmbedder]:
    chunks = [
        make_chunk(0, "Annual maintenance costs 189 euro net for the LW 6 and LW 9.", "prices.pdf", 1),
        make_chunk(1, "Error E03 means the water flow is too low. Clean the dirt filter.", "manual.pdf", 3),
        make_chunk(2, "Compressor warranty: 10 years if the unit is registered within 60 days.", "warranty.pdf", 1),
        make_chunk(3, "Night mode reduces noise between 22:00 and 06:00.", "faq.md", None, "Is it loud at night?"),
    ]
    embedder = FakeEmbedder()
    vectors = embedder.embed_documents([c.embedding_text() for c in chunks])
    return Index(chunks, vectors, embedder.name, {"prices.pdf": "x"}), embedder


@pytest.fixture
def provider_error() -> ProviderError:
    return ProviderError("HTTP 503")
