"""Run the example answers through the REAL pipeline and save the results as seed cache.

    cd backend && python -m app.prewarm

The saved runs are committed in backend/seed_cache/ and copied into the cache at startup, so the
demo examples open instantly even on a fresh free-tier server. They are real runs, replayed —
re-run this script whenever you change the pipeline or the examples.
"""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from .config import settings
from .pipeline import run
from .store import text_key

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
        payload = json.dumps(events, ensure_ascii=False)
        key = text_key(ex["text"])
        (SEED / f"{key}.json").write_text(payload, encoding="utf-8")
        (settings.data_dir / "cache" / f"{key}.json").write_text(payload, encoding="utf-8")
    print(f"\nSaved {len(examples)} runs to {SEED}")


if __name__ == "__main__":
    asyncio.run(main())
