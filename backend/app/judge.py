"""Verdicts. The LLM proposes, the code disposes:
- every quote the LLM returns must be found (almost) verbatim in the source text, otherwise it is dropped;
- numbers are compared deterministically, independent of the LLM;
- an abstract that doesn't mention a claim is NOT evidence against it (-> unverifiable, not "not in source").
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from . import llm
from .models import Citation, Claim, ClaimResult, Evidence, MatchedRecord, NumberCheck, SearchInfo, SourceCheck
from .prompts import JUDGE_ATTACK_SYSTEM, JUDGE_CITED_SYSTEM
from .i18n import LLM_LANGUAGE, current, tr
from . import search
from .search import TIER_RU, Hit
from .search import provider as search_provider
from .sources import SourceText
from .textutil import chunk, number_mismatch, quote_in_text, rank_passages

log = logging.getLogger("pruf.judge")



def _label(cit: Citation, sc: SourceCheck) -> str:
    if sc.matched and sc.matched.title:
        return sc.matched.title
    return cit.title or cit.raw[:120] or cit.url or cit.id


def _source_url(cit: Citation, sc: SourceCheck, st: SourceText) -> str | None:
    return (sc.matched.url if sc.matched and sc.matched.url else None) or st.url or cit.url or (f"https://doi.org/{cit.doi}" if cit.doi else None)


async def judge_cited(claim: Claim, cits: list[Citation], checks: dict[str, SourceCheck], texts: dict[str, SourceText]) -> ClaimResult:
    """A claim with one or more cited sources. Most damning honest verdict wins."""
    per_source: list[ClaimResult] = []
    for cit in cits:
        per_source.append(await _judge_one_source(claim, cit, checks[cit.id], texts.get(cit.id, SourceText("", "none"))))
    if not per_source:
        return ClaimResult(claim_id=claim.id, verdict="unverifiable", mode="cited", reason=tr("j.unrecognized"))
    # if ANY source supports with a verified quote, the claim is supported; otherwise report the worst problem
    order = ["supported", "contradicted", "source_missing", "not_in_source", "unverifiable"]
    for v in order:
        for r in per_source:
            if r.verdict == v:
                if len(per_source) > 1:
                    r.evidence = [e for x in per_source for e in x.evidence]
                    r.notes = [n for x in per_source for n in x.notes]
                return r
    return per_source[0]


async def judge_abstract(claim: Claim, title: str, abstract: str) -> ClaimResult:
    """Judge a claim against a bare abstract (used for suggested replacement works)."""
    cit = Citation(id="R", kind="academic", title=title)
    sc = SourceCheck(citation_id="R", status="exists", method="openalex", detail="", text_scope="abstract",
                     matched=MatchedRecord(title=title))
    return await _judge_one_source(claim, cit, sc, SourceText(abstract, "abstract"))


async def _judge_one_source(claim: Claim, cit: Citation, sc: SourceCheck, st: SourceText) -> ClaimResult:
    label = _label(cit, sc)
    url = _source_url(cit, sc, st)

    if sc.status == "not_found":
        return ClaimResult(claim_id=claim.id, verdict="source_missing", mode="cited",
                           reason=tr("j.source_missing", detail=sc.detail))
    if sc.status in ("unreachable", "unchecked") or st.scope == "none" or len(st.text) < 80:
        why = sc.detail if sc.status in ("unreachable", "unchecked") else tr("j.no_text")
        return ClaimResult(claim_id=claim.id, verdict="unverifiable", mode="cited",
                           reason=tr("j.cannot_read", why=why))

    passages = chunk(st.text)
    top = rank_passages(claim.text, passages, k=10)
    selected = [passages[i] for i in sorted(i for i, _ in top)]  # document order reads better than score order
    block = "\n\n".join(f"[P{n + 1}] {p}" for n, p in enumerate(selected))
    user = (
        f"Утверждение: {claim.text}\n\nИсточник: {label}"
        f"{' (доступна только аннотация)' if st.scope == 'abstract' else ''}\n\nФрагменты:\n{block}"
    )
    try:
        out = await llm.complete_json(_in_lang(JUDGE_CITED_SYSTEM), user, max_tokens=600)
    except llm.LLMError as e:
        return ClaimResult(claim_id=claim.id, verdict="unverifiable", mode="cited", reason=_llm_error(e), error=True)

    verdict = str(out.get("verdict", "not_mentioned"))
    quote = str(out.get("quote") or "").strip()
    reason = str(out.get("reason") or "").strip()
    notes: list[str] = []
    evidence: list[Evidence] = []

    quote_ok = bool(quote) and quote_in_text(quote, st.text)
    if quote and not quote_ok:
        log.warning("claim %s: judge quote not found in source, dropped: %r", claim.id, quote[:200])
        notes.append(tr("j.quote_dropped"))
    if quote_ok:
        stance = {"supports": "supports", "contradicts": "contradicts", "partially": "contradicts"}.get(verdict, "neutral")
        evidence.append(Evidence(source_label=label, url=url, citation_id=cit.id, quote=quote, quote_verified=True, stance=stance))  # type: ignore[arg-type]

    # deterministic number check over the quote + the best passages
    context = " ".join([quote] + selected[:2]) if quote_ok else " ".join(selected[:2])
    cn, sn, mismatch = number_mismatch(claim.text, context)
    if mismatch:
        # a number is "changed" only if it appears NOWHERE in the source — not just outside the best passages
        mismatch = number_mismatch(claim.text, st.text)[2]
    numbers = NumberCheck(claim_numbers=cn, source_numbers=sn[:12], mismatch=mismatch) if cn else None

    if verdict in ("supports", "partially", "contradicts") and not quote_ok:
        final = "unverifiable"
        reason = tr("j.no_quote")
    elif verdict == "supports":
        if mismatch:
            final = "contradicted"
            notes.append(tr("j.numbers_note"))
            reason = tr("j.numbers_reason", a=", ".join(cn), b=", ".join(sn[:4]))
        else:
            final = "supported"
    elif verdict in ("contradicts", "partially"):
        final = "contradicted"
        if verdict == "partially":
            notes.append(tr("j.narrower"))
    else:  # not_mentioned
        if st.scope == "abstract":
            final = "unverifiable"
            reason = tr("j.abstract_missing")
        else:
            final = "not_in_source"
            reason = reason or tr("j.not_in_source")

    if sc.status == "mismatch":
        notes.append(tr("j.distorted_note", x="; ".join(sc.differences) if sc.differences else sc.detail))
    if st.scope == "abstract":
        notes.append(tr("j.abstract_note"))

    return ClaimResult(claim_id=claim.id, verdict=final, mode="cited", reason=reason, evidence=evidence, numbers=numbers, notes=notes)  # type: ignore[arg-type]


async def judge_attack(claim: Claim, hits: list[Hit], queries: list[str] | None = None) -> ClaimResult:
    """No source: search support AND refutation, verify quotes. "Supported" needs a verified quote from an
    authoritative source (official/scientific/reference) or from >= 2 independent domains."""
    info = SearchInfo(provider=search_provider(), queries=list(queries or claim.queries), pages=len(hits),
                      domains=list(dict.fromkeys(h.domain for h in hits))[:8])
    if not hits:
        return ClaimResult(claim_id=claim.id, verdict="unverifiable", mode="attack", search=info,
                           reason=tr("j.attack_nothing", prov=_provider_ru(info.provider)))
    passages: list[tuple[Hit, str]] = []
    for h in hits:
        ch = chunk(h.snippet) or [h.snippet[:900]]
        for i, _ in rank_passages(claim.text + " " + " ".join(info.queries[:1]), ch, k=3):
            passages.append((h, ch[i]))
    ranked = rank_passages(claim.text, [p for _, p in passages], k=10)
    chosen = [passages[i] for i, _ in ranked]
    block = "\n\n".join(
        f"[P{n + 1} | {h.domain} | {TIER_RU[h.tier]}{' | найдено запросом-опровержением' if h.adversarial else ''}] {p}"
        for n, (h, p) in enumerate(chosen)
    )
    try:
        out = await llm.complete_json(_in_lang(JUDGE_ATTACK_SYSTEM), f"Утверждение: {claim.text}\n\nФрагменты:\n{block}", max_tokens=900)
    except llm.LLMError as e:
        return ClaimResult(claim_id=claim.id, verdict="unverifiable", mode="attack", reason=_llm_error(e), search=info, error=True)

    evidence: list[Evidence] = []
    notes: list[str] = []
    dropped = 0
    if not isinstance(out, dict):
        out = {}
    for ev in out.get("evidence") if isinstance(out.get("evidence"), list) else []:
        if not isinstance(ev, dict):
            dropped += 1
            continue
        try:
            idx = int(str(ev.get("passage", "")).strip("P[] ")) - 1
            h, p = chosen[idx]
        except (ValueError, IndexError):
            dropped += 1
            continue
        q = str(ev.get("quote") or "").strip()
        if not quote_in_text(q, p) and not quote_in_text(q, h.snippet):
            dropped += 1
            continue
        stance = "contradicts" if ev.get("stance") == "contradicts" else "supports"
        evidence.append(Evidence(source_label=h.title or h.domain, url=h.url, quote=q, quote_verified=True, stance=stance, tier=h.tier))  # type: ignore[arg-type]
    if dropped:
        notes.append(tr("j.dropped", n=dropped))

    verdict = str(out.get("verdict", "insufficient"))
    reason = str(out.get("reason") or "").strip()
    support = [e for e in evidence if e.stance == "supports"]
    contra = [e for e in evidence if e.stance == "contradicts"]
    strong = lambda evs: any(e.tier in ("official", "reference") for e in evs) or len({_dom(e.url or "") for e in evs}) >= 2  # noqa: E731

    cn, sn, mismatch = number_mismatch(claim.text, " ".join(e.quote for e in evidence))
    numbers = NumberCheck(claim_numbers=cn, source_numbers=sn[:12], mismatch=mismatch) if cn else None

    if verdict == "contradicted" and contra:
        final = "contradicted"
        if not strong(contra):
            notes.append(tr("j.weak_refute"))
    elif verdict == "supported" and support and mismatch:
        final = "contradicted"
        notes.append(tr("j.other_numbers"))
    elif verdict == "supported" and support and strong(support):
        final = "supported"
    elif verdict == "supported" and support:
        final = "unverifiable"
        reason = tr("j.weak_support") + reason
    else:
        final = "unverifiable"
        if verdict != "insufficient":
            reason = tr("j.no_verified") + reason
        elif not reason:
            reason = tr("j.neither")
    notes.insert(0, tr("j.attack_note", prov=_provider_ru(info.provider), n=info.pages))
    return ClaimResult(claim_id=claim.id, verdict=final, mode="attack", reason=reason, evidence=evidence,  # type: ignore[arg-type]
                       numbers=numbers, notes=notes, search=info)


def _dom(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.")


def _provider_ru(p: str) -> str:
    return tr("prov.web") if p == "tavily" else tr("prov.wiki")


def _in_lang(system: str) -> str:
    """The judge prompts ask for the reason "по-русски"; switch that to the user's language and repeat it
    at the very end, where weaker models actually follow it."""
    lang = LLM_LANGUAGE[current()]
    tail = "" if current() == "ru" else f"\n\nВАЖНО: поле reason пиши {lang}, даже если утверждение и источник на другом языке."
    return system.replace("по-русски", lang) + tail


def _llm_error(e: Exception) -> str:
    return tr("j.llm_quota") if isinstance(e, llm.QuotaExhausted) else tr("j.llm_fail", err=e)


async def judge_claim(claim: Claim, cits: list[Citation], checks: dict[str, SourceCheck],
                      texts: dict[str, SourceText]) -> ClaimResult:
    """One entry point for every claim.
    - no source given → search the web for support AND refutation;
    - a source is given → judge against it; if it could not be read (paywall, bot wall, abstract without the
      fact), check the claim on the open web instead of stopping at "could not check"."""
    if not cits:
        queries = claim.queries or [claim.text[:160]]
        return await judge_attack(claim, await search.gather_evidence(queries), queries)
    res = await judge_cited(claim, cits, checks, texts)
    if res.verdict != "unverifiable" or res.error or res.evidence:
        return res
    queries = claim.queries or [claim.text[:160]]
    web = await judge_attack(claim, await search.gather_evidence(queries), queries)
    if web.verdict in ("supported", "contradicted"):
        web.notes.insert(0, tr("j.fallback_note"))
        return web
    return res
