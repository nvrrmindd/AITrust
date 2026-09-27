"""Run the example answers through the REAL pipeline and save the results as seed cache.

    cd backend && python -m app.prewarm              # all examples
    cd backend && python -m app.prewarm kazakhstan   # only these ids
    cd backend && python -m app.prewarm docx         # only the sample coursework (.docx, «Документ»)
    cd backend && python -m app.prewarm --lang en    # the same, with verdicts in English (also: kk)

The saved runs are committed in backend/seed_cache/ and copied into the cache at startup, so the
demo examples open instantly even on a fresh free-tier server. They are real runs, replayed —
re-run this script whenever you change the pipeline or the examples.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

from .config import settings
from .i18n import LANG, norm_lang
from .pipeline import run
from .store import _transient, text_key

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "seed_cache"


def install_seed_cache() -> int:
    """Copy committed seed runs into the runtime cache (called on startup)."""
    n = 0
    if SEED.exists():
        for f in SEED.glob("*.json"):
            target = settings.data_dir / "cache" / f.name
            if not target.exists():
                shutil.copy(f, target)
                n += 1
    return n


async def main() -> None:
    SEED.mkdir(exist_ok=True)
    examples = json.loads((ROOT / "examples.json").read_text(encoding="utf-8"))
    args = sys.argv[1:]
    lang = "ru"
    if "--lang" in args:
        i = args.index("--lang")
        lang = norm_lang(args[i + 1] if i + 1 < len(args) else "ru")
        args = args[:i] + args[i + 2:]
    LANG.set(lang)
    only = set(args)
    if only:
        examples = [ex for ex in examples if ex["id"] in only]
    if not only or "docx" in only:
        await _prewarm_docx()
    for ex in examples:
        print(f"\n=== {ex['id']}: {ex['title']}")
        events = []
        async for ev in run(ex["text"]):
            events.append(ev)
            if ev["type"] == "claim":
                r = ev["result"]
                print(f"  {r['claim_id']}: {r['verdict']:<15} {r['reason'][:110]}")
            elif ev["type"] == "source":
                c = ev["check"]
                print(f"  {c['citation_id']}: {c['status']:<12} {c['detail'][:110]}")
            elif ev["type"] == "done":
                print("  =>", ev["summary"]["headline"], f"({ev['summary']['duration_ms']} ms)")
        if _transient(events):
            print("  NOT SAVED: temporary failures (quota / busy database) — rerun later")
            continue
        payload = json.dumps(events, ensure_ascii=False)
        key = text_key(ex["text"], "", lang)
        (SEED / f"{key}.json").write_text(payload, encoding="utf-8")
        (settings.data_dir / "cache" / f"{key}.json").write_text(payload, encoding="utf-8")
    print(f"\nSaved {len(examples)} runs to {SEED}")


def _save(key: str, events: list[dict]) -> None:
    payload = json.dumps(events, ensure_ascii=False)
    (SEED / f"{key}.json").write_text(payload, encoding="utf-8")
    (settings.data_dir / "cache" / f"{key}.json").write_text(payload, encoding="utf-8")


async def _prewarm_docx() -> None:
    """The «Работа целиком» demo: backend/examples/sample_coursework.docx."""
    from .bibliography import run_document
    from .documents import extract_text

    name = "sample_coursework.docx"
    text = extract_text(name, (ROOT / "examples" / name).read_bytes())
    print(f"\n=== docx: {name}")
    events = []
    async for ev in run_document(text, name):
        events.append(ev)
        if ev["type"] == "score":
            print("  score:", ev["score"])
        elif ev["type"] == "claim":
            r = ev["result"]
            print(f"  {r['claim_id']}: {r['verdict']:<15} {r['reason'][:110]}")
        elif ev["type"] == "done":
            print("  =>", ev["summary"]["headline"], f"({ev['summary']['duration_ms']} ms)")
    if _transient(events):
        print("  NOT SAVED: temporary failures (quota / busy database) — rerun later")
        return
    _save(text_key(text, "document", LANG.get()), events)


if __name__ == "__main__":
    asyncio.run(main())
