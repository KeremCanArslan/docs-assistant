"""Builds the search index from the files in the documents directory.

    python -m app.ingest

Run it again whenever a document is added, changed or removed.
"""

from __future__ import annotations

import sys

from app.config import Settings
from app.index import build_index
from app.providers import ProviderError, build_embedder


def main() -> int:
    settings = Settings.from_env()
    try:
        embedder = build_embedder(settings)
        index = build_index(settings.documents_dir, embedder)
    except (ProviderError, ValueError) as exc:
        print(f"Index not built: {exc}", file=sys.stderr)
        return 1
    index.save(settings.index_dir)
    print(f"{len(index.documents)} documents, {len(index.chunks)} chunks -> {settings.index_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
