"""Accuracy benchmark: how often does Пруф get it right, and — most importantly — how often does it
falsely accuse a REAL source of being fake?

Layout (fill it in as a team, see benchmark/README.md):
    benchmark/answers/<answer_id>.txt       real AI answers you collected (ChatGPT, Gemini, Claude...)
    benchmark/labels_sources.csv            answer_id,source_ref,label        label = real | fake
    benchmark/labels_claims.csv             answer_id,claim_ref,label         label = correct | wrong

source_ref / claim_ref = any distinctive substring of the citation / claim (e.g. the DOI, "[3]", a phrase).

    cd backend && python -m app.benchmark
"""
from __future__ import annotations

import asyncio
import csv
import json
from collections import Counter
from pathlib import Path

from .pipeline import run
from .textutil import normalize

BENCH = Path(__file__).resolve().parent.parent.parent / "benchmark"


def _rows(name: str) -> list[dict]:
    p = BENCH / name
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if (r.get("answer_id") or "").strip()]


async def _run_one(text: str) -> tuple[list[dict], list[dict], dict[str, dict], dict[str, dict]]:
    claims, cits, checks, results = [], [], {}, {}
    async for ev in run(text):
        if ev["type"] == "extracted":
            claims, cits = ev["claims"], ev["citations"]
        elif ev["type"] == "source":
            checks[ev["check"]["citation_id"]] = ev["check"]
        elif ev["type"] == "claim":
            results[ev["result"]["claim_id"]] = ev["result"]
    return claims, cits, checks, results


def _find(ref: str, items: list[dict], fields: list[str]) -> dict | None:
    r = normalize(ref)
    for it in items:
        if any(r and r in normalize(str(it.get(f) or "")) for f in fields):
            return it
    return None


async def main() -> None:
    src_labels, claim_labels = _rows("labels_sources.csv"), _rows("labels_claims.csv")
    answer_ids = sorted({r["answer_id"] for r in src_labels + claim_labels})
    if not answer_ids:
        print("No labels yet. See benchmark/README.md")
        return

    src = Counter()
    claim = Counter()
    errors: list[str] = []
    for aid in answer_ids:
        text = (BENCH / "answers" / f"{aid}.txt").read_text(encoding="utf-8")
        claims, cits, checks, results = await _run_one(text)
        for row in [r for r in src_labels if r["answer_id"] == aid]:
            c = _find(row["source_ref"], cits, ["raw", "doi", "url", "title"])
            if not c:
                src["unmatched"] += 1
                errors.append(f"{aid}: source not extracted: {row['source_ref']}")
                continue
            status = checks.get(c["id"], {}).get("status", "unchecked")
            pred_fake = status == "not_found"
            label_fake = row["label"].strip().lower() == "fake"
            key = ("tp" if pred_fake else "fn") if label_fake else ("fp" if pred_fake else "tn")
            src[key] += 1
            if status in ("unreachable", "unchecked"):
                src["abstained"] += 1
            if key in ("fp", "fn"):
                errors.append(f"{aid}: {key.upper()} {row['source_ref']} -> {status}")
        for row in [r for r in claim_labels if r["answer_id"] == aid]:
            c = _find(row["claim_ref"], claims, ["span", "text"])
            if not c:
                claim["unmatched"] += 1
                continue
            v = results.get(c["id"], {}).get("verdict", "unverifiable")
            wrong = row["label"].strip().lower() == "wrong"
            if v == "unverifiable":
                claim["abstained"] += 1
            elif (v != "supported") == wrong:
                claim["correct"] += 1
            else:
                claim["incorrect"] += 1
                errors.append(f"{aid}: claim '{row['claim_ref'][:50]}' labeled {row['label']} but got {v}")

    tp, fp, fn, tn = src["tp"], src["fp"], src["fn"], src["tn"]
    report = {
        "answers": len(answer_ids),
        "sources_labeled": tp + fp + fn + tn,
        "fake_sources_caught": f"{tp}/{tp + fn}" + (f" ({100 * tp / (tp + fn):.0f}%)" if tp + fn else ""),
        "false_accusations_of_real_sources": f"{fp}/{fp + tn}" + (f" ({100 * fp / (fp + tn):.1f}%)" if fp + tn else ""),
        "precision_when_we_say_fake": f"{100 * tp / (tp + fp):.0f}%" if tp + fp else "n/a",
        "source_abstentions": src["abstained"],
        "claims_labeled": claim["correct"] + claim["incorrect"] + claim["abstained"],
        "claim_accuracy_when_we_decide": (f"{100 * claim['correct'] / (claim['correct'] + claim['incorrect']):.0f}%"
                                          if claim["correct"] + claim["incorrect"] else "n/a"),
        "claim_abstentions": claim["abstained"],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        print("\nErrors to review:\n  " + "\n  ".join(errors))
    (BENCH / "results.json").write_text(json.dumps({"report": report, "errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
