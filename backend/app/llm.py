"""Minimal LLM client: OpenAI-compatible (OpenAI, Groq, OpenRouter) or Anthropic, JSON output only."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from .config import DEFAULT_BASE, PROVIDERS, settings

log = logging.getLogger("pruf.llm")


class LLMError(Exception):
    pass


class RateLimited(LLMError):
    def __init__(self, msg: str, wait: float, daily: bool = False):
        super().__init__(msg)
        self.wait = wait
        self.daily = daily  # the model's daily quota is gone: waiting won't help, switch models


# models whose daily free-tier quota ran out in this process (reset on restart)
_exhausted: set[str] = set()


# Free tiers (Groq: 8k tokens/min) choke on parallel judge calls; keep a small queue.
_sem = asyncio.Semaphore(settings.llm_concurrency)


def _retry_after(r: httpx.Response) -> float:
    try:
        return min(float(r.headers.get("retry-after", "")), 60.0)
    except ValueError:
        m = re.search(r"try again in ([\d.]+)(ms|s)", r.text)
        if m:
            v = float(m.group(1))
            return min(v / 1000 if m.group(2) == "ms" else v, 60.0)
    return 5.0


def _raise_for(r: httpx.Response) -> None:
    if r.status_code == 429:
        daily = bool(re.search(r"PerDay|per day|\(TPD\)|\(RPD\)", r.text, re.I))
        raise RateLimited(f"LLM HTTP 429: {r.text[:300]}", _retry_after(r), daily)
    if r.status_code in (500, 502, 503, 504):  # "model is experiencing high demand" — transient, wait and retry
        raise RateLimited(f"LLM HTTP {r.status_code}: {r.text[:300]}", 4.0)
    if r.status_code >= 400:
        raise LLMError(f"LLM HTTP {r.status_code}: {r.text[:300]}")


def _extract_json(text: str) -> Any:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise LLMError("no JSON in model output")
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    end = text.rfind(closer)
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise LLMError(f"bad JSON from model: {e}") from e


@dataclass(frozen=True)
class Endpoint:
    provider: str
    model: str
    base_url: str
    key: str

    @property
    def name(self) -> str:
        return f"{self.provider}:{self.model}"


def _endpoint(entry: str) -> Optional[Endpoint]:
    """"gemini:gemini-3.6-flash", "groq:openai/gpt-oss-120b" or a bare model name of LLM_PROVIDER."""
    prov, _, model = entry.partition(":")
    if prov not in PROVIDERS or not model:
        prov, model = settings.llm_provider, entry
    key = settings.key_for(prov)
    if not key:
        return None
    base = settings.llm_base_url if prov == settings.llm_provider else DEFAULT_BASE.get(prov, DEFAULT_BASE["openai"])
    return Endpoint(prov, model, base, key)


def endpoints_for(role: str) -> list[Endpoint]:
    """LLM_MODEL_JUDGE / LLM_MODEL_EXTRACT are fallback chains, possibly across providers:
    "gemini:gemini-3.6-flash,gemini:gemini-3.5-flash,groq:openai/gpt-oss-120b". Entries without a key are skipped."""
    spec = {"extract": settings.llm_model_extract, "judge": settings.llm_model_judge}.get(role, settings.llm_model)
    return [ep for e in spec.split(",") if e.strip() and (ep := _endpoint(e.strip()))]


def endpoint_for(role: str) -> Optional[Endpoint]:
    chain = endpoints_for(role)
    return next((ep for ep in chain if ep.name not in _exhausted), None)


def model_for(role: str) -> str:
    ep = endpoint_for(role)
    return ep.name if ep else "none"


async def complete_json(system: str, user: str, *, max_tokens: int = 2000, role: str = "judge") -> Any:
    """role: "extract" (parsing, fast model) or "judge" (verdicts, strongest model)."""
    if not endpoints_for(role):
        raise LLMError("LLM_API_KEY is not set")
    last: Exception | None = None
    failures = 0
    for _ in range(20):  # 429/503 waits are cheap; other errors stop after 3
        ep = endpoint_for(role)
        if ep is None:
            break  # every model of the chain is out for today
        try:
            async with _sem:
                if ep.provider == "anthropic":
                    text = await _anthropic(system, user, max_tokens, ep)
                else:
                    text = await _openai_compatible(system, user, max_tokens, ep, role)
            data = _extract_json(text)
            if not isinstance(data, dict):
                raise LLMError(f"expected a JSON object, got {type(data).__name__}")
            return data
        except RateLimited as e:
            last = e
            if e.daily:
                _exhausted.add(ep.name)
                log.warning("LLM %s: daily quota exhausted, switching to %s", ep.name, model_for(role))
                continue
            log.warning("LLM %s rate limited, waiting %.1fs", ep.name, e.wait)
            await asyncio.sleep(e.wait + 0.5)
        except (httpx.HTTPError, LLMError) as e:
            last = e
            failures += 1
            log.warning("LLM %s attempt %s failed: %s", ep.name, failures, e)
            if failures >= 3:
                break
    raise LLMError(str(last))


async def _openai_compatible(system: str, user: str, max_tokens: int, ep: Endpoint, role: str) -> str:
    model = ep.model
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if "gpt-oss" in model:
        # Reasoning model: keep thinking short so it doesn't eat the max_tokens budget.
        payload["reasoning_effort"] = "low"
    elif model.startswith("gemini"):
        # Gemini thinks by default and thinking counts against max_tokens: parse fast, let the judge think.
        payload["reasoning_effort"] = "low" if role == "extract" else "medium"
        payload["max_tokens"] = max_tokens + 8192
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post(
            ep.base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {ep.key}"},
            json=payload,
        )
    _raise_for(r)
    return r.json()["choices"][0]["message"]["content"]


async def _anthropic(system: str, user: str, max_tokens: int, ep: Endpoint) -> str:
    payload = {
        "model": ep.model,
        "max_tokens": max_tokens,
        "temperature": 0,
        "system": system + "\n\nОтвечай ТОЛЬКО валидным JSON без пояснений.",
        "messages": [{"role": "user", "content": user}],
    }
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post(
            ep.base_url.rstrip("/") + "/v1/messages",
            headers={
                "x-api-key": ep.key,
                "anthropic-version": "2023-06-01",
            },
            json=payload,
        )
    _raise_for(r)
    return "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")
