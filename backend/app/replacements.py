"""Real works to cite instead of a source that does not exist.

OpenAlex search by keywords of the fake reference + the claim that leaned on it. A candidate is marked
"the abstract backs the claim" only when our judge returns a verified verbatim quote from the abstract;
otherwise it is just "similar topic, check yourself".
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

import httpx

from . import netsafe
from .config import settings
from .judge import judge_abstract
from .models import Citation, Claim, Replacement
from .search import keywords
from .sources import OPENALEX, openalex_abstract
from .textutil import _CYR

log = logging.getLogger("pruf.replacements")

TOP = 3


def _kw(text: str, n: int = 6) -> str:
    """Search keywords; unlike search.keywords, keeps short acronyms like "AI" or "ML"."""
    acr = list(dict.fromkeys(re.findall(r"\b[A-Z]{2}\b", text)))
    return " ".join(acr + keywords(text, n=n).split())


def queries(cit: Citation, claim: Optional[Claim]) -> list[str]:
    """OpenAlex ANDs the terms. Reference title + claim when they are in one language; a ru claim next to
    an en title finds junk, so then the title goes alone, and the claim alone is the last resort."""
    title_kw = _kw(cit.title or cit.raw)
    claim_kw = _kw(claim.text) if claim else ""
    same_lang = bool(_CYR.search(title_kw)) == bool(_CYR.search(claim_kw))
    out = ([f"{title_kw} {claim_kw}"] if title_kw and claim_kw and same_lang else []) + [title_kw, claim_kw]
    return [q.strip() for i, q in enumerate(out) if q.strip() and q not in out[:i]]


async def _search(q: str) -> Optional[list[dict]]:
    try:
        status, data = await netsafe.get_json(OPENALEX, {
            "search": q[:300], "filter": "has_doi:true,type:article", "per-page": 5,
            "sort": "relevance_score:desc", "mailto": settings.contact_email,
        })
    except httpx.HTTPError as e:
        log.warning("openalex search failed for %r: %s", q, e)
        return None
    return (data or {}).get("results", []) if status == 200 else None


def to_replacement(w: dict) -> Replacement:
    doi = (w.get("doi") or "").removeprefix("https://doi.org/") or None
    source = (w.get("primary_location") or {}).get("source") or {}
    authors = [a.get("author", {}).get("display_name", "") for a in w.get("authorships", [])]
    return Replacement(
        title=w.get("title") or w.get("display_name") or "",
        authors=[a for a in authors if a],
        year=w.get("publication_year"),
        venue=source.get("display_name"),
        doi=doi,
        url=f"https://doi.org/{doi}" if doi else w.get("id"),
        abstract=openalex_abstract(w),
        cited_by_count=int(w.get("cited_by_count") or 0),
        volume=(w.get("biblio") or {}).get("volume"),
        issue=(w.get("biblio") or {}).get("issue"),
        pages="–".join(p for p in ((w.get("biblio") or {}).get("first_page"), (w.get("biblio") or {}).get("last_page")) if p) or None,
    )


async def _confirm(rep: Replacement, claim: Claim) -> None:
    try:
        res = await judge_abstract(claim, rep.title, rep.abstract)
    except Exception:  # noqa: BLE001 - a replacement must never break the report
        log.exception("judging replacement %s failed", rep.doi)
        return
    quote = next((e.quote for e in res.evidence if e.quote_verified and e.stance == "supports"), None)
    if res.verdict == "supported" and quote:
        rep.confirmed, rep.quote = True, quote


async def find_replacements(cit: Citation, claim: Optional[Claim]) -> list[Replacement]:
    works: list[dict] = []
    for q in queries(cit, claim):
        works = await _search(q) or []
        if works:
            break
    reps = [to_replacement(w) for w in works if w.get("title") or w.get("display_name")][:TOP]
    if claim:
        await asyncio.gather(*(_confirm(r, claim) for r in reps if r.abstract))
    return reps
