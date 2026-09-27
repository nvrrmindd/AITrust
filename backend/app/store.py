"""Jobs, event fan-out, on-disk cache and shareable reports."""
from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

from .config import settings
from .pipeline import PIPELINE_VERSION, run


@dataclass
class Job:
    id: str
    text: str
    events: list[dict] = field(default_factory=list)
    done: bool = False
    cached: bool = False
    filename: Optional[str] = None  # set for «Работа целиком» (uploaded paper)
    created: float = field(default_factory=time.time)
    cond: asyncio.Condition = field(default_factory=asyncio.Condition)


_jobs: dict[str, Job] = {}


def text_key(text: str, mode: str = "") -> str:
    prefix = f"{PIPELINE_VERSION}\n" + (f"{mode}\n" if mode else "")
    return hashlib.sha256(f"{prefix}{text.strip()}".encode()).hexdigest()[:24]


def _key(job: "Job") -> str:
    return text_key(job.text, "document" if job.filename else "")


def _cache_path(key: str):
    return settings.data_dir / "cache" / f"{key}.json"


def _report_path(rid: str):
    return settings.data_dir / "reports" / f"{rid}.json"


def _transient(events: list[dict]) -> bool:
    """A run hit a temporary failure (database busy, LLM quota): show it, but don't cache it, so a retry re-checks."""
    for e in events:
        if e["type"] == "error":
            return True
        chk = e.get("check") or {}
        items = [it.get("check") or {} for it in e.get("items", [])] if e["type"] == "bibliography" else [chk]
        if any(c.get("status") == "unreachable" and "повторите" in c.get("detail", "") for c in items):
            return True
        if e["type"] == "claim" and e["result"]["reason"].startswith(("Сбой модели", "Внутренняя ошибка")):
            return True
    return False


def _save_report(job: Job) -> None:
    payload = {"id": job.id, "text": job.text, "events": job.events, "created": job.created, "filename": job.filename}
    _report_path(job.id).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    if not _transient(job.events):
        _cache_path(_key(job)).write_text(json.dumps(job.events, ensure_ascii=False), encoding="utf-8")


def load_report(rid: str) -> Optional[dict]:
    if rid in _jobs and _jobs[rid].done:
        j = _jobs[rid]
        return {"id": j.id, "text": j.text, "events": j.events, "created": j.created, "filename": j.filename}
    p = _report_path(rid)
    if p.exists() and rid.replace("-", "").replace("_", "").isalnum():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def start(text: str, filename: Optional[str] = None) -> Job:
    jid = secrets.token_urlsafe(6)
    job = Job(id=jid, text=text, filename=filename)
    _jobs[jid] = job
    cached = _cache_path(_key(job))
    if cached.exists():
        job.events = json.loads(cached.read_text(encoding="utf-8"))
        job.done = job.cached = True
        _save_report(job)
    else:
        asyncio.create_task(_run(job))
    _gc()
    return job


async def _run(job: Job) -> None:
    try:
        if job.filename:
            from .bibliography import run_document
            events = run_document(job.text, job.filename)
        else:
            events = run(job.text)
        async for ev in events:
            async with job.cond:
                job.events.append(ev)
                job.cond.notify_all()
    except Exception as e:  # noqa: BLE001
        async with job.cond:
            job.events.append({"type": "error", "message": f"{type(e).__name__}: {e}"})
    finally:
        async with job.cond:
            job.done = True
            job.cond.notify_all()
        _save_report(job)


async def stream(jid: str) -> AsyncIterator[dict]:
    job = _jobs.get(jid)
    if job is None:
        rep = load_report(jid)
        if rep is None:
            yield {"type": "error", "message": "Отчёт не найден."}
            return
        for ev in rep["events"]:
            yield ev
        return
    if job.cached:
        # replay of a REAL earlier run of the same text, paced so the UI can animate
        yield {"type": "cached"}
        for ev in job.events:
            if ev["type"] in ("claim", "source") or (ev["type"] == "bibliography" and len(ev.get("items", [])) == 1):
                await asyncio.sleep(0.35)
            yield ev
        return
    i = 0
    while True:
        async with job.cond:
            while i >= len(job.events) and not job.done:
                await job.cond.wait()
            batch = job.events[i:]
            finished = job.done
        for ev in batch:
            yield ev
        i += len(batch)
        if finished and i >= len(job.events):
            return


def _gc() -> None:
    cutoff = time.time() - 3600
    for k in [k for k, j in _jobs.items() if j.done and j.created < cutoff]:
        _jobs.pop(k, None)
