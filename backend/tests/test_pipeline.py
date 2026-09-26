"""End-to-end pipeline with mocked LLM + network: checks events order and the headline."""
import asyncio

import httpx
import respx

from app import llm, netsafe, pipeline

TEXT = """ИИ-поисковики часто ошибаются: по данным Tow Center, они дали неверные ответы на 40% запросов [1].
Кроме того, исследование Smith & Lee (2023) показало, что 74% студентов не проверяют источники [2].
Grok 3 ошибся в 94% запросов [1].

[1] https://news.example/tow-center
[2] Smith, J., Lee, K. (2023). Students and AI citations. Journal of AI Ethics, 12(3), 45–67. https://doi.org/10.9999/jaie.2023.045"""

PAGE = """<html><head><title>AI search has a citation problem</title></head><body><article>
<p>The Tow Center tested eight generative search tools with live search.</p>
<p>Collectively, they provided incorrect answers to more than 60 percent of queries.</p>
<p>Grok 3 answered 94 percent of the queries incorrectly.</p>
<p>Premium chatbots provided more confidently incorrect answers than their free counterparts. """ + "Filler text. " * 60 + "</p></article></body></html>"


async def fake_llm(system, user, max_tokens=0):
    if "СТРУКТУРИРОВАТЬ" in system:
        return {
            "citations": [
                {"id": "S1", "raw": "[1] https://news.example/tow-center", "kind": "web", "url": "https://news.example/tow-center"},
                {"id": "S2", "raw": "[2] Smith, J., Lee, K. (2023)...", "kind": "academic", "doi": "10.9999/jaie.2023.045",
                 "title": "Students and AI citations", "authors": ["Smith J.", "Lee K."], "year": 2023},
            ],
            "claims": [
                {"id": "C1", "span": "по данным Tow Center, они дали неверные ответы на 40% запросов", "text": "ИИ-поисковики дали неверные ответы на 40% запросов (Tow Center)", "citation_ids": ["S1"]},
                {"id": "C2", "span": "74% студентов не проверяют источники", "text": "74% студентов не проверяют источники (Smith & Lee 2023)", "citation_ids": ["S2"]},
                {"id": "C3", "span": "Grok 3 ошибся в 94% запросов", "text": "Grok 3 ошибся в 94% запросов", "citation_ids": ["S1"]},
            ],
        }
    if "40%" in user:
        return {"verdict": "contradicts", "passage": "P1", "quote": "they provided incorrect answers to more than 60 percent of queries", "reason": "В источнике — более 60%, а не 40%."}
    return {"verdict": "supports", "passage": "P1", "quote": "Grok 3 answered 94 percent of the queries incorrectly", "reason": "Совпадает."}


@respx.mock
def test_pipeline_end_to_end(monkeypatch):
    monkeypatch.setattr(llm, "complete_json", fake_llm)

    async def ok(url):
        return None
    monkeypatch.setattr(netsafe, "assert_public", ok)
    respx.get("https://news.example/tow-center").mock(return_value=httpx.Response(200, html=PAGE))
    doi = "10.9999/jaie.2023.045"
    respx.get(f"https://doi.org/api/handles/{doi}").mock(return_value=httpx.Response(404, json={"responseCode": 100}))
    respx.get(f"https://api.crossref.org/works/{doi}").mock(return_value=httpx.Response(404))
    respx.get(f"https://api.openalex.org/works/doi:{doi}").mock(return_value=httpx.Response(404))
    real = {"id": "https://openalex.org/W1", "title": "Undergraduates and chatbot references", "doi": "https://doi.org/10.1000/real.1",
            "publication_year": 2024, "authorships": [], "cited_by_count": 3}
    respx.get("https://api.openalex.org/works").mock(return_value=httpx.Response(200, json={"results": [real]}))

    async def collect():
        return [ev async for ev in pipeline.run(TEXT)]

    events = asyncio.run(collect())
    types = [e["type"] for e in events]
    assert types[0] == "stage" and "extracted" in types and types[-1] == "done"
    verdicts = {e["result"]["claim_id"]: e["result"]["verdict"] for e in events if e["type"] == "claim"}
    assert verdicts == {"C1": "contradicted", "C2": "source_missing", "C3": "supported"}
    reps = [e for e in events if e["type"] == "replacements"]
    assert len(reps) == 1 and reps[0]["citation_id"] == "S2" and reps[0]["claim_id"] == "C2"
    assert reps[0]["works"][0]["doi"] == "10.1000/real.1" and not reps[0]["works"][0]["confirmed"]
    summary = events[-1]["summary"]
    assert "1 из 2 источников не существуют" in summary["headline"]
    assert summary["danger_zone"] == 2
