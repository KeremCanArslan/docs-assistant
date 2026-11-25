from pathlib import Path

import pytest
from conftest import DOCUMENTS

from app.loaders import _tidy_layout, load_directory, load_document


def test_pdf_keeps_page_numbers_and_table_rows():
    sections = load_document(DOCUMENTS / "datasheet-lw-series-en.pdf")
    assert [s.page for s in sections] == list(range(1, len(sections) + 1))
    first_page = sections[0].text
    assert "Heating capacity A7/W35 | 6.1 kW | 8.8 kW | 12.2 kW" in first_page
    assert sections[0].title.startswith("Hollvik LW series")


def test_pdf_ligatures_become_plain_letters():
    text = "\n".join(s.text for s in load_document(DOCUMENTS / "datasheet-lw-series-en.pdf"))
    assert "ﬂ" not in text and "ﬁ" not in text
    assert "flow temperature" in text


def test_docx_keeps_headings_and_table_rows():
    sections = load_document(DOCUMENTS / "serviceanweisung-sa07-de.docx")
    priorities = next(s for s in sections if s.heading == "2. Prioritäten")
    assert "P1 | Kompletter Heizungsausfall" in priorities.text
    assert all(s.page is None for s in sections)


def test_markdown_is_split_by_heading(tmp_path: Path):
    path = tmp_path / "faq.md"
    path.write_text("# Product FAQ\n\nIntro line.\n\n## First question?\n\nAnswer one.\n\n## Second?\n\nAnswer two.\n")
    sections = load_document(path)
    assert [s.heading for s in sections] == [None, "First question?", "Second?"]
    assert {s.title for s in sections} == {"Product FAQ"}
    assert sections[2].text == "Answer two."


def test_html_ignores_scripts_and_styles(tmp_path: Path):
    path = tmp_path / "page.html"
    path.write_text(
        "<html><head><title>Opening hours</title><style>p{color:red}</style></head>"
        "<body><script>var secret = 1;</script><p>Open Monday to Friday.</p></body></html>"
    )
    [section] = load_document(path)
    assert section.title == "Opening hours"
    assert "Open Monday to Friday." in section.text
    assert "secret" not in section.text and "color" not in section.text


def test_unsupported_file_type_is_rejected(tmp_path: Path):
    path = tmp_path / "data.xlsx"
    path.write_bytes(b"not really excel")
    with pytest.raises(ValueError, match="Unsupported"):
        load_document(path)


def test_directory_loads_every_supported_file_and_skips_others(tmp_path: Path):
    (tmp_path / "a.md").write_text("# A\n\nText A.")
    (tmp_path / "b.txt").write_text("Text B.")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    (tmp_path / ".hidden.md").write_text("hidden")
    assert sorted(s.doc_id for s in load_directory(tmp_path)) == ["a.md", "b.txt"]


def test_layout_cleanup_joins_split_headings_and_marks_columns():
    raw = "1.\nPerformance\ndata\n\n Model        LW\n6      LW\n9\n\n COP A7/W35        5.0        4.9\n"
    lines = [line for line in _tidy_layout(raw).splitlines() if line]
    assert lines[0] == "1. Performance data"
    assert lines[1] == "Model LW 6 LW 9"
    assert lines[2] == "COP A7/W35 | 5.0 | 4.9"
