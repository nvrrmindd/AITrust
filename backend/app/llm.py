"""Minimal LLM client: OpenAI-compatible (OpenAI, Groq, OpenRouter) or Anthropic, JSON output only."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from .config import settings

log = logging.getLogger("pruf.llm")


class LLMError(Exception):
    pass


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
    for attempt in range(3):
        try:
            if settings.llm_provider == "anthropic":
                text = await _anthropic(system, user, max_tokens)
            else:
                text = await _openai_compatible(system, user, max_tokens)
            return _extract_json(text)
        except (httpx.HTTPError, LLMError) as e:
            last = e
            log.warning("LLM attempt %s failed: %s", attempt + 1, e)
    raise LLMError(str(last))


async def _openai_compatible(system: str, user: str, max_tokens: int) -> str:
    payload = {
        "model": settings.llm_model,
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post(
            settings.llm_base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json=payload,
        )
    if r.status_code >= 400:
        raise LLMError(f"LLM HTTP {r.status_code}: {r.text[:300]}")
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
    if r.status_code >= 400:
        raise LLMError(f"LLM HTTP {r.status_code}: {r.text[:300]}")
    return "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")
