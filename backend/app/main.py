"""HTTP API + static frontend in one process (one URL to deploy and to send to the jury)."""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from . import store
from .config import settings
from .models import CheckRequest
from .pipeline import PIPELINE_VERSION

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = FastAPI(title="Пруф API", version=PIPELINE_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

EXAMPLES_FILE = Path(__file__).resolve().parent.parent / "examples.json"
_hits: dict[str, deque] = defaultdict(deque)


@app.on_event("startup")
def _seed() -> None:
    from .prewarm import install_seed_cache

    n = install_seed_cache()
    logging.getLogger("pruf").info("seed cache: %s runs installed; llm=%s; search=%s", n,
                                   bool(settings.llm_api_key), "tavily" if settings.tavily_api_key else "wikipedia")


def _client_ip(req: Request) -> str:
    fwd = req.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (req.client.host if req.client else "?")


def _rate_limited(ip: str) -> bool:
    q, now = _hits[ip], time.time()
    while q and q[0] < now - 3600:
        q.popleft()
    if len(q) >= settings.rate_limit_per_hour:
        return True
    q.append(now)
    return False


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "version": PIPELINE_VERSION,
        "llm_configured": bool(settings.llm_api_key),
        "llm": f"{settings.llm_provider}:{settings.llm_model}",
        "search": "tavily" if settings.tavily_api_key else "wikipedia",
    }


@app.get("/api/examples")
def examples() -> list[dict]:
    return json.loads(EXAMPLES_FILE.read_text(encoding="utf-8")) if EXAMPLES_FILE.exists() else []


@app.post("/api/check")
async def create_check(body: CheckRequest, request: Request) -> dict:
    text = body.text.strip()
    if len(text) > settings.max_text_chars:
        raise HTTPException(413, f"Слишком длинный текст: максимум {settings.max_text_chars} символов.")
    cached = store._cache_path(store.text_key(text)).exists()
    if not cached:
        if not settings.llm_api_key:
            raise HTTPException(503, "Сервер не настроен: не задан LLM_API_KEY. Попробуйте один из примеров.")
        if _rate_limited(_client_ip(request)):
            raise HTTPException(429, "Слишком много проверок подряд. Подождите немного.")
    job = store.start(text)
    return {"id": job.id, "cached": job.cached}


@app.get("/api/check/{jid}/events")
async def events(jid: str) -> StreamingResponse:
    async def gen():
        async for ev in store.stream(jid):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/reports/{rid}")
def report(rid: str) -> dict:
    rep = store.load_report(rid)
    if rep is None:
        raise HTTPException(404, "Отчёт не найден")
    return rep


# ---------------------------------------------------------------- static frontend (SPA)

@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    root = settings.static_dir
    if path.startswith("api/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    target = (root / path).resolve()
    if path and target.is_file() and root.resolve() in target.parents:
        return FileResponse(target)
    index = root / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"detail": "frontend not built — run `npm run build` in frontend/"}, status_code=404)
