"""Plain text out of an uploaded student paper: .docx, .pdf, .txt, .md."""
from __future__ import annotations

import io
import re
import zipfile

from .i18n import tr

MAX_BYTES = 10 * 1024 * 1024
MAX_CHARS = 60_000
FORMATS = (".docx", ".pdf", ".txt", ".md")


class DocumentError(Exception):
    """Message is shown to the user as is."""


def extract_text(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    ext = next((e for e in FORMATS if name.endswith(e)), "")
    if not ext:
        raise DocumentError(tr("doc.format"))
    if len(data) > MAX_BYTES:
        raise DocumentError(tr("doc.too_big"))
    if not data.strip():
        raise DocumentError(tr("doc.empty"))
    if ext == ".docx":
        text = _docx(data)
    elif ext == ".pdf":
        text = _pdf(data)
    else:
        text = _plain(data)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise DocumentError(tr("doc.no_text"))
    return text[:MAX_CHARS]


def _plain(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def _docx(data: bytes) -> str:
    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        doc = Document(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001
        raise DocumentError(tr("doc.docx_bad")) from e

    lines: list[str] = []
    # body in document order: paragraphs and tables interleaved
    for el in doc.element.body.iterchildren():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "p":
            lines.append(Paragraph(el, doc).text)
        elif tag == "tbl":
            for row in Table(el, doc).rows:
                cells = list(dict.fromkeys(c.text.strip() for c in row.cells))
                lines.append(" | ".join(c for c in cells if c))
    notes = _docx_notes(data)
    if notes:
        lines += ["", "Сноски", *notes]
    return "\n".join(lines)


def _docx_notes(data: bytes) -> list[str]:
    """python-docx has no footnote API; read word/footnotes.xml and endnotes.xml directly."""
    out: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for part in ("word/footnotes.xml", "word/endnotes.xml"):
                if part not in z.namelist():
                    continue
                xml = z.read(part).decode("utf-8", "replace")
                for note in re.findall(r"<w:(?:footnote|endnote)\b[^>]*>(.*?)</w:(?:footnote|endnote)>", xml, re.S):
                    t = "".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", note)).strip()
                    if t:
                        out.append(t)
    except zipfile.BadZipFile:
        pass
    return out


def _pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = [(p.extract_text() or "") for p in reader.pages[:200]]
    except Exception as e:  # noqa: BLE001
        raise DocumentError(tr("doc.pdf_bad")) from e
    text = "\n".join(pages)
    if len(re.sub(r"\s", "", text)) < 40:
        raise DocumentError(tr("doc.pdf_scan"))
    return text
