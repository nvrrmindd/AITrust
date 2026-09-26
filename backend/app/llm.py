"""Minimal LLM client: OpenAI-compatible (OpenAI, Groq, OpenRouter) or Anthropic, JSON output only."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx

from .config import settings

log = logging.getLogger("pruf.llm")


class LLMError(Exception):
    pass


class RateLimited(LLMError):
    def __init__(self, msg: str, wait: float):
        super().__init__(msg)
        self.wait = wait


# Free tiers (Groq: 8k tokens/min) choke on parallel judge calls; keep a small queue.
_sem = asyncio.Semaphore(2)


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
        raise RateLimited(f"LLM HTTP 429: {r.text[:300]}", _retry_after(r))
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


async def complete_json(system: str, user: str, *, max_tokens: int = 2000) -> Any:
    if not settings.llm_api_key:
        raise LLMError("LLM_API_KEY is not set")
    last: Exception | None = None
    for attempt in range(12):  # 429 waits are cheap; other errors stop after 3
        try:
            async with _sem:
                if settings.llm_provider == "anthropic":
                    text = await _anthropic(system, user, max_tokens)
                else:
                    text = await _openai_compatible(system, user, max_tokens)
            data = _extract_json(text)
            if not isinstance(data, dict):
                raise LLMError(f"expected a JSON object, got {type(data).__name__}")
            return data
        except RateLimited as e:
            last = e
            log.warning("LLM rate limited, waiting %.1fs", e.wait)
            await asyncio.sleep(e.wait + 0.5)
        except (httpx.HTTPError, LLMError) as e:
            last = e
            log.warning("LLM attempt %s failed: %s", attempt + 1, e)
            if attempt >= 2:
                break
    raise LLMError(str(last))


async def _openai_compatible(system: str, user: str, max_tokens: int) -> str:
    payload = {
        "model": settings.llm_model,
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if "gpt-oss" in settings.llm_model:
        # Reasoning model: keep thinking short so it doesn't eat the max_tokens budget.
        payload["reasoning_effort"] = "low"
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post(
            settings.llm_base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json=payload,
        )
    _raise_for(r)
    return r.json()["choices"][0]["message"]["content"]


async def _anthropic(system: str, user: str, max_tokens: int) -> str:
    payload = {
        "model": settings.llm_model,
        "max_tokens": max_tokens,
        "temperature": 0,
        "system": system + "\n\nОтвечай ТОЛЬКО валидным JSON без пояснений.",
        "messages": [{"role": "user", "content": user}],
    }
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post(
            settings.llm_base_url.rstrip("/") + "/v1/messages",
            headers={
                "x-api-key": settings.llm_api_key,
                "anthropic-version": "2023-06-01",
            },
            json=payload,
        )
    _raise_for(r)
    return "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")
