"""Web search for claims that came without a source ("Attack the answer" mode).

Tavily if TAVILY_API_KEY is set; otherwise Wikipedia (ru + en) as a free, keyless fallback."""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from . import netsafe
from .config import settings
from .textutil import _CYR

log = logging.getLogger("pruf.search")


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


async def search(query: str, adversarial: bool, limit: int = 4) -> list[Hit]:
    try:
        if settings.tavily_api_key:
            return await _tavily(query, adversarial, limit)
        return await _wikipedia(query, adversarial, limit)
    except (httpx.HTTPError, KeyError, ValueError) as e:
        log.warning("search failed for %r: %s", query, e)
        return []


async def _tavily(query: str, adversarial: bool, limit: int) -> list[Hit]:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
            json={"api_key": settings.tavily_api_key, "query": query, "max_results": limit,
                  "search_depth": "basic", "include_raw_content": True},
        )
    r.raise_for_status()
    hits = []
    for it in r.json().get("results", []):
        body = (it.get("raw_content") or it.get("content") or "")[:20000]
        hits.append(Hit(it["url"], it.get("title", ""), body, query, adversarial))
    return hits


async def _wikipedia(query: str, adversarial: bool, limit: int) -> list[Hit]:
    lang = "ru" if _CYR.search(query) else "en"
    api = f"https://{lang}.wikipedia.org/w/api.php"
    # adversarial phrasing ("миф", "опровержение") hurts Wikipedia search, strip it
    q = re.sub(r"\b(миф|опровержени\w*|на самом деле|myth|debunk\w*|actually|false)\b", "", query, flags=re.I).strip()
    status, data = await netsafe.get_json(api, {"action": "query", "list": "search", "srsearch": q, "srlimit": min(limit, 3), "format": "json"})
    titles = [s["title"] for s in (data or {}).get("query", {}).get("search", [])] if status == 200 else []
    if not titles:
        return []
    status, data = await netsafe.get_json(api, {
        "action": "query", "prop": "extracts", "explaintext": 1, "titles": "|".join(titles), "format": "json", "exlimit": len(titles),
    })
    pages = (data or {}).get("query", {}).get("pages", {}) if status == 200 else {}
    hits = []
    for p in pages.values():
        if p.get("extract"):
            url = f"https://{lang}.wikipedia.org/wiki/{p['title'].replace(' ', '_')}"
            hits.append(Hit(url, p["title"], p["extract"][:30000], query, adversarial))
    return hits


async def gather_evidence(queries: list[str]) -> list[Hit]:
    """queries[0] is neutral, the rest are adversarial. Dedupe by URL, keep adversarial flag if any."""
    results = await asyncio.gather(*(search(q, adversarial=i > 0) for i, q in enumerate(queries[:3])))
    seen: dict[str, Hit] = {}
    for hits in results:
        for h in hits:
            if h.url not in seen:
                seen[h.url] = h
            elif h.adversarial:
                seen[h.url].adversarial = True
    return list(seen.values())[:8]
