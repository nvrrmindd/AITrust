"""Turn an AI answer into claims + citations (LLM), then repair/augment with deterministic parsing."""
from __future__ import annotations

import re
from typing import Any

from . import llm
from .config import settings
from .models import Citation, Claim
from .prompts import EXTRACT_SYSTEM
from .textutil import certainty, clean_doi, find_dois, find_urls, locate


def _as_int(v: Any) -> int | None:
    try:
        return int(str(v)[:4])
    except (TypeError, ValueError):
        return None


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
        year=_as_int(raw.get("year")),
        venue=raw.get("venue") or None,
    )


async def extract(text: str) -> tuple[list[Claim], list[Citation]]:
    system = EXTRACT_SYSTEM.replace("{max_claims}", str(settings.max_claims))
    data = await llm.complete_json(system, f"Ответ ИИ:\n<<<\n{text}\n>>>", max_tokens=4000)

    citations = [_norm_citation(c, i + 1) for i, c in enumerate(data.get("citations") or [])]
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
    ids = {c.id for c in citations}

    claims: list[Claim] = []
    for i, c in enumerate((data.get("claims") or [])[: settings.max_claims]):
        span = str(c.get("span") or "").strip()
        ctext = str(c.get("text") or span).strip()
        if not ctext:
            continue
        start, end = locate(span, text)
        tone, markers = certainty(span or ctext)
        cids = [x for x in (c.get("citation_ids") or []) if x in ids]
        queries = [str(q) for q in (c.get("queries") or []) if str(q).strip()][:3]
        if not cids and not queries:
            queries = [ctext[:120]]
        claims.append(Claim(
            id=f"C{i + 1}", text=ctext, span=text[start:end] if start >= 0 else span, start=start, end=end,
            citation_ids=cids, certainty=tone, certainty_markers=markers, queries=queries,  # type: ignore[arg-type]
        ))
    return claims, citations
