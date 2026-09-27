"""Does the cited source exist, and what does it actually say?

Existence is decided deterministically (doi.org handle registry, Crossref, OpenAlex, HTTP status),
never by an LLM. Every status carries a human-readable explanation.
"""
from __future__ import annotations

import asyncio
import io
import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup
from rapidfuzz import fuzz

from . import netsafe
from .models import Citation, MatchedRecord, SourceCheck
from .i18n import tr
from .textutil import normalize

log = logging.getLogger("pruf.sources")
logging.getLogger("pypdf").setLevel(logging.ERROR)  # font-encoding chatter on journal PDFs

CROSSREF = "https://api.crossref.org/works"
OPENALEX = "https://api.openalex.org/works"
DOI_HANDLE = "https://doi.org/api/handles/"

SOFT_404 = re.compile(r"\b(404|page not found|not found|страница не найдена|не найдено|ошибка 404)\b", re.I)


@dataclass
class SourceText:
    text: str
    scope: str  # "full" | "abstract" | "none"
    url: Optional[str] = None


# ------------------------------------------------------------------ helpers

def _bare_title(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", normalize(t))).strip()


def title_similarity(a: Optional[str], b: Optional[str]) -> int:
    if not a or not b:
        return 0
    na, nb = _bare_title(a), _bare_title(b)
    short, long_ = sorted((na, nb), key=len)
    if len(short) >= 20 and long_.startswith(short):
        return 100  # subtitle dropped or added: same work
    main_a, main_b = (_bare_title(re.split(r"[:?.]|\s[-–—]\s", t, maxsplit=1)[0]) for t in (a, b))
    if min(len(main_a), len(main_b)) >= 20 and main_a == main_b:
        return 90  # same main title, the subtitle differs
    return int(fuzz.token_sort_ratio(na, nb))


def _surname(author: str) -> str:
    a = author.replace(",", " ").strip()
    parts = [p for p in re.split(r"\s+", a) if len(p.strip(".")) > 1]
    return normalize(parts[0]) if parts else ""


def compare_metadata(cit: Citation, rec: MatchedRecord) -> list[str]:
    """Human-readable differences between what the AI cited and what really exists."""
    diffs: list[str] = []
    if cit.year and rec.year and abs(cit.year - rec.year) > 1:
        diffs.append(tr("diff.year", a=cit.year, b=rec.year))
    if cit.authors and rec.authors:
        real = {_surname(a) for a in rec.authors}
        real_full = normalize(" ".join(rec.authors))
        cited = [_surname(a) for a in cit.authors if _surname(a)]
        missing = [a for a in cited if a not in real and a not in real_full]
        if cited and len(missing) == len(cited):
            diffs.append(tr("diff.authors", a=", ".join(cit.authors[:3]), b=", ".join(rec.authors[:3])))
    if cit.title and rec.title and title_similarity(cit.title, rec.title) < 80:
        diffs.append(tr("diff.title", b=rec.title))
    return diffs


def _crossref_record(item: dict) -> MatchedRecord:
    title = (item.get("title") or [None])[0]
    authors = [f"{a.get('family', '')} {a.get('given', '')[:1]}.".strip() for a in item.get("author", []) if a.get("family")]
    year = None
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            year = int(parts[0][0])
            break
    venue = (item.get("container-title") or [None])[0]
    url = f"https://doi.org/{item['DOI']}" if item.get("DOI") else item.get("URL")
    return MatchedRecord(title=title, authors=authors, year=year, venue=venue, url=url)


def _openalex_record(w: dict) -> MatchedRecord:
    authors = [a.get("author", {}).get("display_name", "") for a in w.get("authorships", [])]
    loc = (w.get("primary_location") or {}).get("source") or {}
    url = w.get("doi") or (w.get("primary_location") or {}).get("landing_page_url") or w.get("id")
    return MatchedRecord(title=w.get("title"), authors=[a for a in authors if a], year=w.get("publication_year"),
                         venue=loc.get("display_name"), url=url)


def openalex_abstract(w: dict) -> str:
    inv = w.get("abstract_inverted_index") or {}
    if not inv:
        return ""
    pos: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        pos.extend((i, word) for i in idxs)
    return " ".join(w for _, w in sorted(pos))


def _strip_jats(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def html_to_text(html: bytes, url: str = "") -> tuple[str, str]:
    """Returns (main_text, page_title)."""
    raw = html.decode("utf-8", errors="ignore")
    title = ""
    try:
        soup = BeautifulSoup(raw, "lxml")
        title = (soup.title.string or "").strip() if soup.title else ""
    except Exception:  # noqa: BLE001
        soup = None
    text = trafilatura.extract(raw, url=url or None, include_comments=False, include_tables=True, favor_recall=True) or ""
    if len(text) < 400 and soup is not None:
        for t in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            t.decompose()
        text = re.sub(r"\n\s*\n+", "\n\n", soup.get_text("\n")).strip()
    return text, title


def pdf_to_text(data: bytes, max_pages: int = 25) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages[:max_pages])


# ------------------------------------------------------------------ fetchers

async def _mirror(url: str) -> Optional[tuple[str, str, str]]:
    """Readable copy for sites that block bots (Cloudflare 403 etc.): Jina reader (fast), then the
    Wayback Machine. Either one can be down, so we try both. Returns (text, title, url_read)."""
    try:
        res = await netsafe.safe_get(f"https://r.jina.ai/{url}")
        raw = res.body.decode("utf-8", "replace") if res.status < 400 else ""
        title = m.group(1).strip() if (m := re.search(r"^Title:\s*(.+)$", raw, re.M)) else ""
        body = raw.split("Markdown Content:", 1)[-1]
        body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)           # images
        body = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", body)       # links -> their text
        body = re.sub(r"^[#>*\-\s]+|[*_`]+", "", body, flags=re.M)   # markdown marks
        if len(body) > 300:
            return body, title, url
    except Exception:  # noqa: BLE001
        pass
    try:
        res = await netsafe.safe_get(f"https://web.archive.org/web/2026id_/{url}")
        if res.status < 400 and res.body:
            text, title = html_to_text(res.body, url)
            if len(text) > 300:
                return text, title, res.url
    except Exception:  # noqa: BLE001
        pass
    return None


async def fetch_page(url: str) -> tuple[Optional[SourceCheck], SourceText, str]:
    """Returns (status-if-conclusive, text, page_title). status None means the page exists."""
    try:
        res = await netsafe.safe_get(url)
    except netsafe.DNSFailure:
        return _sc("not_found", "http", tr("src.domain_missing", host=urlparse(url).hostname)), SourceText("", "none"), ""
    except netsafe.BlockedURL:
        return _sc("unchecked", "http", tr("src.internal")), SourceText("", "none"), ""
    except (httpx.TimeoutException, httpx.TransportError, httpx.TooManyRedirects) as e:
        return _sc("unreachable", "http", tr("src.no_response", err=type(e).__name__)), SourceText("", "none"), ""

    if res.status in (404, 410):
        return _sc("not_found", "http", tr("src.page_404", status=res.status)), SourceText("", "none"), ""
    if res.status >= 400:
        mirrored = await _mirror(url)
        if mirrored:
            text, title, read_url = mirrored
            return None, SourceText(text, "full", read_url), title
        return _sc("unreachable", "http", tr("src.blocked", status=res.status)), SourceText("", "none"), ""

    ctype = res.content_type.lower()
    if "pdf" in ctype or res.url.lower().endswith(".pdf"):
        try:
            return None, SourceText(pdf_to_text(res.body), "full", res.url), ""
        except Exception:  # noqa: BLE001
            return None, SourceText("", "none", res.url), ""
    text, title = html_to_text(res.body, res.url)
    if title and SOFT_404.search(title) and len(text) < 1500:
        return _sc("not_found", "http", tr("src.soft_404", title=title[:80])), SourceText("", "none"), title
    return None, SourceText(text, "full" if len(text) > 300 else "none", res.url), title


def _sc(status: str, method: str, detail: str, **kw) -> SourceCheck:
    return SourceCheck(citation_id="", status=status, method=method, detail=detail, **kw)  # type: ignore[arg-type]


async def _doi_registered(doi: str) -> Optional[bool]:
    """True/False from the global DOI handle registry (covers Crossref, DataCite, mEDRA...). None = unknown."""
    try:
        status, data = await netsafe.get_json(DOI_HANDLE + quote(doi, safe="/"))
    except httpx.HTTPError:
        return None
    if status == 200 and data and data.get("responseCode") == 1:
        return True
    if status == 404 or (data and data.get("responseCode") == 100):
        return False
    return None


async def _crossref_doi(doi: str) -> Optional[dict]:
    try:
        status, data = await netsafe.get_json(f"{CROSSREF}/{quote(doi, safe='/')}")
    except httpx.HTTPError:
        return None
    return data.get("message") if status == 200 and data else None


async def _openalex_doi(doi: str) -> Optional[dict]:
    try:
        status, data = await netsafe.get_json(f"{OPENALEX}/doi:{quote(doi, safe='/')}")
    except httpx.HTTPError:
        return None
    return data if status == 200 else None


# OpenAlex throttles anonymous bursts (429): at most 2 title searches at a time
_openalex_sem = asyncio.Semaphore(2)


async def _get_json_retry(url: str, params: dict, tries: int = 5) -> Optional[dict]:
    """Title search is what decides "this paper does not exist", so a busy API must not make us give up:
    retry 429/5xx/timeouts with backoff (~20 s in total). None = the database really did not answer."""
    for i in range(tries):
        try:
            if url.startswith(OPENALEX):
                async with _openalex_sem:
                    status, data = await netsafe.get_json(url, params)
            else:
                status, data = await netsafe.get_json(url, params)
            if status == 200 and data is not None:
                return data
            if status not in (429, 500, 502, 503, 504):
                return None
        except httpx.HTTPError:
            pass
        await asyncio.sleep(2.0 * (i + 1))
    return None


async def _search_crossref(cit: Citation) -> Optional[list[dict]]:
    q = cit.raw or " ".join(filter(None, [cit.title, " ".join(cit.authors), str(cit.year or ""), cit.venue]))
    data = await _get_json_retry(CROSSREF, {"query.bibliographic": q[:400], "rows": 5})
    return data.get("message", {}).get("items", []) if data is not None else None


async def _search_openalex(cit: Citation) -> Optional[list[dict]]:
    q = cit.title or cit.raw
    data = await _get_json_retry(OPENALEX, {"search": q[:300], "per-page": 5})
    return data.get("results", []) if data is not None else None


async def _openalex_fulltext(w: dict) -> Optional[SourceText]:
    """If OpenAlex knows an open-access PDF, read it: full text beats the abstract."""
    loc = w.get("best_oa_location") or {}
    pdf = loc.get("pdf_url")
    if not pdf:
        return None
    status, text, _ = await fetch_page(pdf)
    if status is None and len(text.text) > 1500:
        return SourceText(text.text, "full", pdf)
    return None


# ------------------------------------------------------------------ main entry

async def check_citation(cit: Citation) -> tuple[SourceCheck, SourceText]:
    try:
        if cit.doi:
            sc, st = await _check_doi(cit)
        elif cit.url:
            sc, st = await _check_url(cit)
        elif cit.title or cit.raw:
            sc, st = await _check_by_metadata(cit)
        else:
            sc, st = _sc("unchecked", "none", tr("src.nothing")), SourceText("", "none")
    except Exception as e:  # noqa: BLE001 — a single source must never crash the whole report
        log.exception("source check failed")
        sc, st = _sc("unchecked", "error", tr("src.failed", err=type(e).__name__)), SourceText("", "none")
    sc.citation_id = cit.id
    return sc, st


async def _check_doi(cit: Citation) -> tuple[SourceCheck, SourceText]:
    doi = cit.doi or ""
    registered, cr, oa = await asyncio.gather(_doi_registered(doi), _crossref_doi(doi), _openalex_doi(doi))
    if registered is False and not cr and not oa:
        return _sc("not_found", "doi.org",
                   tr("src.doi_missing", doi=doi)), SourceText("", "none")
    rec = _crossref_record(cr) if cr else (_openalex_record(oa) if oa else None)
    if rec is None:
        if registered:
            return _sc("exists", "doi.org", tr("src.doi_no_meta", doi=doi)), SourceText("", "none")
        return _sc("unreachable", "doi.org", tr("src.doi_down")), SourceText("", "none")

    diffs = compare_metadata(cit, rec)
    text = await _text_for_record(cr, oa)
    if cit.title and rec.title and title_similarity(cit.title, rec.title) < 60:
        return _sc("mismatch", "doi.org+crossref",
                   tr("src.doi_other_work", title=rec.title),
                   matched=rec, differences=diffs, text_scope=text.scope), text
    if diffs:
        return _sc("mismatch", "doi.org+crossref", tr("src.pub_mismatch"),
                   matched=rec, differences=diffs, text_scope=text.scope), text
    return _sc("exists", "doi.org+crossref", tr("src.pub_ok"), matched=rec, text_scope=text.scope), text


async def _text_for_record(cr: Optional[dict], oa: Optional[dict]) -> SourceText:
    if oa:
        full = await _openalex_fulltext(oa)
        if full:
            return full
        abstract = openalex_abstract(oa)
        if abstract:
            return SourceText(abstract, "abstract", oa.get("doi"))
    if cr and cr.get("abstract"):
        return SourceText(_strip_jats(cr["abstract"]), "abstract", f"https://doi.org/{cr.get('DOI')}")
    return SourceText("", "none")


async def _check_url(cit: Citation) -> tuple[SourceCheck, SourceText]:
    status, text, title = await fetch_page(cit.url or "")
    if status:
        return status, text
    matched = MatchedRecord(title=title or None, url=text.url or cit.url)
    if text.scope == "none":
        return _sc("exists", "http", tr("src.page_no_text"),
                   matched=matched), text
    return _sc("exists", "http", tr("src.page_ok"), matched=matched, text_scope="full"), text


async def _check_by_metadata(cit: Citation) -> tuple[SourceCheck, SourceText]:
    cr_items, oa_items = await asyncio.gather(_search_crossref(cit), _search_openalex(cit))
    best: tuple[int, Optional[MatchedRecord], Optional[dict], Optional[dict]] = (0, None, None, None)
    for it in cr_items or []:
        rec = _crossref_record(it)
        s = title_similarity(cit.title or cit.raw, rec.title)
        if s > best[0]:
            best = (s, rec, it, None)
    for w in oa_items or []:
        rec = _openalex_record(w)
        s = title_similarity(cit.title or cit.raw, rec.title)
        if s > best[0]:
            best = (s, rec, None, w)
    score, rec, cr, oa = best
    searched_ok = cr_items is not None and oa_items is not None

    if rec and score >= 88:
        diffs = compare_metadata(cit, rec)
        text = await _text_for_record(cr, oa)
        if diffs:
            return _sc("mismatch", "crossref+openalex", tr("src.work_mismatch"),
                       matched=rec, differences=diffs, text_scope=text.scope), text
        return _sc("exists", "crossref+openalex", tr("src.work_ok"),
                   matched=rec, text_scope=text.scope), text

    if not searched_ok:
        why = tr("src.openalex_busy") if cr_items is not None else tr("src.crossref_busy") if oa_items is not None else tr("src.dbs_busy")
        return _sc("unreachable", "crossref+openalex", why, retry=True), SourceText("", "none")

    if cit.kind == "academic":
        near = tr("src.nearest", title=rec.title) if rec and score >= 60 else ""
        return _sc("not_found", "crossref+openalex",
                   tr("src.fake_work") + near,
                   matched=rec if rec and score >= 60 else None), SourceText("", "none")
    return _sc("unchecked", "crossref+openalex",
               tr("src.unchecked_nodb")), SourceText("", "none")
