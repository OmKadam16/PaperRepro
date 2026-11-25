"""Citation styles, marker insertion and export. Deterministic: no LLM touches the output.

Styles: numbered ([1], Vancouver-like list), ieee ([1], IEEE list), apa ((Author, Year)).
Numbers follow first appearance in the draft; APA lists are alphabetical.
"""
from __future__ import annotations

import io
import re
import zipfile
from xml.sax.saxutils import escape

from paperrepro.state import Project, Source, Style

STYLE_NAMES = {"numbered": "Numbered [1]", "ieee": "IEEE", "apa": "APA 7"}
PARTICLES = {"van", "von", "de", "der", "den", "da", "di", "du", "la", "le", "del", "dos", "bin", "al"}


# ---------------------------------------------------------------- names
def split_name(full: str) -> tuple[str, list[str]]:
    """'Balaji Lakshminarayanan' -> ('Lakshminarayanan', ['B']); handles 'van der Waals'."""
    parts = [p for p in re.split(r"\s+", full.strip()) if p]
    if not parts:
        return "", []
    if "," in full:  # "Last, First"
        last, first = [x.strip() for x in full.split(",", 1)]
        return last, [w[0] for w in first.split() if w]
    i = len(parts) - 1
    while i > 0 and parts[i - 1].lower() in PARTICLES:
        i -= 1
    last = " ".join(parts[i:])
    initials = [w[0] for w in parts[:i] if w[0].isalpha()]
    return last, initials


def _initials(i: list[str], dots: bool = True, space: bool = True) -> str:
    return (" " if space else "").join(f"{c}." if dots else c for c in i)


# ---------------------------------------------------------------- references
def _tail(s: Source) -> str:
    return f"https://doi.org/{s.doi}" if s.doi else s.url


def ref_numbered(s: Source) -> str:
    names = [f"{last} {_initials(i, dots=False, space=False)}".strip() for last, i in map(split_name, s.authors)]
    who = ", ".join(names[:6]) + (", et al." if len(names) > 6 else "")
    bits = [f"{who}." if who else "", f"{s.title.rstrip('.')}.", f"{s.venue}." if s.venue else "",
            f"{s.year}." if s.year else "", _tail(s)]
    return " ".join(b for b in bits if b)


def ref_ieee(s: Source) -> str:
    names = [f"{_initials(i)} {last}".strip() for last, i in map(split_name, s.authors)]
    if len(names) > 6:
        who = f"{names[0]} et al."
    elif len(names) > 1:
        who = ", ".join(names[:-1]) + (", and " if len(names) > 2 else " and ") + names[-1]
    else:
        who = names[0] if names else ""
    bits = [f"{who}," if who else "", f"“{s.title.rstrip('.')},”",
            f"{s.venue}," if s.venue else "", f"{s.year}." if s.year else "",
            f"doi: {s.doi}." if s.doi else (s.url or "")]
    return " ".join(b for b in bits if b)


def ref_apa(s: Source) -> str:
    names = [f"{last}, {_initials(i)}".strip(", ") for last, i in map(split_name, s.authors)]
    if len(names) > 20:
        who = ", ".join(names[:19]) + ", ... " + names[-1]
    elif len(names) > 1:
        who = ", ".join(names[:-1]) + ", & " + names[-1]
    else:
        who = names[0] if names else s.title
    year = f"({s.year})." if s.year else "(n.d.)."
    title = s.title.rstrip(".") + "." if names else ""
    bits = [who, year, title, f"{s.venue}." if s.venue else "", _tail(s)]
    return " ".join(b for b in bits if b)


REF = {"numbered": ref_numbered, "ieee": ref_ieee, "apa": ref_apa}


def apa_in_text(s: Source) -> str:
    lasts = [split_name(a)[0] for a in s.authors]
    if not lasts:
        who = s.title.split(":")[0][:40]
    elif len(lasts) == 1:
        who = lasts[0]
    elif len(lasts) == 2:
        who = f"{lasts[0]} & {lasts[1]}"
    else:
        who = f"{lasts[0]} et al."
    return f"{who}, {s.year or 'n.d.'}"


# ---------------------------------------------------------------- numbering + markers
def numbering(project: Project) -> dict[str, int]:
    """Source id -> number, by first appearance in the draft."""
    nums: dict[str, int] = {}
    for p in project.draft.paragraphs:
        for s in p.sentences:
            for sid in project.chosen.get(s.id, []):
                if sid in project.sources and sid not in nums:
                    nums[sid] = len(nums) + 1
    return nums


def _compress(ns: list[int]) -> list[str]:
    """[1,2,3,5] -> ['1–3', '5']"""
    out, ns = [], sorted(set(ns))
    i = 0
    while i < len(ns):
        j = i
        while j + 1 < len(ns) and ns[j + 1] == ns[j] + 1:
            j += 1
        out.append(f"{ns[i]}–{ns[j]}" if j - i >= 2 else ", ".join(map(str, ns[i:j + 1])))
        i = j + 1
    return out


def marker(project: Project, sentence_id: str, style: Style, nums: dict[str, int]) -> str:
    ids = [i for i in project.chosen.get(sentence_id, []) if i in project.sources]
    if not ids:
        return ""
    if style == "apa":
        return "(" + "; ".join(apa_in_text(project.sources[i]) for i in ids) + ")"
    parts = _compress([nums[i] for i in ids])
    if style == "ieee":  # each number bracketed: [1], [3], [5]–[7]
        items = []
        for p in parts:
            if "–" in p:
                a, b = p.split("–")
                items.append(f"[{a}]–[{b}]")
            else:
                items.extend(f"[{x.strip()}]" for x in p.split(","))
        return ", ".join(items)
    return "[" + ", ".join(parts) + "]"


def insert_marker(sentence: str, mark: str) -> str:
    """Place the marker before the sentence's final punctuation: 'shown [1].'"""
    if not mark:
        return sentence
    m = re.search(r"([.!?;:]+[\"'”’)\]]*)\s*$", sentence)
    if m:
        return sentence[:m.start()].rstrip() + " " + mark + m.group(1)
    return sentence.rstrip() + " " + mark


# ---------------------------------------------------------------- rendering + export
def references(project: Project, style: Style) -> list[str]:
    nums = numbering(project)
    srcs = [project.sources[i] for i in nums]
    fmt = REF[style]
    if style == "apa":
        return sorted((fmt(s) for s in srcs), key=lambda r: r.lower())
    return [f"[{nums[s.id]}] {fmt(s)}" for s in srcs]


def rendered(project: Project, style: Style | None = None) -> list[tuple[str, str]]:
    """(kind, text) paragraphs with markers inserted, then the reference list."""
    style = style or project.style
    nums = numbering(project)
    out = []
    for p in project.draft.paragraphs:
        text = " ".join(insert_marker(s.text, marker(project, s.id, style, nums)) for s in p.sentences)
        out.append(("heading" if p.kind == "heading" else "body", text))
    refs = references(project, style)
    if refs:
        had = any(p.kind == "references" for p in project.draft.paragraphs)
        out.append(("heading", "Added references" if had else "References"))
        out.extend(("ref", r) for r in refs)
    return out


def to_text(project: Project, style: Style | None = None) -> str:
    return "\n\n".join(t for _, t in rendered(project, style)) + "\n"


_STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:pPr><w:spacing w:after="160" w:line="276" w:lineRule="auto"/></w:pPr><w:rPr><w:rFonts w:ascii="Georgia" w:hAnsi="Georgia"/><w:sz w:val="22"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Note"><w:name w:val="Note"/><w:basedOn w:val="Normal"/><w:rPr><w:i/><w:color w:val="6C6556"/><w:sz w:val="20"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Reference"><w:name w:val="Reference"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="567" w:hanging="567"/><w:spacing w:after="80"/></w:pPr><w:rPr><w:sz w:val="20"/></w:rPr></w:style>
</w:styles>"""
_CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""
_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""
_XML_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")  # not allowed in XML


def to_docx(project: Project, style: Style | None = None) -> bytes:
    return docx_bytes(rendered(project, style))


def docx_bytes(paragraphs: list[tuple[str, str]]) -> bytes:
    """(kind, text) -> a minimal valid .docx. kind: heading | body | ref | bullet."""
    body = []
    for kind, text in paragraphs:
        sty = {"heading": "Heading1", "ref": "Reference", "bullet": "Reference", "note": "Note"}.get(kind)
        ppr = f'<w:pPr><w:pStyle w:val="{sty}"/></w:pPr>' if sty else ""
        body.append(f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(_XML_BAD.sub("", text))}</w:t></w:r></w:p>')
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + "".join(body) + "</w:body></w:document>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        z.writestr("word/styles.xml", _STYLES_XML)
        z.writestr("word/document.xml", doc)
    return buf.getvalue()
