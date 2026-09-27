"""Accuracy evaluation on the team's labelled sets (numbers for the pitch).

    cd backend && python -m app.eval                      # claims + refs
    cd backend && python -m app.eval --only refs          # only references.csv (almost no LLM tokens)
    cd backend && python -m app.eval --only hard --limit 20
    cd backend && python -m app.eval --fresh              # ignore benchmark/eval_cache

benchmark/claims.csv       id,lang,topic,claim,label(true|false),mutation,source_url
benchmark/claims_hard.csv  id,lang,topic,claim,label(true|false|unsupported),mutation,difficulty,source_url
benchmark/references.csv   id,reference,label(real|fake|distorted),note

Claims go through the full pipeline (each claim is its own text, no source given -> search + judge).
References do NOT: they are parsed by regex into a Citation and sent straight to check_citation (no LLM);
the LLM is asked (one batch) only for references where regex found neither a DOI nor a title.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

from . import llm
from .bibliography import _BATCH_SYSTEM, Reference, parse_reference
from .config import settings
from .extract import _norm_citation
from .models import Citation
from .pipeline import run
from .sources import check_citation

BENCH = Path(__file__).resolve().parent.parent.parent / "benchmark"
CACHE = BENCH / "eval_cache"
PARALLEL_CLAIMS = 2  # every claim = LLM extract + LLM judge: free-tier rate limits
PARALLEL_REFS = 4    # references are network-only; Crossref/OpenAlex throttle bursts

CLAIM_MAP = {"supported": "true", "contradicted": "false", "not_in_source": "false", "source_missing": "false",
             "unverifiable": "abstain"}
REF_MAP = {"not_found": "fake", "mismatch": "distorted", "exists": "real", "unreachable": "abstain", "unchecked": "abstain"}


def _rows(name: str) -> list[dict]:
    p = BENCH / name
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if (r.get("id") or "").strip()]


def _cached(key: str, fresh: bool) -> dict | None:
    p = CACHE / f"{key}.json"
    return None if fresh or not p.exists() else json.loads(p.read_text(encoding="utf-8"))


def _store(key: str, rec: dict) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / f"{key}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


# ---------------------------------------------------------------- claims

async def eval_claim(row: dict, fresh: bool) -> dict:
    if rec := _cached(row["id"], fresh):
        return rec
    t0 = time.time()
    results, error = [], ""
    try:
        async for ev in run(row["claim"]):
            if ev["type"] == "claim":
                results.append(ev["result"])
            elif ev["type"] == "error":
                error = ev["message"]
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}: {e}"
    verdicts = [CLAIM_MAP.get(r["verdict"], "abstain") for r in results]
    # one claim per row; if the extractor split it, any refutation wins, "true" needs all parts supported
    if "false" in verdicts:
        got = "false"
    elif verdicts and all(v == "true" for v in verdicts):
        got = "true"
    else:
        got = "abstain"
    main = next((r for r in results if CLAIM_MAP.get(r["verdict"]) == got), results[0] if results else None)
    return _store(row["id"], {
        "id": row["id"], "kind": "claim", "text": row["claim"], "expected": row["label"], "got": got,
        "verdict": main["verdict"] if main else None,
        "reason": (main["reason"] if main else error or "Утверждение не выделено"),
        "quote": (main["evidence"][0]["quote"] if main and main.get("evidence") else ""),
        "seconds": round(time.time() - t0, 1), "model": llm.model_for("judge"),
    })


# ---------------------------------------------------------------- references

async def _llm_fill(rows: list[dict], cits: dict[str, Citation]) -> None:
    """ONE batch request for references where regex found neither a DOI nor a title."""
    todo = [r for r in rows if not cits[r["id"]].doi and not cits[r["id"]].title]
    if not todo:
        return
    block = "\n".join(f"{i + 1}. {r['reference']}" for i, r in enumerate(todo))
    try:
        out = await llm.complete_json(_BATCH_SYSTEM, f"Ссылки:\n{block}", max_tokens=300 + 150 * len(todo), role="extract")
    except llm.LLMError as e:
        print(f"  LLM batch for {len(todo)} refs failed: {e}")
        return
    for item in out.get("refs") or []:
        try:
            r = todo[int(item.get("n")) - 1]
        except (TypeError, ValueError, IndexError):
            continue
        cits[r["id"]] = _norm_citation({**item, "id": r["id"], "raw": r["reference"]}, 1)


async def eval_refs(rows: list[dict], fresh: bool) -> list[dict]:
    out: dict[str, dict] = {}
    todo = []
    for r in rows:
        if rec := _cached(r["id"], fresh):
            out[r["id"]] = rec
        else:
            todo.append(r)
    cits = {r["id"]: parse_reference(Reference(1, r["reference"]))[0] for r in todo}
    for r in todo:
        cits[r["id"]].id = r["id"]
    await _llm_fill(todo, cits)
    sem = asyncio.Semaphore(PARALLEL_REFS)

    async def one(r: dict) -> None:
        async with sem:
            t0 = time.time()
            sc, _ = await check_citation(cits[r["id"]])
        c = cits[r["id"]]
        out[r["id"]] = _store(r["id"], {
            "id": r["id"], "kind": "ref", "text": r["reference"], "expected": r["label"], "got": REF_MAP[sc.status],
            "verdict": sc.status, "reason": sc.detail + (" " + "; ".join(sc.differences) if sc.differences else ""),
            "parsed": {"doi": c.doi, "url": c.url, "title": c.title, "year": c.year, "kind": c.kind},
            "seconds": round(time.time() - t0, 1),
        })

    await asyncio.gather(*(one(r) for r in todo))
    return [out[r["id"]] for r in rows]


# ---------------------------------------------------------------- metrics

def _pct(a: int, b: int) -> str:
    return f"{a}/{b} ({100 * a / b:.0f}%)" if b else "—"


def claim_metrics(recs: list[dict], rows: list[dict]) -> dict:
    by_id = {r["id"]: r for r in rows}
    decided = [r for r in recs if r["got"] != "abstain"]
    correct = [r for r in decided if r["got"] == r["expected"] or (r["expected"] == "unsupported" and r["got"] == "false")]
    tp = sum(1 for r in recs if r["got"] == "false" and r["expected"] in ("false", "unsupported"))
    fp = sum(1 for r in recs if r["got"] == "false" and r["expected"] == "true")
    fn = sum(1 for r in recs if r["got"] != "false" and r["expected"] in ("false", "unsupported"))
    groups: dict[str, dict[str, list]] = {"mutation": defaultdict(list), "lang": defaultdict(list)}
    for r in recs:
        for g in groups:
            groups[g][by_id[r["id"]].get(g) or "—"].append(r)
    acc = lambda rs: _pct(sum(1 for r in rs if r["got"] == r["expected"] or (r["expected"] == "unsupported" and r["got"] == "false")),  # noqa: E731
                          sum(1 for r in rs if r["got"] != "abstain"))
    unsupported = [r for r in recs if r["expected"] == "unsupported"]
    return {
        "n": len(recs),
        "coverage": _pct(len(decided), len(recs)),
        "accuracy_decided": _pct(len(correct), len(decided)),
        "false_precision": _pct(tp, tp + fp), "false_recall": _pct(tp, tp + fn),
        "true_called_false": _pct(fp, sum(1 for r in recs if r["expected"] == "true")),
        "unsupported_called_true": _pct(sum(1 for r in unsupported if r["got"] == "true"), len(unsupported)),
        "by_mutation": {k: acc(v) for k, v in sorted(groups["mutation"].items())},
        "by_lang": {k: acc(v) for k, v in sorted(groups["lang"].items())},
        "avg_seconds": round(sum(r["seconds"] for r in recs) / max(len(recs), 1), 1),
    }


def ref_metrics(recs: list[dict]) -> dict:
    exp = Counter(r["expected"] for r in recs)
    hit = lambda e, g: sum(1 for r in recs if r["expected"] == e and r["got"] in g)  # noqa: E731
    decided = [r for r in recs if r["got"] != "abstain"]
    return {
        "n": len(recs),
        "coverage": _pct(len(decided), len(recs)),
        "accuracy_decided": _pct(sum(1 for r in decided if r["got"] == r["expected"]), len(decided)),
        "fake_caught": _pct(hit("fake", {"fake"}), exp["fake"]),
        "distorted_caught": _pct(hit("distorted", {"distorted"}), exp["distorted"]),
        "distorted_flagged_any": _pct(hit("distorted", {"distorted", "fake"}), exp["distorted"]),
        "FALSE_ACCUSATIONS_real_called_fake": _pct(hit("real", {"fake"}), exp["real"]),
        "real_called_distorted": _pct(hit("real", {"distorted"}), exp["real"]),
        "avg_seconds": round(sum(r["seconds"] for r in recs) / max(len(recs), 1), 1),
    }


def _print(title: str, m: dict) -> None:
    print(f"\n=== {title}")
    for k, v in m.items():
        if isinstance(v, dict):
            print(f"  {k}:")
            for kk, vv in v.items():
                print(f"    {kk:<22} {vv}")
        else:
            print(f"  {k:<36} {v}")


def _errors_md(sections: list[tuple[str, list[dict]]]) -> str:
    out = ["# Ошибки оценки\n", f"Модель-судья: `{settings.llm_model_judge}`, поиск: {'Tavily' if settings.tavily_api_key else 'Википедия'}.\n"]
    for title, recs in sections:
        wrong = [r for r in recs if r["got"] != r["expected"] and not (r["expected"] == "unsupported" and r["got"] in ("false", "abstain"))]
        out.append(f"\n## {title}: {len(wrong)} из {len(recs)}\n")
        out.append("| id | текст | ожидалось | получили | вердикт | reason |\n|---|---|---|---|---|---|")
        for r in wrong:
            cell = lambda s: str(s or "").replace("|", "\\|").replace("\n", " ")[:300]  # noqa: E731
            out.append(f"| {r['id']} | {cell(r['text'])} | {r['expected']} | {r['got']} | {r['verdict']} | {cell(r['reason'])} |")
    return "\n".join(out) + "\n"


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=["claims", "hard", "refs"], action="append",
                    help="which set(s); default: claims + refs")
    ap.add_argument("--limit", type=int, default=0, help="first N rows of each set")
    ap.add_argument("--fresh", action="store_true", help="ignore benchmark/eval_cache")
    args = ap.parse_args()
    sets = args.only or ["claims", "refs"]
    cut = (lambda rows: rows[: args.limit]) if args.limit else (lambda rows: rows)
    results: dict[str, dict] = {"judge_model": settings.llm_model_judge, "extract_model": settings.llm_model_extract,
                                "search": "tavily" if settings.tavily_api_key else "wikipedia"}
    sections: list[tuple[str, list[dict]]] = []

    for name, file in (("claims", "claims.csv"), ("hard", "claims_hard.csv")):
        if name not in sets:
            continue
        rows = cut(_rows(file))
        sem = asyncio.Semaphore(PARALLEL_CLAIMS)
        done = 0

        async def one(r: dict) -> dict:
            nonlocal done
            async with sem:
                rec = await eval_claim(r, args.fresh)
            done += 1
            print(f"  [{done}/{len(rows)}] {r['id']}: {r['label']:<11} -> {rec['got']:<7} ({rec['verdict']})", flush=True)
            return rec

        print(f"\n{file}: {len(rows)} утверждений")
        recs = list(await asyncio.gather(*(one(r) for r in rows)))
        results[name] = claim_metrics(recs, rows)
        _print(f"{file}", results[name])
        sections.append((file, recs))

    if "refs" in sets:
        rows = cut(_rows("references.csv"))
        print(f"\nreferences.csv: {len(rows)} ссылок")
        recs = await eval_refs(rows, args.fresh)
        results["refs"] = ref_metrics(recs)
        _print("references.csv", results["refs"])
        sections.append(("references.csv", recs))

    (BENCH / "eval_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (BENCH / "eval_errors.md").write_text(_errors_md(sections), encoding="utf-8")
    print(f"\nСохранено: {BENCH / 'eval_results.json'}, {BENCH / 'eval_errors.md'}")


if __name__ == "__main__":
    asyncio.run(main())
