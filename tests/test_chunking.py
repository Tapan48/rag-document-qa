from app.ingestion.chunking import chunk_units
from app.ingestion.extraction import TextUnit


def _word_unit(word: str, count: int, source: dict) -> TextUnit:
    return TextUnit(text=" ".join([word] * count), source=source)


def test_chunk_units_returns_empty_list_for_no_units():
    assert chunk_units([]) == []


def test_chunk_units_single_small_unit_produces_one_chunk():
    units = [TextUnit(text="hello world", source={"kind": "line", "line": 1})]

    chunks = chunk_units(units, chunk_size=50, overlap=10)

    assert len(chunks) == 1
    assert chunks[0].position == 0
    assert "hello" in chunks[0].text and "world" in chunks[0].text
    assert chunks[0].metadata == {"lines": [1, 1]}


def test_chunk_units_splits_long_text_with_overlap():
    # ~300 "word" tokens (tiktoken may merge repeats, so just assert multiple chunks + overlap)
    units = [_word_unit("token", 300, {"kind": "page", "page": 1})]

    chunks = chunk_units(units, chunk_size=100, overlap=20)

    assert len(chunks) > 1
    assert [c.position for c in chunks] == list(range(len(chunks)))
    # every chunk should reference page 1, the only source
    assert all(c.metadata == {"pages": [1]} for c in chunks)


def test_chunk_units_is_deterministic():
    units = [_word_unit("token", 300, {"kind": "page", "page": 1})]

    first = chunk_units(units, chunk_size=100, overlap=20)
    second = chunk_units(units, chunk_size=100, overlap=20)

    assert [c.text for c in first] == [c.text for c in second]
    assert [c.metadata for c in first] == [c.metadata for c in second]


def test_chunk_units_merges_metadata_across_units():
    units = [
        TextUnit(text="short first page text", source={"kind": "page", "page": 1}),
        TextUnit(text="short second page text", source={"kind": "page", "page": 2}),
    ]

    chunks = chunk_units(units, chunk_size=100, overlap=0)

    assert len(chunks) == 1
    assert chunks[0].metadata == {"pages": [1, 2]}


def test_chunk_units_merges_paragraph_and_table_metadata():
    units = [
        TextUnit(text="a paragraph", source={"kind": "paragraph", "paragraph": 0}),
        TextUnit(text="a table row", source={"kind": "table_row", "table": 0, "row": 0}),
    ]

    chunks = chunk_units(units, chunk_size=100, overlap=0)

    assert len(chunks) == 1
    assert chunks[0].metadata == {
        "paragraphs": [0],
        "tables": [{"table": 0, "row": 0}],
    }
