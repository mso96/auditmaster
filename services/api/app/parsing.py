"""Document text extraction.

The default parser is self-hosted and ships no model weights: PDF via pypdf
(one block per page), DOCX via python-docx (heading sections, tables in
reading order), and TXT/MD as text. Markdown headings become section labels.

Docling is a better fit for scanned pages and complex layout, but it
downloads model weights and pulls in PyTorch, which does not fit the small
air-gapped image. ``parse_document`` is the seam. A Docling backend can
replace the body later and should still return ``ParsedBlock`` values so
chunking and citations keep document, page, and section metadata.
"""

import io
import re
from dataclasses import dataclass
from pathlib import Path
from zipfile import BadZipFile

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader
from pypdf.errors import PdfReadError

_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")
_SUPPORTED = {".pdf", ".docx", ".txt", ".md", ".markdown"}


class ParseError(Exception):
    """The upload is not a readable PDF, DOCX, TXT, or Markdown file."""


@dataclass(frozen=True)
class ParsedBlock:
    text: str
    page: int | None
    section: str | None


def clean_filename(name: str | None) -> str:
    base = Path(name or "").name.replace("\x00", "").strip()
    if not base or base in {".", ".."}:
        raise ParseError("Dosya adı gerekli.")
    return base[:180]


def suffix_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def ensure_supported(filename: str) -> str:
    suffix = suffix_of(filename)
    if suffix not in _SUPPORTED:
        raise ParseError("Desteklenen türler: PDF, DOCX, TXT, MD.")
    return suffix


def parse_document(filename: str, data: bytes) -> list[ParsedBlock]:
    suffix = ensure_supported(filename)
    if suffix == ".pdf":
        blocks = _parse_pdf(data)
    elif suffix == ".docx":
        blocks = _parse_docx(data)
    else:
        text = _decode_text(data)
        blocks = _parse_markdown(text) if suffix in {".md", ".markdown"} else _parse_plain(text)
    blocks = [block for block in blocks if block.text.strip()]
    if not blocks:
        raise ParseError("Belgeden metin çıkarılamadı.")
    return blocks


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1254"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _parse_plain(text: str) -> list[ParsedBlock]:
    if "\f" not in text:
        return [ParsedBlock(text=text.strip(), page=None, section=None)]
    blocks: list[ParsedBlock] = []
    for index, part in enumerate(text.split("\f"), start=1):
        cleaned = part.strip()
        if cleaned:
            blocks.append(ParsedBlock(text=cleaned, page=index, section=None))
    return blocks


def _parse_markdown(text: str) -> list[ParsedBlock]:
    blocks: list[ParsedBlock] = []
    section: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        buffer.clear()
        if not body:
            return
        content = f"{section}\n{body}" if section else body
        blocks.append(ParsedBlock(text=content, page=None, section=section))

    for line in text.splitlines():
        match = _HEADING.match(line.strip())
        if match:
            flush()
            heading = match.group(1).strip()
            section = heading[:200] or section
            continue
        buffer.append(line)
    flush()
    return blocks


def _parse_pdf(data: bytes) -> list[ParsedBlock]:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ParseError("Şifreli PDF okunamadı.")
        blocks: list[ParsedBlock] = []
        for index, page in enumerate(reader.pages, start=1):
            extracted = page.extract_text() or ""
            cleaned = extracted.strip()
            if cleaned:
                blocks.append(ParsedBlock(text=cleaned, page=index, section=None))
        return blocks
    except ParseError:
        raise
    except PdfReadError as exc:
        raise ParseError("PDF okunamadı.") from exc


def _parse_docx(data: bytes) -> list[ParsedBlock]:
    try:
        document = Document(io.BytesIO(data))
    except (BadZipFile, ValueError) as exc:
        raise ParseError("DOCX dosyası okunamadı.") from exc

    blocks: list[ParsedBlock] = []
    section: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(part for part in buffer if part.strip()).strip()
        buffer.clear()
        if not body:
            return
        content = f"{section}\n{body}" if section else body
        blocks.append(ParsedBlock(text=content, page=None, section=section))

    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            paragraph = Paragraph(child, document)
            style_name = ""
            if paragraph.style is not None and paragraph.style.name:
                style_name = paragraph.style.name
            text = paragraph.text.strip()
            if style_name.startswith("Heading"):
                flush()
                if text:
                    section = text[:200]
                continue
            if text:
                buffer.append(text)
        elif child.tag == qn("w:tbl"):
            table = Table(child, document)
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                # Merged cells repeat the same text; keep first occurrence per row.
                unique: list[str] = []
                for cell in cells:
                    if cell not in unique:
                        unique.append(cell)
                if unique:
                    buffer.append(" | ".join(unique))
    flush()
    return blocks
