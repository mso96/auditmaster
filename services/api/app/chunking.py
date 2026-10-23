"""Split parsed blocks into citation-sized chunks.

Each chunk keeps the page and section of its block. Long blocks break on a
paragraph or sentence boundary when one exists, with a short overlap so a
citation near the cut is not stranded.
"""

import re
from dataclasses import dataclass

from app.parsing import ParsedBlock

CHUNK_SIZE = 900
CHUNK_OVERLAP = 120
MAX_CHUNKS = 400
_MIN_CHARS = 20


@dataclass(frozen=True)
class TextChunk:
    content: str
    page: int | None
    section: str | None
    index: int


def chunk_blocks(
    blocks: list[ParsedBlock],
    *,
    size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for block in blocks:
        for part in _split_text(block.text, size=size, overlap=overlap):
            cleaned = part.strip()
            if len(cleaned) < _MIN_CHARS:
                continue
            chunks.append(
                TextChunk(
                    content=cleaned,
                    page=block.page,
                    section=block.section,
                    index=len(chunks),
                )
            )
    if chunks or not blocks:
        return chunks
    text = "\n\n".join(block.text.strip() for block in blocks if block.text.strip()).strip()
    if not text:
        return []
    return [TextChunk(content=text, page=blocks[0].page, section=blocks[0].section, index=0)]


def _split_text(text: str, *, size: int, overlap: int) -> list[str]:
    collapsed = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(collapsed) <= size:
        return [collapsed] if collapsed else []
    parts: list[str] = []
    start = 0
    while start < len(collapsed):
        end = min(start + size, len(collapsed))
        if end < len(collapsed):
            window = collapsed[start:end]
            break_at = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(". "))
            if break_at > size // 2:
                end = start + break_at + 1
        piece = collapsed[start:end].strip()
        if piece:
            parts.append(piece)
        if end >= len(collapsed):
            break
        start = max(end - overlap, start + 1)
    return parts
