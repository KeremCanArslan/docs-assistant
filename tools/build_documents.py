"""Builds the sample knowledge base in documents/ from tools/document_sources/.

HTML sources are printed to PDF with headless Chrome. The internal guideline is
written in Markdown and converted to DOCX with python-docx, so the knowledge base
contains PDF, DOCX and Markdown files like a real company share drive.

This script is only needed when the sample documents change. The built files are
committed, so the app and the tests never need Chrome.

    python tools/build_documents.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.shared import Pt

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "tools" / "document_sources"
OUT = ROOT / "documents"

CHROME_CANDIDATES = [
    os.environ.get("CHROME_BIN", ""),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome",
    "chromium",
    "chromium-browser",
]


def find_chrome() -> str:
    for candidate in CHROME_CANDIDATES:
        if not candidate:
            continue
        path = shutil.which(candidate) or (candidate if Path(candidate).exists() else None)
        if path:
            return path
    sys.exit("Chrome or Chromium not found. Set CHROME_BIN.")


def html_to_pdf(chrome: str, source: Path, target: Path) -> None:
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                f"--user-data-dir={profile}",
                "--no-pdf-header-footer",
                f"--print-to-pdf={target}",
                source.as_uri(),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
    if not target.exists() or target.stat().st_size == 0:
        sys.exit(f"PDF was not written: {target}")


def _add_table(doc: Document, rows: list[list[str]]) -> None:
    header, body = rows[0], rows[1:]
    table = doc.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    for cell, text in zip(table.rows[0].cells, header, strict=True):
        cell.text = text
        for run in cell.paragraphs[0].runs:
            run.bold = True
    for row in body:
        cells = table.add_row().cells
        for cell, text in zip(cells, row, strict=False):  # short rows leave the last cells empty
            cell.text = text


def markdown_to_docx(source: Path, target: Path) -> None:
    """Converts the small Markdown subset used in the guideline (headings, lists, tables)."""
    doc = Document()
    doc.styles["Normal"].font.size = Pt(10.5)
    table_rows: list[list[str]] = []

    def flush_table() -> None:
        if table_rows:
            _add_table(doc, table_rows)
            table_rows.clear()

    for raw in source.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not all(re.fullmatch(r"-{3,}", c) for c in cells):
                table_rows.append(cells)
            continue
        flush_table()
        if not line or line == "---":
            continue
        if line.startswith("# "):
            doc.add_heading(line[2:], level=1)
        elif line.startswith("## "):
            doc.add_heading(line[3:], level=2)
        elif line.startswith("- "):
            doc.add_paragraph(line[2:], style="List Bullet")
        elif re.match(r"\d+\. ", line):
            doc.add_paragraph(line.split(". ", 1)[1], style="List Number")
        else:
            doc.add_paragraph(line)
    flush_table()
    doc.core_properties.title = source.stem
    doc.core_properties.author = "Hollvik Wärmetechnik GmbH (fictional)"
    doc.save(target)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    chrome = find_chrome()
    for source in sorted(SOURCES.glob("*.html")):
        target = OUT / f"{source.stem}.pdf"
        html_to_pdf(chrome, source, target)
        print(f"PDF  {target.relative_to(ROOT)}")
    for source in sorted(SOURCES.glob("*.md")):
        target = OUT / f"{source.stem}.docx"
        markdown_to_docx(source, target)
        print(f"DOCX {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
