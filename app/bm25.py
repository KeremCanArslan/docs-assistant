"""Okapi BM25 keyword search. Catches exact identifiers the vector search can miss, such as error codes."""

from __future__ import annotations

import math
import re
from collections import Counter

TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
FOLD = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "s", "ı": "i", "ş": "s", "ğ": "g", "ç": "c"})


def tokenize(text: str) -> list[str]:
    return [t.lower().translate(FOLD) for t in TOKEN.findall(text)]


# Letters and digits in one token: error codes (E03), refrigerants (R290), breakers (C20), test points (A7, W35).
IDENTIFIER = re.compile(r"(?=.*[a-z])(?=.*\d)[a-z0-9]+")


def identifiers(text: str) -> list[str]:
    """Tokens that must match exactly. Plain words and plain numbers are left to the vector search."""
    return [t for t in tokenize(text) if IDENTIFIER.fullmatch(t)]


class BM25:
    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.docs = [Counter(tokenize(d)) for d in documents]
        self.lengths = [sum(c.values()) for c in self.docs]
        self.avg_length = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        frequency: Counter[str] = Counter()
        for counts in self.docs:
            frequency.update(counts.keys())
        n = len(self.docs)
        self.idf = {term: math.log(1 + (n - df + 0.5) / (df + 0.5)) for term, df in frequency.items()}

    def scores(self, query: str | list[str]) -> list[float]:
        """Scores every document for a query string or for a list of already tokenized terms."""
        terms = tokenize(query) if isinstance(query, str) else query
        result = []
        for counts, length in zip(self.docs, self.lengths, strict=True):
            score = 0.0
            norm = self.k1 * (1 - self.b + self.b * length / self.avg_length) if self.avg_length else self.k1
            for term in terms:
                tf = counts.get(term)
                if tf:
                    score += self.idf[term] * tf * (self.k1 + 1) / (tf + norm)
            result.append(score)
        return result
