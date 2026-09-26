"""Orchestration: extract -> check every source in parallel -> judge every claim in parallel.
Results are emitted as events as soon as each piece is ready (the UI lights claims up one by one)."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncIterator

from . import search
from .extract import extract
from .judge import judge_attack, judge_cited
from .models import Citation, Claim, ClaimResult, SourceCheck, Summary
from .replacements import find_replacements
from .sources import SourceText, check_citation

PIPELINE_VERSION = "1.1"

log = logging.getLogger("pruf.pipeline")

VERDICT_RU = {
    "supported": "подтверждено",
    "contradicted": "источник говорит другое",
    "not_in_source": "в источнике этого нет",
    "source_missing": "источник не существует",
    "unverifiable": "не удалось проверить",
}


def _plural(n: int, one: str, few: str, many: str) -> str:
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return few
    return many


def summarize(claims: list[Claim], checks: list[SourceCheck], results: list[ClaimResult], started: float) -> Summary:
    counts = {k: 0 for k in VERDICT_RU}
    for r in results:
        counts[r.verdict] = counts.get(r.verdict, 0) + 1
    missing = sum(1 for c in checks if c.status == "not_found")
    mism = sum(1 for c in checks if c.status == "mismatch")
    by_id = {c.id: c for c in claims}
    danger = sum(1 for r in results if r.verdict != "supported" and by_id[r.claim_id].certainty == "assertive")

    parts = []
    if checks and missing:
        parts.append(f"{missing} из {len(checks)} {_plural(len(checks), 'источника', 'источников', 'источников')} не существуют")
    if mism:
        parts.append(f"{mism} {_plural(mism, 'источник искажён', 'источника искажены', 'источников искажены')}")
    bad = counts["contradicted"]
    if bad:
        parts.append(f"{bad} {_plural(bad, 'утверждение противоречит', 'утверждения противоречат', 'утверждений противоречат')} источникам")
    if not parts:
        ok = counts["supported"]
        headline = (f"Подтверждено {ok} из {len(results)} утверждений" if results else "Проверяемых утверждений не найдено")
        if counts["unverifiable"] or counts["not_in_source"]:
            headline += f", {counts['unverifiable'] + counts['not_in_source']} — без доказательств"
    else:
        headline = "; ".join(parts)
        headline = headline[0].upper() + headline[1:]
    return Summary(headline=headline + ".", counts=counts, sources_total=len(checks), sources_missing=missing,
                   sources_mismatch=mism, danger_zone=danger, duration_ms=int((time.time() - started) * 1000))


async def run(text: str) -> AsyncIterator[dict]:
    started = time.time()
    yield {"type": "stage", "stage": "extract", "message": "Разбираю ответ на утверждения и источники…"}
    claims, citations = await extract(text)
    yield {"type": "extracted", "claims": [c.model_dump() for c in claims], "citations": [c.model_dump() for c in citations]}
    if not claims:
        s = summarize([], [], [], started)
        yield {"type": "done", "summary": s.model_dump()}
        return

    queue: asyncio.Queue[dict | None] = asyncio.Queue()
    checks: dict[str, SourceCheck] = {}
    texts: dict[str, SourceText] = {}
    results: list[ClaimResult] = []
    cit_by_id: dict[str, Citation] = {c.id: c for c in citations}
    source_done: dict[str, asyncio.Event] = {c.id: asyncio.Event() for c in citations}

    async def do_source(c: Citation) -> None:
        try:
            sc, st = await check_citation(c)
            checks[c.id], texts[c.id] = sc, st
            source_done[c.id].set()
            await queue.put({"type": "source", "check": sc.model_dump()})
            if sc.status == "not_found":
                claim = next((cl for cl in claims if c.id in cl.citation_ids), None)
                try:
                    reps = await find_replacements(c, claim)
                except Exception:  # noqa: BLE001
                    log.exception("replacements for %s failed", c.id)
                    reps = []
                await queue.put({"type": "replacements", "citation_id": c.id, "claim_id": claim.id if claim else None,
                                 "works": [r.model_dump() for r in reps]})
        finally:
            await queue.put(None)  # this task is finished

    async def do_claim(cl: Claim) -> None:
        try:
            if cl.citation_ids:
                for cid in cl.citation_ids:
                    await source_done[cid].wait()
                res = await judge_cited(cl, [cit_by_id[i] for i in cl.citation_ids], checks, texts)
            else:
                hits = await search.gather_evidence(cl.queries)
                res = await judge_attack(cl, hits, cl.queries)
        except Exception as e:  # noqa: BLE001
            log.exception("claim %s failed", cl.id)
            res = ClaimResult(claim_id=cl.id, verdict="unverifiable", mode="cited" if cl.citation_ids else "attack",
                              reason=f"Внутренняя ошибка проверки: {type(e).__name__}.")
        results.append(res)
        await queue.put({"type": "claim", "result": res.model_dump()})
        await queue.put(None)

    yield {"type": "stage", "stage": "verify", "message": "Проверяю источники и ищу опровержения…"}
    tasks = [asyncio.create_task(do_source(c)) for c in citations] + [asyncio.create_task(do_claim(c)) for c in claims]
    pending = len(tasks)
    while pending:  # each task emits its events, then None
        ev = await queue.get()
        if ev is None:
            pending -= 1
        else:
            yield ev
    await asyncio.gather(*tasks, return_exceptions=True)

    s = summarize(claims, list(checks.values()), results, started)
    yield {"type": "done", "summary": s.model_dump()}
