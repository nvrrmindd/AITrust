"""Real works suggested instead of a non-existent source: OpenAlex mocked, the judge's LLM mocked."""
import asyncio

import httpx
import respx

from app import llm
from app.models import Citation, Claim
from app.replacements import find_replacements, queries

OA = "https://api.openalex.org/works"


def _inv(text: str) -> dict:
    inv: dict[str, list[int]] = {}
    for i, w in enumerate(text.split()):
        inv.setdefault(w, []).append(i)
    return inv


ABSTRACT_OK = ("We surveyed 1200 undergraduates about generative AI. Most students do not verify the sources that "
               "chatbots cite, and 74% of students never check AI citations before using them in coursework.")
ABSTRACT_TOPIC = ("This paper reviews the literature on academic integrity and large language models in higher education, "
                  "discussing policy responses of universities and implications for assessment design.")


def _work(n: int, title: str, abstract: str | None) -> dict:
    return {
        "id": f"https://openalex.org/W{n}", "title": title, "doi": f"https://doi.org/10.1000/real.{n}",
        "publication_year": 2020 + n, "cited_by_count": 10 * n,
        "authorships": [{"author": {"display_name": "Anna Petrova"}}, {"author": {"display_name": "John Smith"}}],
        "primary_location": {"source": {"display_name": "Computers & Education"}},
        "biblio": {"volume": "12", "issue": "3", "first_page": "45", "last_page": "67"},
        "abstract_inverted_index": _inv(abstract) if abstract else None,
    }


WORKS = [
    _work(1, "Do students check what chatbots cite?", ABSTRACT_OK),
    _work(2, "Academic integrity in the age of LLMs", ABSTRACT_TOPIC),
    _work(3, "Citation practices of undergraduates", None),
    _work(4, "Fourth result is not shown", ABSTRACT_OK),
]

CIT = Citation(id="S2", kind="academic", title="Students and AI citations", authors=["Smith J."], year=2023)
CLAIM = Claim(id="C2", text="74% студентов не проверяют источники, которые приводит ИИ", citation_ids=["S2"])


async def fake_judge(system, user, max_tokens=0, role="judge"):
    if "Do students check" in user:
        return {"verdict": "supports", "quote": "74% of students never check AI citations before using them", "reason": "ok"}
    # a "quote" that is not in the abstract must not produce a confirmation
    return {"verdict": "supports", "quote": "74% of students never verify anything at all", "reason": "похоже"}


@respx.mock
def test_replacements_from_openalex(monkeypatch):
    monkeypatch.setattr(llm, "complete_json", fake_judge)
    route = respx.get(OA).mock(side_effect=[httpx.Response(200, json={"results": []}),  # title query: nothing
                                            httpx.Response(200, json={"results": WORKS})])
    reps = asyncio.run(find_replacements(CIT, CLAIM))

    assert route.call_count == 2
    first = route.calls[0].request.url.params
    assert first["filter"] == "has_doi:true,type:article" and first["sort"] == "relevance_score:desc"
    assert first["per-page"] == "5" and first["mailto"]
    assert route.calls[1].request.url.params["search"] == queries(CIT, CLAIM)[1]

    assert [r.title for r in reps] == ["Do students check what chatbots cite?", "Academic integrity in the age of LLMs",
                                       "Citation practices of undergraduates"]
    a, b, c = reps
    assert a.doi == "10.1000/real.1" and a.url == "https://doi.org/10.1000/real.1"
    assert a.authors == ["Anna Petrova", "John Smith"] and a.year == 2021 and a.venue == "Computers & Education"
    assert a.cited_by_count == 10 and a.pages == "45–67"
    assert a.abstract == ABSTRACT_OK  # rebuilt from abstract_inverted_index
    assert a.confirmed and "74% of students" in (a.quote or "")
    assert not b.confirmed and b.quote is None  # unverified quote -> only "similar topic"
    assert not c.confirmed and c.abstract == ""  # no abstract -> not judged


@respx.mock
def test_replacements_openalex_down_is_empty(monkeypatch):
    monkeypatch.setattr(llm, "complete_json", fake_judge)
    respx.get(OA).mock(return_value=httpx.Response(503))
    assert asyncio.run(find_replacements(CIT, CLAIM)) == []


def test_queries_fall_back_from_combined_to_parts():
    same = Claim(id="C1", text="Most students never verify AI citations", citation_ids=["S2"])
    qs = queries(CIT, same)
    assert len(qs) == 3 and qs[0].startswith(qs[1]) and qs[0].endswith(qs[2]) and "AI" in qs[1]
    # ru claim + en title: no mixed query, the title goes first
    assert queries(CIT, CLAIM) == [qs[1], queries(Citation(id="x"), CLAIM)[0]]
    assert queries(CIT, None) == [qs[1]]
