"""«Проверить работу перед сдачей»: a whole student paper instead of one AI answer.

1. find the reference list (last matching heading), split it into entries, parse each with regexes;
   whatever the regexes could not parse goes to the LLM in ONE batch request;
2. check EVERY reference with the same check_citation as the chat mode (6 in parallel);
3. from the body take only sentences that cite a reference ([n], [n, с. 25], (Автор, 2020)), at most 15,
   and judge them against the cited sources with the same judge.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from . import llm
from .config import settings
from .extract import _marker_numbers, _norm_citation
from .judge import judge_cited
from .models import Citation, Claim, ClaimResult, SourceCheck
from .pipeline import run, summarize
from .replacements import find_replacements
from .sources import SourceText, check_citation
from .textutil import certainty, clean_doi, find_dois, find_urls, locate

log = logging.getLogger("pruf.bibliography")

MAX_CLAIMS = 15
SOURCE_PARALLEL = 6

HEADINGS = (
    "список литературы", "список использованной литературы", "список использованных источников",
    "список источников", "литература", "библиография", "библиографический список", "references",
    "bibliography", "works cited", "reference list", "пайдаланылған әдебиеттер",
    "пайдаланылған әдебиеттер тізімі",
)
_HEADING = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\.?\s+)?(" + "|".join(re.escape(h) for h in HEADINGS) + r")\s*:?\s*$", re.I | re.M)
_STOP = re.compile(r"^\s*(приложени[ея]|appendix|annex|қосымша)\b.{0,60}$", re.I | re.M)

_NUMBERED = re.compile(r"^\s*(?:\[(\d{1,3})\]|(\d{1,3})[.)])\s+(.+)$")
_AUTHOR_START = re.compile(r"^\s*[A-ZА-ЯЁӘҒҚҢӨҰҮҺІ][\w'’\-]+,?\s+(?:[A-ZА-ЯЁ]\.\s?-?){1,3}")
_YEAR = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")
_ACADEMIC = re.compile(
    r"//|journal|вестник|известия|proceedings|журнал|review|letters|transactions|conference|конференц|"
    r"\bvol\.|\bт\.\s*\d|№\s*\d|\b\d+\s*\(\d+\)|\bpp?\.\s*\d|,\s*\d{1,4}\s*,\s*[\de]\d*[–-]?\d*\.?\s*$|"
    r"scientific reports|nature\b|science\b|plos", re.I)
_BOOK = re.compile(r"\b(М\.|СПб\.|Алматы|Астана|Нур-Султан|изд|издательство|press|publisher|учебник|учеб\.|пособие|монография)", re.I)
_LAW = re.compile(r"\b(закон|кодекс|постановлени|указ\b|приказ\b)", re.I)


# ---------------------------------------------------------------- 1. find + split + parse

def find_bibliography(text: str) -> Optional[tuple[str, str]]:
    """(body, reference list) split at the LAST reference-list heading, or None."""
    heads = list(_HEADING.finditer(text or ""))
    if not heads:
        return None
    h = heads[-1]
    bib = text[h.end():]
    if stop := _STOP.search(bib):
        bib = bib[: stop.start()]
    if not bib.strip():
        return None
    return text[: h.start()], bib


@dataclass
class Reference:
    n: int
    raw: str


def split_references(bib: str) -> list[Reference]:
    lines = [ln.strip() for ln in bib.splitlines()]
    numbered = sum(1 for ln in lines if _NUMBERED.match(ln)) >= 2
    entries: list[list] = []  # [number or None, text]
    for ln in lines:
        if not ln:
            if not numbered and entries and entries[-1][1]:
                entries.append([None, ""])  # a blank line ends an unnumbered entry
            continue
        m = _NUMBERED.match(ln) if numbered else None
        if m:
            entries.append([int(m.group(1) or m.group(2)), m.group(3).strip()])
        elif not numbered and (_AUTHOR_START.match(ln) or not entries or not entries[-1][1]):
            entries.append([None, ln])
        elif entries:
            entries[-1][1] = (entries[-1][1] + " " + ln).strip()
    refs: list[Reference] = []
    for i, (n, raw) in enumerate([e for e in entries if len(e[1]) >= 15]):
        refs.append(Reference(n if n is not None else i + 1, raw))
    return refs


def parse_reference(ref: Reference) -> tuple[Citation, bool]:
    """Regex parse. Returns (citation, parsed_well_enough)."""
    raw = ref.raw
    plain = re.sub(r"(?:https?://|www\.)\S+", " ", raw)  # "//" inside a URL is not the ГОСТ journal marker
    dois = find_dois(raw)
    doi = dois[0] if dois else None
    urls = [u for u in find_urls(raw) if "doi.org/" not in u.lower()]
    if not doi and (m := re.search(r"doi\.org/(10\.\S+)", raw, re.I)):
        doi = clean_doi(m.group(1))
    years = _YEAR.findall(raw)
    year = int(years[0]) if years else None

    title = venue = None
    authors: list[str] = []
    if m := re.match(r"^(?P<auth>.+?)\s*\((?P<y>(?:19|20)\d{2})[a-z]?\)\.?\s*(?P<rest>.+)$", raw):
        # APA: Surname, I., & Surname, I. (2023). Title. Venue, 13, 1–10. https://doi.org/...
        authors = re.findall(r"([A-ZА-ЯЁ][\w'’\-]+),\s*(?:[A-ZА-ЯЁ]\.\s?)+", m.group("auth"))
        parts = re.split(r"(?<=\.)\s+", m.group("rest"), maxsplit=1)  # "?" inside a title does not end it
        title = parts[0].rstrip(".")
        if len(parts) > 1:
            venue = re.split(r",\s*\d|\.\s|https?://", parts[1])[0].strip(" .,") or None
    else:
        # ГОСТ: Фамилия И. О. Название / И. О. Фамилия // Журнал. — 2020. — № 3. — С. 1–10.
        m = re.match(r"^(?P<auth>(?:[A-ZА-ЯЁӘҒҚҢӨҰҮҺІ][\w'’\-]+,?\s+(?:[A-ZА-ЯЁ]\.\s?-?){1,3},?\s*)+)(?P<rest>.+)$", raw)
        rest = m.group("rest") if m else raw
        if m:
            authors = re.findall(r"([A-ZА-ЯЁӘҒҚҢӨҰҮҺІ][\w'’\-]+),?\s+(?:[A-ZА-ЯЁ]\.)", m.group("auth"))
        title = re.split(r"\s+/{1,2}\s*|\s*\[(?:электронный ресурс|electronic resource)\]|\.\s+[—–-]\s+|\s+URL:|https?://", rest, flags=re.I)[0]
        title = title.strip(" .,:;") or None
        if v := re.search(r"//\s*([^.—–]+)", plain):
            venue = v.group(1).strip(" .,")
    if title and (len(title) < 8 or len(title) > 400):
        title = None

    if doi or _ACADEMIC.search(plain):
        kind = "academic"
    elif _LAW.search(raw):
        kind = "law"
    elif urls:
        kind = "web"
    elif _BOOK.search(raw):
        kind = "book"
    else:
        kind = "other"
    cit = Citation(id=f"S{ref.n}", raw=raw, kind=kind, url=urls[0] if urls else None, doi=doi,  # type: ignore[arg-type]
                   title=title, authors=authors[:12], year=year, venue=venue)
    return cit, bool(doi or urls or (title and year))


_BATCH_SYSTEM = """Ты разбираешь список литературы студенческой работы. Для КАЖДОЙ ссылки верни поля.
Верни JSON: {"refs": [{"n": 1, "kind": "academic|web|book|law|other", "title": "название работы", "authors": ["Фамилия И."],
"year": 2020, "venue": "журнал/издательство/сайт или null", "doi": "DOI или null", "url": "ссылка или null"}]}
- n — номер ссылки из входа. Не выдумывай: чего нет в тексте ссылки — null.
- kind=academic для статей в журналах и сборниках; book для книг, учебников, монографий; law для законов; web для сайтов."""


async def parse_all(refs: list[Reference]) -> list[Citation]:
    parsed = [parse_reference(r) for r in refs]
    unclear = [r for r, (_, ok) in zip(refs, parsed) if not ok]
    fixed: dict[int, Citation] = {}
    if unclear:
        block = "\n".join(f"{r.n}. {r.raw}" for r in unclear)
        try:
            out = await llm.complete_json(_BATCH_SYSTEM, f"Ссылки:\n{block}", max_tokens=min(400 + 150 * len(unclear), 4000), role="extract")
            by_n = {r.n: r for r in unclear}
            for item in out.get("refs") or []:
                try:
                    n = int(item.get("n"))
                except (TypeError, ValueError):
                    continue
                if n in by_n:
                    c = _norm_citation({**item, "id": f"S{n}", "raw": by_n[n].raw}, n)
                    fixed[n] = c
        except llm.LLMError as e:
            log.warning("bibliography batch parse failed: %s", e)
    return [fixed.get(r.n, c) for r, (c, _) in zip(refs, parsed)]


# ---------------------------------------------------------------- 2. cited sentences of the body

_NUM_MARK = re.compile(r"\[(\d{1,3}(?:\s*[,;–-]\s*\d{1,3})*)(?:\s*[,;]\s*(?:с|c|p|pp|стр|б)\.?\s*[\d–\-]+)?\]")
_AY_MARK = re.compile(r"\(([^()]{2,160}?\b(?:19|20)\d{2}[a-zа-я]?(?:\s*[,;]\s*(?:с|c|p|pp)\.?\s*[\d–\-]+)?)\)")
_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-ZА-ЯЁӘҒҚҢӨҰҮҺІ«\"(\[])|\n+")


def _sentences_with_offsets(text: str) -> list[tuple[int, int]]:
    out, pos = [], 0
    for m in _BOUNDARY.finditer(text):
        out.append((pos, m.start()))
        pos = m.end()
    out.append((pos, len(text)))
    return [(a, b) for a, b in out if b - a >= 25]


def _cited_ids(sentence: str, cits: list[Citation]) -> list[str]:
    by_n = {c.id: c for c in cits}
    ids: list[str] = []
    for m in _NUM_MARK.finditer(sentence):
        ids += [f"S{n}" for n in _marker_numbers(f"[{m.group(1)}]") if f"S{n}" in by_n]
    for m in _AY_MARK.finditer(sentence):
        for part in re.split(r"\s*;\s*", m.group(1)):
            name = re.match(r"\s*([A-ZА-ЯЁӘҒҚҢӨҰҮҺІ][\w'’\-]+)", part)
            year = re.search(r"(?:19|20)\d{2}", part)
            if not name or not year:
                continue
            for c in cits:
                if name.group(1).lower() in c.raw.lower() and year.group(0) in c.raw:
                    ids.append(c.id)
                    break
    return list(dict.fromkeys(ids))


def cited_claims(body: str, cits: list[Citation], limit: int = MAX_CLAIMS) -> list[Claim]:
    found = []
    for a, b in _sentences_with_offsets(body):
        sent = body[a:b].strip()
        ids = _cited_ids(sent, cits)
        if not ids:
            continue
        start = body.index(sent, a)
        clean = _AY_MARK.sub("", _NUM_MARK.sub("", sent))
        clean = re.sub(r"\s+([.,;:])", r"\1", re.sub(r"\s{2,}", " ", clean)).strip()
        found.append((start, sent, clean[:400], ids))
    # facts with numbers first (most checkable), then document order
    chosen = sorted(found, key=lambda f: (not re.search(r"\d", f[2]), f[0]))[:limit]
    chosen.sort(key=lambda f: f[0])
    claims = []
    for i, (start, sent, clean, ids) in enumerate(chosen):
        tone, markers = certainty(sent)
        claims.append(Claim(id=f"C{i + 1}", text=clean, span=sent, start=start, end=start + len(sent),
                            citation_ids=ids, certainty=tone, certainty_markers=markers))  # type: ignore[arg-type]
    return claims


# ---------------------------------------------------------------- 2b. documents without a reference list

SELECTED_NOTICE = ("В документе нет списка литературы, поэтому проверяем утверждения о фактах и числах из всего текста. "
                   "Титульный лист, личные данные, даты и обязанности не проверяем: их нельзя сверить с открытыми источниками.")
NOTHING_CHECKABLE = ("В документе не нашлось утверждений, которые можно сверить с открытыми источниками: только личные данные, "
                     "даты, обязанности и описание работы. Такие сведения Trustable? не проверяет.")
_FACT_CUES = re.compile(
    r"по данным|согласно|исследован|статистик|составля|составил|насчитыва|достиг|увеличил|сократил|вырос|снизил|"
    r"крупнейш|млн|млрд|тыс\.|процент|%|\bв \d{4} год|закон|кодекс|постановлени|указ\b|according|percent|million|billion",
    re.I)
_PERSONAL = re.compile(
    r"\b(я|мной|мною|мне|меня|мой|моя|мои|моей|моих|мы|нами|нам|нас|наш|наша|наши)\b|практик|обязанност|руководител|"
    r"студент\w* групп|ф\.?\s?и\.?\s?о|выполнил|ознакомил|изучил|приняла? участие|подпись|отч[её]т|дневник|"
    r"цел[ьи] (работы|практики)|задач[аи] (работы|практики)|кафедр|факультет|специальност|курса\b",
    re.I)
_TOC_LINE = re.compile(r"(\.{3,}|…)\s*\d{1,3}\s*$|^\s*\d+(\.\d+)*\.?\s+[А-ЯЁA-Z][^.!?]{0,80}\s+\d{1,3}\s*$", re.M)


def _looks_like_report(text: str) -> bool:
    """Title page / internship-report boilerplate at the start: select sentences even for short documents."""
    head = text[:1500]
    return len(_PERSONAL.findall(head)) >= 3


def _sentence_score(s: str) -> int:
    if _TOC_LINE.search(s) or len(s) < 40 or s.isupper():
        return -10
    score = 0
    if re.search(r"\d", s):
        score += 2
    score += 2 * min(len(_FACT_CUES.findall(s)), 2)
    if len(re.findall(r"(?<=\s)[A-ZА-ЯЁ][\w\-]{2,}", s)) >= 2:
        score += 1
    score -= 4 * min(len(_PERSONAL.findall(s)), 2)
    return score


def checkable_text(text: str, budget: int) -> str:
    """The most checkable sentences of the whole document, in document order, within `budget` characters."""
    spans = []
    for a, b in _sentences_with_offsets(text):
        sent = text[a:b].strip()
        sc = _sentence_score(sent)
        if sc >= 2:
            spans.append((sc, a, sent))
    chosen, used = [], 0
    for sc, a, sent in sorted(spans, key=lambda x: (-x[0], x[1])):
        if used + len(sent) + 2 > budget:
            continue
        chosen.append((a, sent))
        used += len(sent) + 2
    return "\n\n".join(sent for _, sent in sorted(chosen))


# ---------------------------------------------------------------- 3. orchestration

def score(checks: list[SourceCheck], total: int) -> dict:
    st = [c.status for c in checks]
    return {"verified": st.count("exists"), "total": total, "fabricated": st.count("not_found"),
            "distorted": st.count("mismatch"), "unreachable": st.count("unreachable") + st.count("unchecked")}


def _item(c: Citation, sc: Optional[SourceCheck]) -> dict:
    return {"n": int(c.id[1:]), "id": c.id, "raw": c.raw, "citation": c.model_dump(),
            "check": sc.model_dump() if sc else None}


async def run_document(text: str, filename: str) -> AsyncIterator[dict]:
    started = time.time()
    yield {"type": "document", "filename": filename, "chars": len(text), "text": text,
           "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    found = find_bibliography(text)
    if not found:
        # no reference list: pick the checkable factual sentences from the WHOLE document (not the title page),
        # check them like any text, and map the highlights back onto the full document
        part = text if len(text) <= settings.max_text_chars and not _looks_like_report(text) else checkable_text(text, settings.max_text_chars)
        if not part.strip():
            yield {"type": "notice", "message": NOTHING_CHECKABLE}
            yield {"type": "done", "summary": summarize([], [], [], started).model_dump()}
            return
        if part is not text:
            yield {"type": "notice", "message": SELECTED_NOTICE}
        async for ev in run(part):
            if ev["type"] == "extracted" and part is not text:
                for c in ev["claims"]:
                    c["start"], c["end"] = locate(c.get("span") or c["text"], text)
            yield ev
        return
    body, bib = found
    yield {"type": "stage", "stage": "extract", "message": "Разбираю список литературы…"}
    refs = split_references(bib)
    if not refs:
        yield {"type": "error", "message": "Заголовок списка литературы есть, но ссылок под ним не нашлось."}
        return
    citations = await parse_all(refs)
    yield {"type": "bibliography", "items": [_item(c, None) for c in citations]}
    claims = cited_claims(body, citations)
    yield {"type": "extracted", "claims": [c.model_dump() for c in claims], "citations": [c.model_dump() for c in citations]}
    yield {"type": "stage", "stage": "verify", "message": f"Проверяю {len(citations)} источников и {len(claims)} утверждений…"}

    queue: asyncio.Queue[dict] = asyncio.Queue()
    checks: dict[str, SourceCheck] = {}
    texts: dict[str, SourceText] = {}
    results: list[ClaimResult] = []
    by_id = {c.id: c for c in citations}
    done = {c.id: asyncio.Event() for c in citations}
    sem = asyncio.Semaphore(SOURCE_PARALLEL)

    async def do_source(c: Citation) -> None:
        async with sem:
            sc, st = await check_citation(c)
        checks[c.id], texts[c.id] = sc, st
        done[c.id].set()
        await queue.put({"type": "bibliography", "items": [_item(c, sc)]})
        if len(checks) == len(citations):
            await queue.put({"type": "score", "score": score(list(checks.values()), len(citations))})
        if sc.status == "not_found":
            claim = next((cl for cl in claims if c.id in cl.citation_ids), None)
            try:
                reps = await find_replacements(c, claim)
            except Exception:  # noqa: BLE001
                log.exception("replacements for %s failed", c.id)
                reps = []
            await queue.put({"type": "replacements", "citation_id": c.id, "claim_id": claim.id if claim else None,
                             "works": [r.model_dump() for r in reps]})

    async def do_claim(cl: Claim) -> None:
        try:
            for cid in cl.citation_ids:
                await done[cid].wait()
            res = await judge_cited(cl, [by_id[i] for i in cl.citation_ids], checks, texts)
        except Exception as e:  # noqa: BLE001
            log.exception("claim %s failed", cl.id)
            res = ClaimResult(claim_id=cl.id, verdict="unverifiable", mode="cited", reason=f"Внутренняя ошибка проверки: {type(e).__name__}.")
        results.append(res)
        await queue.put({"type": "claim", "result": res.model_dump()})

    tasks = [asyncio.create_task(do_source(c)) for c in citations] + [asyncio.create_task(do_claim(c)) for c in claims]
    runner = asyncio.gather(*tasks, return_exceptions=True)
    while not (runner.done() and queue.empty()):
        get = asyncio.ensure_future(queue.get())
        await asyncio.wait({get, runner}, return_when=asyncio.FIRST_COMPLETED)
        if get.done():
            yield get.result()
        else:
            get.cancel()
    await runner
    s = summarize(claims, list(checks.values()), results, started)
    yield {"type": "done", "summary": s.model_dump()}
