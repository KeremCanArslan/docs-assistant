"""Turns PDF, DOCX, Markdown and HTML files into text sections with a page number or heading."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from docx import Document as DocxDocument
from pypdf import PdfReader

SUPPORTED = {".pdf", ".docx", ".md", ".markdown", ".html", ".htm", ".txt"}


@dataclass(frozen=True)
class Section:
    doc_id: str  # file name, used in links and citations
    title: str  # human readable document title
    text: str
    page: int | None = None  # 1-based page number for PDFs
    heading: str | None = None  # nearest heading for formats without pages


def _clean(text: str) -> str:
    # NFKC turns PDF ligatures such as "ﬂ" into plain letters, so "ﬂow" can be found as "flow".
    text = unicodedata.normalize("NFKC", text).replace("­", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _is_fragment(line: str) -> bool:
    words = line.split()
    if len(words) == 1 and re.fullmatch(r"\d+(?:\.\d+)*\.?", words[0]):
        return True  # heading number such as "3." or "3.1"
    return 0 < len(words) <= 3 and len(" ".join(words)) <= 25 and not line.rstrip().endswith((".", ":", ";", "!", "?"))


def _tidy_layout(text: str) -> str:
    """Cleans text from pypdf's layout mode.

    Layout mode keeps each table row on one line; wide gaps between columns become " | ".
    Some PDF generators place every word of a bold heading or table header separately,
    which comes out as one word per line; runs of such short lines are joined again.
    """
    lines: list[str] = []
    fragments: list[str] = []

    def flush() -> None:
        if fragments:
            lines.append(" ".join(" ".join(f.split()) for f in fragments))
            fragments.clear()

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            flush()
            lines.append("")
            continue
        line = re.sub(r"\s{3,}", " | ", line)
        if _is_fragment(line.replace(" | ", " ")):
            fragments.append(line.replace(" | ", " "))
            continue
        if fragments and len(fragments) > 1:
            flush()
        elif fragments:
            # a single short line directly before a longer one belongs to it (wrapped cell or heading number)
            line = f"{fragments.pop()} {line}"
        lines.append(line)
    flush()
    return "\n".join(lines)


def _load_pdf(path: Path) -> list[Section]:
    reader = PdfReader(path)
    meta_title = (reader.metadata.title if reader.metadata else None) or ""
    sections = []
    for number, page in enumerate(reader.pages, start=1):
        text = _clean(_tidy_layout(page.extract_text(extraction_mode="layout") or ""))
        if text:
            sections.append(Section(path.name, meta_title.strip() or path.stem, text, page=number))
    return sections


def _split_markdown(path: Path, raw: str) -> list[Section]:
    title = path.stem
    sections: list[Section] = []
    heading: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        text = _clean("\n".join(buffer))
        if text:
            sections.append(Section(path.name, title, text, heading=heading))
        buffer.clear()

    for line in raw.splitlines():
        if line.startswith("# ") and title == path.stem:
            title = line[2:].strip()
            continue
        match = re.match(r"#{2,6} (.+)", line)
        if match:
            flush()
            heading = match.group(1).strip()
            continue
        if line.strip() == "---":
            continue
        buffer.append(line)
    flush()
    return [Section(s.doc_id, title, s.text, heading=s.heading) for s in sections]


def _load_docx(path: Path) -> list[Section]:
    """Rebuilds the DOCX as Markdown-like text (headings, lists, table rows) and splits it by heading."""
    doc = DocxDocument(path)
    lines: list[str] = []
    body = doc.element.body
    paragraphs = {p._p: p for p in doc.paragraphs}
    tables = {t._tbl: t for t in doc.tables}
    for child in body.iterchildren():
        if child in paragraphs:
            para = paragraphs[child]
            text = para.text.strip()
            if not text:
                continue
            style = (para.style.name or "").lower() if para.style is not None else ""
            if style.startswith("heading 1") or style == "title":
                lines.append(f"# {text}")
            elif style.startswith("heading"):
                lines.append(f"## {text}")
            elif "list" in style:
                lines.append(f"- {text}")
            else:
                lines.append(text)
        elif child in tables:
            for row in tables[child].rows:
                lines.append(" | ".join(cell.text.strip() for cell in row.cells))
    return _split_markdown(path, "\n".join(lines))


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "head"}
    BLOCK = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "br", "table", "section"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" | ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def _load_html(path: Path) -> list[Section]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    title_match = re.search(r"<title>(.*?)</title>", raw, re.I | re.S)
    parser = _TextExtractor()
    parser.feed(raw)
    text = _clean("".join(parser.parts))
    title = _clean(title_match.group(1)) if title_match else path.stem
    return [Section(path.name, title, text)] if text else []


def load_document(path: Path) -> list[Section]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _load_pdf(path)
    if suffix == ".docx":
        return _load_docx(path)
    if suffix in (".md", ".markdown", ".txt"):
        return _split_markdown(path, path.read_text(encoding="utf-8", errors="replace"))
    if suffix in (".html", ".htm"):
        return _load_html(path)
    raise ValueError(f"Unsupported file type: {path.name}")


def load_directory(directory: Path) -> list[Section]:
    sections: list[Section] = []
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in SUPPORTED and not path.name.startswith("."):
            sections.extend(load_document(path))
    return sections
