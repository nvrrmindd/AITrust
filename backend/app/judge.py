"""Verdicts. The LLM proposes, the code disposes:
- every quote the LLM returns must be found (almost) verbatim in the source text, otherwise it is dropped;
- numbers are compared deterministically, independent of the LLM;
- an abstract that doesn't mention a claim is NOT evidence against it (-> unverifiable, not "not in source").
"""
from __future__ import annotations

import logging

from . import llm
from .models import Citation, Claim, ClaimResult, Evidence, NumberCheck, SourceCheck
from .prompts import JUDGE_ATTACK_SYSTEM, JUDGE_CITED_SYSTEM
from .search import Hit
from .sources import SourceText
from .textutil import chunk, number_mismatch, quote_in_text, rank_passages

log = logging.getLogger("pruf.judge")

QUOTE_DROPPED = "Модель-судья не смогла привести дословную цитату из источника — её вердикт отброшен."


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
        return ClaimResult(claim_id=claim.id, verdict="unverifiable", mode="cited", reason="Источник не распознан.")
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


async def _judge_one_source(claim: Claim, cit: Citation, sc: SourceCheck, st: SourceText) -> ClaimResult:
    label = _label(cit, sc)
    url = _source_url(cit, sc, st)

    if sc.status == "not_found":
        return ClaimResult(claim_id=claim.id, verdict="source_missing", mode="cited",
                           reason=f"Утверждение опирается на источник, которого не существует. {sc.detail}")
    if sc.status in ("unreachable", "unchecked") or st.scope == "none" or len(st.text) < 80:
        why = sc.detail if sc.status in ("unreachable", "unchecked") else "Текст источника недоступен."
        return ClaimResult(claim_id=claim.id, verdict="unverifiable", mode="cited",
                           reason=f"Не удалось прочитать источник, поэтому честно не выносим вердикт. {why}")

    passages = chunk(st.text)
    top = rank_passages(claim.text, passages, k=6)
    selected = [passages[i] for i, _ in top]
    block = "\n\n".join(f"[P{n + 1}] {p}" for n, p in enumerate(selected))
    user = (
        f"Утверждение: {claim.text}\n\nИсточник: {label}"
        f"{' (доступна только аннотация)' if st.scope == 'abstract' else ''}\n\nФрагменты:\n{block}"
    )
    try:
        out = await llm.complete_json(JUDGE_CITED_SYSTEM, user, max_tokens=600)
    except llm.LLMError as e:
        return ClaimResult(claim_id=claim.id, verdict="unverifiable", mode="cited", reason=f"Сбой модели-судьи: {e}")

    verdict = str(out.get("verdict", "not_mentioned"))
    quote = str(out.get("quote") or "").strip()
    reason = str(out.get("reason") or "").strip()
    notes: list[str] = []
    evidence: list[Evidence] = []

    quote_ok = bool(quote) and quote_in_text(quote, st.text)
    if quote and not quote_ok:
        notes.append(QUOTE_DROPPED)
    if quote_ok:
        stance = {"supports": "supports", "contradicts": "contradicts", "partially": "contradicts"}.get(verdict, "neutral")
        evidence.append(Evidence(source_label=label, url=url, citation_id=cit.id, quote=quote, quote_verified=True, stance=stance))  # type: ignore[arg-type]

    # deterministic number check over the quote + the best passages
    context = " ".join([quote] + selected[:2]) if quote_ok else " ".join(selected[:2])
    cn, sn, mismatch = number_mismatch(claim.text, context)
    numbers = NumberCheck(claim_numbers=cn, source_numbers=sn[:12], mismatch=mismatch) if cn else None

    if verdict in ("supports", "partially", "contradicts") and not quote_ok:
        final = "unverifiable"
        reason = "Модель нашла что-то похожее, но не смогла подтвердить это дословной цитатой. Вердикт не выносим."
    elif verdict == "supports":
        if mismatch:
            final = "contradicted"
            notes.append("Цифры в утверждении не совпадают с цифрами в источнике.")
            reason = (f"Источник говорит о том же, но с другими числами: в ответе ИИ — {', '.join(cn)}, "
                      f"в источнике — {', '.join(sn[:4])}.")
        else:
            final = "supported"
    elif verdict in ("contradicts", "partially"):
        final = "contradicted"
        if verdict == "partially":
            notes.append("Источник говорит о более узком или осторожном утверждении, чем ответ ИИ.")
    else:  # not_mentioned
        if st.scope == "abstract":
            final = "unverifiable"
            reason = "В аннотации статьи этого нет, а полный текст недоступен — подтвердить или опровергнуть нельзя."
        else:
            final = "not_in_source"
            reason = reason or "Источник существует и прочитан, но этого утверждения в нём нет."

    if sc.status == "mismatch":
        notes.append("Данные источника в ответе ИИ искажены: " + ("; ".join(sc.differences) if sc.differences else sc.detail))
    if st.scope == "abstract":
        notes.append("Проверено по аннотации статьи (полный текст недоступен).")

    return ClaimResult(claim_id=claim.id, verdict=final, mode="cited", reason=reason, evidence=evidence, numbers=numbers, notes=notes)  # type: ignore[arg-type]


async def judge_attack(claim: Claim, hits: list[Hit]) -> ClaimResult:
    """A claim with no source: search for support AND refutation, judge, verify quotes."""
    if not hits:
        return ClaimResult(claim_id=claim.id, verdict="unverifiable", mode="attack",
                           reason="ИИ не указал источник, а поиск ничего релевантного не нашёл. Это утверждение ничем не подкреплено.")
    passages: list[tuple[Hit, str]] = []
    for h in hits:
        ch = chunk(h.snippet) or [h.snippet[:900]]
        for i, _ in rank_passages(claim.text, ch, k=2):
            passages.append((h, ch[i]))
    ranked = rank_passages(claim.text, [p for _, p in passages], k=8)
    chosen = [passages[i] for i, _ in ranked]
    block = "\n\n".join(
        f"[P{n + 1} | {h.domain}{' | найдено запросом-опровержением' if h.adversarial else ''}] {p}" for n, (h, p) in enumerate(chosen)
    )
    try:
        out = await llm.complete_json(JUDGE_ATTACK_SYSTEM, f"Утверждение: {claim.text}\n\nФрагменты:\n{block}", max_tokens=800)
    except llm.LLMError as e:
        return ClaimResult(claim_id=claim.id, verdict="unverifiable", mode="attack", reason=f"Сбой модели-судьи: {e}")

    evidence: list[Evidence] = []
    notes: list[str] = []
    dropped = 0
    for ev in out.get("evidence") or []:
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
        evidence.append(Evidence(source_label=h.title or h.domain, url=h.url, quote=q, quote_verified=True, stance=stance))  # type: ignore[arg-type]
    if dropped:
        notes.append(f"{dropped} цитат(ы) модели не нашлись в источниках дословно и были отброшены.")

    verdict = str(out.get("verdict", "insufficient"))
    reason = str(out.get("reason") or "").strip()
    has_contra = any(e.stance == "contradicts" for e in evidence)
    has_support = any(e.stance == "supports" for e in evidence)

    cn, sn, mismatch = number_mismatch(claim.text, " ".join(e.quote for e in evidence))
    numbers = NumberCheck(claim_numbers=cn, source_numbers=sn[:12], mismatch=mismatch) if cn else None

    if verdict == "contradicted" and has_contra:
        final = "contradicted"
    elif verdict == "supported" and has_support and not mismatch:
        final = "supported"
    elif verdict == "supported" and has_support and mismatch:
        final = "contradicted"
        notes.append("Найденные источники приводят другие числа.")
    else:
        final = "unverifiable"
        if verdict != "insufficient":
            reason = "Модель что-то нашла, но не подтвердила это дословными цитатами. " + reason
    notes.insert(0, "ИИ не дал источник — мы искали и подтверждения, и опровержения.")
    return ClaimResult(claim_id=claim.id, verdict=final, mode="attack", reason=reason, evidence=evidence, numbers=numbers, notes=notes)  # type: ignore[arg-type]
