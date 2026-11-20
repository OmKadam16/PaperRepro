"""Turn fetched bytes (PDF, JATS XML, HTML) into plain text. No network here."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET


class ParseError(RuntimeError):
    pass


def pdf_to_text(data: bytes) -> str:
    try:
        import pymupdf
    except ImportError as e:
        raise ParseError("PDF parsing needs the pdf extra: uv pip install -e '.[pdf]'") from e
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:
        raise ParseError(f"not a readable PDF: {e}") from e
    text = "\n".join(page.get_text() for page in doc)
    if len(text.strip()) < 200:
        raise ParseError("PDF has almost no extractable text (scanned image?)")
    return text


def _text(el: ET.Element) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def jats_to_text(data: bytes) -> str:
    """Flatten a JATS article (Europe PMC / bioRxiv source XML) into headed plain text."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ParseError(f"invalid JATS XML: {e}") from e
    out: list[str] = []
    title = root.find(".//article-title")
    if title is not None:
        out.append(f"TITLE: {_text(title)}")
    abstract = root.find(".//abstract")
    if abstract is not None:
        out.append(f"\n## Abstract\n{_text(abstract)}")
    body = root.find(".//body")
    if body is None:
        raise ParseError("JATS has no <body>: full text not included")
    for sec in body.iter("sec"):
        head = sec.find("title")
        paras = [_text(p) for p in sec.findall("p")]
        if head is not None or paras:
            out.append(f"\n## {_text(head) if head is not None else '(untitled)'}")
            out.extend(paras)
    for tw in root.iter("table-wrap"):
        cap = tw.find(".//caption")
        rows = ["\t".join(_text(c) for c in tr) for tr in tw.iter("tr")]
        out.append(f"\nTABLE: {_text(cap) if cap is not None else ''}\n" + "\n".join(rows))
    for fig in root.iter("fig"):
        cap = fig.find(".//caption")
        if cap is not None:
            out.append(f"\nFIGURE: {_text(cap)}")
    for ext in root.iter("ext-link"):
        href = ext.get("{http://www.w3.org/1999/xlink}href")
        if href:
            out.append(f"LINK: {href}")
    return "\n".join(out)


def html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
