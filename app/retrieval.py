"""Hybrid search: vector similarity, plus exact keyword matching for codes and identifiers.

The vector search handles meaning and works across languages (an English question
finds a German page). BM25 keyword search is added only for identifier-like terms
in the question (E03, R290, C20, A7/W35), where an exact match matters more than
meaning. On the evaluation set, full-text BM25 fused with equal weight pulled
same-language but irrelevant chunks above the right cross-language chunk
(recall@5 93 % instead of 100 %), so it is restricted to identifiers.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.bm25 import identifiers
from app.chunking import Chunk
from app.index import Index
from app.providers import Embedder

RRF_K = 60  # constant from the reciprocal rank fusion paper (Cormack et al., 2009)
CANDIDATES = 20  # how many results each method contributes before fusion


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float  # fused RRF score
    similarity: float  # cosine similarity of the chunk to the question
    keyword_score: float  # BM25 score on the identifier terms, 0 when the question has none


def search(index: Index, embedder: Embedder, question: str, top_k: int = 5) -> list[Hit]:
    query_vector = embedder.embed_query(question)
    similarities = index.vectors @ query_vector
    terms = identifiers(question)
    keyword_scores = np.array(index.bm25.scores(terms)) if terms else np.zeros(len(index.chunks))

    rankings = [list(np.argsort(-similarities)[:CANDIDATES])]
    if terms:
        rankings.append([i for i in np.argsort(-keyword_scores)[:CANDIDATES] if keyword_scores[i] > 0])

    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, position in enumerate(ranking):
            fused[int(position)] = fused.get(int(position), 0.0) + 1.0 / (RRF_K + rank + 1)

    best = sorted(fused, key=lambda i: fused[i], reverse=True)[:top_k]
    return [Hit(index.chunks[i], fused[i], float(similarities[i]), float(keyword_scores[i])) for i in best]
