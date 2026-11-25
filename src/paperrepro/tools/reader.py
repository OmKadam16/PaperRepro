"""Turn an uploaded draft into paragraphs. No network, no LLM.

PDF pages with a text layer are read exactly; pages without one (scans, photos) are
returned as PNG images for the OCR helper. Word files are read from their XML directly.
"""
from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field

MAX_BYTES = 25 * 1024 * 1024
MIN_PAGE_CHARS = 40  # below this a PDF page is treated as a scan
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class ReadError(RuntimeError):
    pass


@dataclass
class RawDoc:
    blocks: list[tuple[str, str]] = field(default_factory=list)  # (kind, text) kind: heading|body
    scans: dict[int, bytes] = field(default_factory=dict)  # 1-based page -> PNG, needs OCR
    page_of_block: list[int] = field(default_factory=list)  # for PDFs: page each block came from


def _clean(text: str) -> str:
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # re-join words hyphenated across lines
    return re.sub(r"\s+", " ", text).strip()


def looks_like_heading(text: str) -> bool:
    t = text.strip()
    if not t or len(t) > 90 or t.endswith((".", ",", ";", ":")):
        return False
    if re.match(r"^(\d+(\.\d+)*|[IVX]+\.|[A-Z]\.)\s+\S", t):
        return True
    return len(t.split()) <= 8 and (t.istitle() or t.isupper())


def read_pdf(data: bytes) -> RawDoc:
    try:
        import pymupdf
    except ImportError as e:
        raise ReadError("PDF support needs the pdf extra: uv pip install -e '.[pdf]'") from e
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:
        raise ReadError(f"not a readable PDF: {e}") from e
    raw = RawDoc()
    for i, page in enumerate(doc, start=1):
        if len(page.get_text().strip()) < MIN_PAGE_CHARS:
            raw.scans[i] = page.get_pixmap(dpi=150).tobytes("png")
            raw.blocks.append(("ocr", f"__OCR_PAGE_{i}__"))
            raw.page_of_block.append(i)
            continue
        for b in page.get_text("blocks"):
            if b[6] != 0:  # image block
                continue
            text = _clean(b[4])
            if len(text) < 2 or re.fullmatch(r"\d{1,4}", text):  # page numbers
                continue
            raw.blocks.append(("heading" if looks_like_heading(text) else "body", text))
            raw.page_of_block.append(i)
    if not raw.blocks:
        raise ReadError("the PDF has no pages")
    return raw


def read_docx(data: bytes) -> RawDoc:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as e:
        raise ReadError("not a readable Word (.docx) file") from e
    root = ET.fromstring(xml)
    raw = RawDoc()
    for p in root.iter(f"{W}p"):
        text = _clean("".join(t.text or "" for t in p.iter(f"{W}t")))
        if not text:
            continue
        style = p.find(f"{W}pPr/{W}pStyle")
        name = (style.get(f"{W}val") if style is not None else "") or ""
        is_heading = name.lower().startswith(("heading", "title")) or looks_like_heading(text)
        raw.blocks.append(("heading" if is_heading else "body", text))
    if not raw.blocks:
        raise ReadError("the Word file has no text")
    return raw


def read_text(data: bytes) -> RawDoc:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    raw = RawDoc()
    for chunk in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        line = chunk.strip()
        if not line:
            continue
        if line.startswith("#"):
            raw.blocks.append(("heading", line.lstrip("#").strip()))
        else:
            kind = "heading" if "\n" not in line and looks_like_heading(line) else "body"
            raw.blocks.append((kind, _clean(line)))
    if not raw.blocks:
        raise ReadError("the text is empty")
    return raw


def read_upload(filename: str, data: bytes) -> RawDoc:
    if not data:
        raise ReadError("the file is empty")
    if len(data) > MAX_BYTES:
        raise ReadError(f"files up to {MAX_BYTES // (1024 * 1024)} MB, please")
    name = filename.lower()
    if name.endswith(".pdf") or data[:4] == b"%PDF":
        return read_pdf(data)
    if name.endswith(".docx") or data[:2] == b"PK":
        return read_docx(data)
    if name.endswith((".txt", ".md", ".markdown", ".tex")) or "." not in name:
        return read_text(data)
    raise ReadError("upload a PDF, a Word file (.docx), or plain text (.txt, .md)")
