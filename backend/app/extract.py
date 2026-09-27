"""Turn an AI answer into claims + citations (LLM), then repair/augment with deterministic parsing."""
from __future__ import annotations

import re
from typing import Any

from . import llm
from .config import settings
from .models import Citation, Claim
from .prompts import EXTRACT_SYSTEM
from .textutil import certainty, clean_doi, find_dois, find_urls, locate, normalize


def _as_int(v: Any) -> int | None:
    try:
        return int(str(v)[:4])
    except (TypeError, ValueError):
        return None


def _year_in(text: str) -> int | None:
    m = re.search(r"\b(19[5-9]\d|20[0-4]\d)\b", text)
    return int(m.group(1)) if m else None


def _norm_citation(raw: dict, idx: int) -> Citation:
    url = (raw.get("url") or "").strip() or None
    doi = (raw.get("doi") or "").strip() or None
    if url and re.search(r"doi\.org/", url, re.I):
        doi = doi or clean_doi(url)
    if doi:
        doi = clean_doi(doi)
    kind = raw.get("kind") if raw.get("kind") in ("academic", "web", "book", "law", "other") else "other"
    if doi and kind == "other":
        kind = "academic"
    authors = raw.get("authors") or []
    if isinstance(authors, str):
        authors = [a.strip() for a in re.split(r";|,(?=\s*[A-ZА-Я])| and | и ", authors) if a.strip()]
    return Citation(
        id=str(raw.get("id") or f"S{idx}"),
        raw=str(raw.get("raw") or "").strip(),
        kind=kind,
        url=url,
        doi=doi,
        title=(raw.get("title") or None),
        authors=[str(a) for a in authors][:12],
        year=_as_int(raw.get("year")) or _year_in(str(raw.get("raw") or "")),
        venue=raw.get("venue") or None,
    )


_REF_LINE = re.compile(r"^\s*\[(\d{1,3})\]\s*(.+)$", re.M)
_MARKER = re.compile(r"\[(\d{1,3}(?:\s*[,;–-]\s*\d{1,3})*)\]")
_SENT_TAIL = re.compile(r"[^\n]*?(?:[.!?](?=\s|$)|$)")


def _marker_numbers(s: str) -> list[int]:
    out: list[int] = []
    for m in _MARKER.finditer(s):
        for part in re.split(r"\s*[,;]\s*", m.group(1)):
            ends = [int(x) for x in re.split(r"\s*[–-]\s*", part)]
            lo, hi = ends[0], ends[-1]
            out.extend(range(lo, min(hi, lo + 20) + 1))
    return out


def _renumber(citations: list[Citation], text: str) -> dict[str, str]:
    """The LLM sometimes reuses ids (two sources both "S2"). Give ids from the numbered reference list ([n] -> Sn)
    when the answer has one, make every id unique, return first-seen old id -> new id."""
    refs = {int(m.group(1)): m.group(2).lower() for m in _REF_LINE.finditer(text)}
    used: set[str] = set()
    old_to_new: dict[str, str] = {}
    pending: list[Citation] = []
    def same(c: Citation, line: str) -> bool:
        if (c.url and c.url.lower() in line) or (c.doi and c.doi.lower() in line):
            return True
        # no URL/DOI: match by title or by the start of the raw reference text
        probes = [p for p in (c.title, c.raw[:60] if c.raw else None) if p and len(p) >= 15]
        return any(normalize(p) in normalize(line) for p in probes)

    for c in citations:
        n = next((n for n, line in refs.items() if f"S{n}" not in used and same(c, line)), None)
        if n is None:
            pending.append(c)
            continue
        old_to_new.setdefault(c.id, f"S{n}")
        c.id = f"S{n}"
        used.add(c.id)
    k = 0
    for c in pending:
        new = c.id if c.id not in used and re.fullmatch(r"S\d+", c.id) else ""
        while not new:
            k += 1
            new = f"S{k}" if f"S{k}" not in used and k not in refs else ""
        old_to_new.setdefault(c.id, new)
        c.id = new
        used.add(new)
    return old_to_new


async def extract(text: str) -> tuple[list[Claim], list[Citation]]:
    system = EXTRACT_SYSTEM.replace("{max_claims}", str(settings.max_claims))
    data = await llm.complete_json(system, f"Ответ ИИ:\n<<<\n{text}\n>>>", max_tokens=4000, role="extract")

    citations = [_norm_citation(c, i + 1) for i, c in enumerate(data.get("citations") or [])]
    # "по данным Бюро национальной статистики" is an attribution, not a findable work: no URL, no DOI, no year.
    # Such claims are checked by web search (attack mode) instead of a registry lookup that can only fail.
    citations = [c for c in citations if c.url or c.doi or c.year]
    ids = {c.id for c in citations}

    # safety net: every URL / DOI literally present in the text must become a citation
    known_urls = {c.url for c in citations if c.url}
    known_dois = {c.doi.lower() for c in citations if c.doi}
    n = len(citations)
    for doi in find_dois(text):
        if doi.lower() not in known_dois:
            n += 1
            citations.append(Citation(id=f"S{n}", raw=doi, kind="academic", doi=doi))
            known_dois.add(doi.lower())
    for url in find_urls(text):
        if "doi.org/" in url.lower():
            continue
        if url not in known_urls:
            n += 1
            citations.append(Citation(id=f"S{n}", raw=url, kind="web", url=url))
            known_urls.add(url)
    id_map = _renumber(citations, text)
    ids = {c.id for c in citations}

    claims: list[Claim] = []
    for i, c in enumerate((data.get("claims") or [])[: settings.max_claims]):
        span = str(c.get("span") or "").strip()
        ctext = str(c.get("text") or span).strip()
        if not ctext:
            continue
        start, end = locate(span, text)
        tone, markers = certainty(span or ctext)
        cids = [id_map.get(x, x) for x in (c.get("citation_ids") or [])]
        if start >= 0:
            # explicit [n] markers in the claim's sentence beat whatever the LLM linked
            tail = _SENT_TAIL.match(text, end)
            marked = [f"S{n}" for n in _marker_numbers(text[start:tail.end() if tail else end])]
            if any(m in ids for m in marked):
                cids = marked
        cids = list(dict.fromkeys(x for x in cids if x in ids))
        queries = [str(q) for q in (c.get("queries") or []) if str(q).strip()][:3]
        if not cids and not queries:
            queries = [ctext[:120]]
        claims.append(Claim(
            id=f"C{i + 1}", text=ctext, span=text[start:end] if start >= 0 else span, start=start, end=end,
            citation_ids=cids, certainty=tone, certainty_markers=markers, queries=queries,  # type: ignore[arg-type]
        ))
    return claims, citations
