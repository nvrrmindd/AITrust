"""Web search for claims that came without a source ("Attack the answer" mode).
Tavily (real web search) if TAVILY_API_KEY is set; keyless fallback: Wikipedia ru + en."""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from urllib.parse import quote, urlparse

import httpx

from . import netsafe
from .config import settings
from .textutil import _CYR, _STOP

log = logging.getLogger("pruf.search")

_OFFICIAL_SUFFIX = (".gov", ".gov.kz", ".edu", ".edu.kz", ".int", ".mil", ".ac.uk", ".gov.uk", ".europa.eu", ".gc.ca")
_OFFICIAL = {
    "who.int", "un.org", "worldbank.org", "imf.org", "oecd.org", "stat.gov.kz", "adilet.zan.kz", "akorda.kz", "primeminister.kz",
    "mitre.org", "attack.mitre.org", "nist.gov", "cve.org", "ietf.org", "w3.org", "iso.org", "unesco.org",
    "nature.com", "science.org", "sciencedirect.com", "springer.com", "wiley.com", "arxiv.org", "doi.org",
    "ncbi.nlm.nih.gov", "pubmed.ncbi.nlm.nih.gov", "cdc.gov", "nih.gov", "esa.int", "nasa.gov",
}
_REFERENCE = {
    "wikipedia.org", "britannica.com", "learn.microsoft.com", "docs.microsoft.com", "developer.mozilla.org", "owasp.org",
    "docs.python.org", "cloud.google.com", "aws.amazon.com", "kaspersky.com", "cloudflare.com",
}
_MEDIA = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "theguardian.com", "nytimes.com", "ft.com", "bloomberg.com",
    "economist.com", "forbes.kz", "kursiv.media", "tengrinews.kz", "inform.kz", "kapital.kz", "interfax.ru", "rbc.ru",
}
TIER_RU = {"official": "официальный или научный источник", "reference": "справочник", "media": "СМИ", "other": "прочий сайт"}


def tier_of(domain: str) -> str:
    d = domain.lower().removeprefix("www.")

    def match(pool: set[str]) -> bool:
        return any(d == p or d.endswith("." + p) for p in pool)

    if match(_OFFICIAL) or d.endswith(_OFFICIAL_SUFFIX):
        return "official"
    if match(_REFERENCE):
        return "reference"
    if match(_MEDIA):
        return "media"
    return "other"


@dataclass
class Hit:
    url: str
    title: str
    snippet: str
    query: str
    adversarial: bool

    @property
    def domain(self) -> str:
        return (urlparse(self.url).hostname or "").removeprefix("www.")

    @property
    def tier(self) -> str:
        return tier_of(self.domain)


def provider() -> str:
    return "tavily" if settings.tavily_api_key else "wikipedia"


async def search(query: str, adversarial: bool, limit: int = 5) -> list[Hit]:
    try:
        if settings.tavily_api_key:
            return await _tavily(query, adversarial, limit)
        return await _wikipedia(query, adversarial)
    except (httpx.HTTPError, KeyError, ValueError) as e:
        log.warning("search failed for %r: %s", query, e)
        return []


async def _tavily(query: str, adversarial: bool, limit: int) -> list[Hit]:
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
            json={"api_key": settings.tavily_api_key, "query": query, "max_results": limit,
                  "search_depth": "advanced", "include_raw_content": True},
        )
    r.raise_for_status()
    hits = []
    for it in r.json().get("results", []):
        body = (it.get("raw_content") or it.get("content") or "")[:25000]
        if body:
            hits.append(Hit(it["url"], it.get("title", ""), body, query, adversarial))
    return hits


_ADVERSARIAL_WORDS = re.compile(
    r"\b(миф\w*|опроверж\w*|на самом деле|неверн\w*|ошибк\w*|правда ли|myth\w*|debunk\w*|actually|false|wrong|incorrect)\b", re.I)


def keywords(query: str, n: int = 5) -> str:
    """Wikipedia search ANDs every term, a whole sentence finds nothing. Keep IDs/numbers/names first, then longest words."""
    q = _ADVERSARIAL_WORDS.sub(" ", query)
    words = re.findall(r"[\w\-.&]+", q)
    words = [w.strip(".") for w in words if w.lower() not in _STOP and len(w.strip(".")) > 2]
    special = [w for w in words if re.search(r"\d", w) or w[:1].isupper()]
    rest = sorted([w for w in words if w not in special], key=len, reverse=True)
    out: list[str] = []
    for w in special + rest:
        if w.lower() not in (x.lower() for x in out):
            out.append(w)
    return " ".join(out[:n])


async def _wiki_search(lang: str, q: str, k: int = 2) -> list[str]:
    status, data = await netsafe.get_json(
        f"https://{lang}.wikipedia.org/w/api.php",
        {"action": "query", "list": "search", "srsearch": q, "srlimit": k, "format": "json"})
    return [s["title"] for s in (data or {}).get("query", {}).get("search", [])] if status == 200 else []


async def _wiki_page(lang: str, title: str) -> str:
    # TextExtracts returns full text of only ONE page per request
    status, data = await netsafe.get_json(
        f"https://{lang}.wikipedia.org/w/api.php",
        {"action": "query", "prop": "extracts", "explaintext": 1, "titles": title, "format": "json", "redirects": 1})
    pages = (data or {}).get("query", {}).get("pages", {}) if status == 200 else {}
    return next((p.get("extract", "") for p in pages.values()), "")


async def _wikipedia(query: str, adversarial: bool) -> list[Hit]:
    kw = keywords(query)
    if not kw:
        return []
    langs = ["ru", "en"] if _CYR.search(query) else ["en", "ru"]
    found = await asyncio.gather(*(_wiki_search(lang, kw) for lang in langs))
    pairs = [(lang, t) for lang, titles in zip(langs, found) for t in titles]
    if not pairs and len(kw.split()) > 2:
        short = " ".join(kw.split()[:2])
        found = await asyncio.gather(*(_wiki_search(lang, short) for lang in langs))
        pairs = [(lang, t) for lang, titles in zip(langs, found) for t in titles]
    texts = await asyncio.gather(*(_wiki_page(lang, t) for lang, t in pairs))
    return [
        Hit(f"https://{lang}.wikipedia.org/wiki/{quote(t.replace(' ', '_'))}", t, txt[:30000], query, adversarial)
        for (lang, t), txt in zip(pairs, texts) if txt
    ]


async def gather_evidence(queries: list[str]) -> list[Hit]:
    """queries[0] neutral, the rest adversarial. Dedupe by URL, authoritative sources first."""
    results = await asyncio.gather(*(search(q, adversarial=i > 0) for i, q in enumerate(queries[:3])))
    seen: dict[str, Hit] = {}
    for hits in results:
        for h in hits:
            if h.url not in seen:
                seen[h.url] = h
            elif h.adversarial:
                seen[h.url].adversarial = True
    order = {"official": 0, "reference": 1, "media": 2, "other": 3}
    return sorted(seen.values(), key=lambda h: order[h.tier])[:10]
