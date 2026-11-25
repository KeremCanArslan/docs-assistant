"""Builds, saves and loads the search index: chunks, their vectors and the keyword index.

The index is small (a few hundred chunks), so vectors live in a NumPy matrix and
search is one matrix-vector product. For tens of thousands of chunks the same
interface can be backed by pgvector, Qdrant or a similar vector store.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from app.bm25 import BM25
from app.chunking import Chunk, chunk_sections
from app.loaders import SUPPORTED, load_directory
from app.providers import Embedder


def documents_fingerprint(directory: Path) -> dict[str, str]:
    files = sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED)
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


@dataclass
class Index:
    chunks: list[Chunk]
    vectors: np.ndarray  # shape (len(chunks), dim), rows normalized
    embedder_name: str
    documents: dict[str, str]  # file name -> sha256

    def __post_init__(self) -> None:
        if len(self.chunks) != len(self.vectors):
            raise ValueError("chunks and vectors do not match")
        self.bm25 = BM25([c.embedding_text() for c in self.chunks])

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "vectors.npy", self.vectors.astype(np.float32))
        (directory / "chunks.json").write_text(
            json.dumps([asdict(c) for c in self.chunks], ensure_ascii=False, indent=1), encoding="utf-8"
        )
        manifest = {
            "embedder": self.embedder_name,
            "dimension": int(self.vectors.shape[1]) if self.vectors.size else 0,
            "chunks": len(self.chunks),
            "documents": self.documents,
            "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, directory: Path) -> Index:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        chunks = [Chunk(**item) for item in json.loads((directory / "chunks.json").read_text(encoding="utf-8"))]
        vectors = np.load(directory / "vectors.npy")
        return cls(chunks, vectors, manifest["embedder"], manifest["documents"])

    def is_stale(self, documents_dir: Path) -> bool:
        return self.documents != documents_fingerprint(documents_dir)


def build_index(documents_dir: Path, embedder: Embedder) -> Index:
    chunks = chunk_sections(load_directory(documents_dir))
    if not chunks:
        raise ValueError(f"No text found in {documents_dir}")
    vectors = embedder.embed_documents([c.embedding_text() for c in chunks])
    return Index(chunks, vectors, embedder.name, documents_fingerprint(documents_dir))
