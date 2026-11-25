"""Splits sections into overlapping chunks and keeps the nearest heading with each chunk."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.loaders import Section

# A numbered heading in extracted PDF text, e.g. "3.1 Mindestabstände" or "7. Connectivity".
HEADING = re.compile(r"^\d+(?:\.\d+)*\.?\s+\S.{0,80}$")


@dataclass(frozen=True)
class Chunk:
    id: str
    doc_id: str
    title: str
    text: str
    page: int | None
    heading: str | None

    def location(self) -> str:
        if self.page is not None:
            return f"p. {self.page}"
        return self.heading or ""

    def embedding_text(self) -> str:
        """Title and heading are prepended so a chunk is understandable on its own."""
        context = " / ".join(part for part in (self.title, self.heading) if part)
        return f"{context}\n{self.text}"


def _is_heading(line: str) -> bool:
    return bool(HEADING.match(line)) and not line.rstrip().endswith((".", ":", ";"))


def chunk_sections(sections: list[Section], max_chars: int = 900, overlap_lines: int = 2) -> list[Chunk]:
    """Packs whole lines into chunks of at most max_chars.

    Lines are never cut, so a table row stays together. The last lines of a chunk
    are repeated at the start of the next one so an answer that spans the border
    can still be found. A numbered heading starts a new chunk.
    """
    chunks: list[Chunk] = []
    counters: dict[str, int] = {}
    last_heading: dict[str, str | None] = {}

    def emit(section: Section, lines: list[str], heading: str | None) -> None:
        text = "\n".join(lines).strip()
        if not text:
            return
        n = counters.get(section.doc_id, 0)
        counters[section.doc_id] = n + 1
        chunks.append(Chunk(f"{section.doc_id}#{n}", section.doc_id, section.title, text, section.page, heading))

    for section in sections:
        heading = section.heading if section.heading is not None else last_heading.get(section.doc_id)
        current: list[str] = []
        current_heading = heading

        for raw_line in section.text.split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            if section.page is not None and _is_heading(line):
                if len(current) == 1 and current[0] == current_heading:
                    # the previous heading had no text of its own ("3. Setup" followed by "3.1 Clearances")
                    line = f"{current[0]} / {line}"
                else:
                    emit(section, current, current_heading)
                current = [line]
                heading = current_heading = line
                continue
            if current and len("\n".join(current)) + len(line) + 1 > max_chars:
                emit(section, current, current_heading)
                current = current[-overlap_lines:] if overlap_lines else []
                current_heading = heading
            current.append(line)
        emit(section, current, current_heading)
        last_heading[section.doc_id] = heading
    return chunks
