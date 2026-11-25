from app.bm25 import BM25, identifiers, tokenize
from app.chunking import chunk_sections
from app.loaders import Section


def section(text: str, page: int | None = 1, heading: str | None = None) -> Section:
    return Section("doc.pdf", "Doc", text, page=page, heading=heading)


def test_numbered_heading_starts_a_new_chunk_and_is_kept():
    text = "Intro text.\n1. Safety\nNo ignition sources.\n2. Transport\nUpright only."
    chunks = chunk_sections([section(text)])
    assert [c.heading for c in chunks] == [None, "1. Safety", "2. Transport"]
    assert chunks[1].text == "1. Safety\nNo ignition sources."


def test_heading_without_own_text_is_merged_into_the_next():
    chunks = chunk_sections([section("3. Setup\n3.1 Clearances\nFront 1.5 m")])
    assert len(chunks) == 1
    assert chunks[0].heading == "3. Setup / 3.1 Clearances"


def test_long_text_is_split_on_line_borders_with_overlap():
    lines = [f"Line {i} " + "x" * 80 for i in range(30)]
    chunks = chunk_sections([section("\n".join(lines), page=None)], max_chars=400, overlap_lines=2)
    assert len(chunks) > 1
    assert all(len(c.text) <= 400 for c in chunks)
    first, second = chunks[0].text.splitlines(), chunks[1].text.splitlines()
    assert second[:2] == first[-2:]
    assert len({c.id for c in chunks}) == len(chunks)


def test_heading_carries_over_to_the_next_page():
    chunks = chunk_sections([section("4. Wiring\nUse a type A RCD.", page=1), section("Cable 2.5 mm2.", page=2)])
    assert chunks[-1].page == 2
    assert chunks[-1].heading == "4. Wiring"


def test_embedding_text_includes_title_and_heading():
    [chunk] = chunk_sections([section("Night mode is quiet.", page=None, heading="Noise")])
    assert chunk.embedding_text() == "Doc / Noise\nNight mode is quiet."


def test_tokenizer_folds_umlauts_and_turkish_letters():
    assert tokenize("Störungscode für Isı") == ["storungscode", "fur", "isi"]


def test_identifiers_are_codes_with_letters_and_digits():
    assert identifiers("What does E03 mean at A7/W35?") == ["e03", "a7", "w35"]
    assert identifiers("How loud is the LW 9 at 3 metres?") == []


def test_bm25_ranks_the_document_with_the_rare_code_first():
    bm25 = BM25(["Error E03: flow too low.", "Error E12: compressor too hot.", "General error handling."])
    scores = bm25.scores(["e12"])
    assert scores.index(max(scores)) == 1
    assert scores[2] == 0
