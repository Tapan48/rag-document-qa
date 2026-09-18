from dataclasses import dataclass

import tiktoken

from app.config import settings
from app.ingestion.extraction import TextUnit

_ENCODING = tiktoken.get_encoding("cl100k_base")


@dataclass
class Chunk:
    position: int
    text: str
    metadata: dict


def chunk_units(
    units: list[TextUnit],
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[Chunk]:
    chunk_size = chunk_size if chunk_size is not None else settings.chunk_size_tokens
    overlap = overlap if overlap is not None else settings.chunk_overlap_tokens
    step = max(chunk_size - overlap, 1)

    all_tokens: list[int] = []
    unit_bounds: list[tuple[int, int]] = []
    for unit in units:
        tokens = _ENCODING.encode(unit.text)
        start = len(all_tokens)
        all_tokens.extend(tokens)
        unit_bounds.append((start, len(all_tokens)))

    if not all_tokens:
        return []

    chunks = []
    position = 0
    start = 0
    total = len(all_tokens)
    while start < total:
        end = min(start + chunk_size, total)
        text = _ENCODING.decode(all_tokens[start:end])

        covered_sources = [
            units[i].source
            for i, (u_start, u_end) in enumerate(unit_bounds)
            if u_start < end and u_end > start
        ]
        chunks.append(Chunk(position=position, text=text, metadata=_merge_sources(covered_sources)))
        position += 1

        if end == total:
            break
        start += step

    return chunks


def _merge_sources(sources: list[dict]) -> dict:
    if not sources:
        return {}

    kind = sources[0]["kind"]
    if kind == "page":
        pages = sorted({s["page"] for s in sources})
        return {"pages": pages}
    if kind == "line":
        lines = sorted({s["line"] for s in sources})
        return {"lines": [lines[0], lines[-1]]}

    paragraphs = sorted({s["paragraph"] for s in sources if s["kind"] == "paragraph"})
    tables = sorted({(s["table"], s["row"]) for s in sources if s["kind"] == "table_row"})
    metadata: dict = {}
    if paragraphs:
        metadata["paragraphs"] = paragraphs
    if tables:
        metadata["tables"] = [{"table": t, "row": r} for t, r in tables]
    return metadata
