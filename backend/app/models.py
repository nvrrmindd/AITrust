"""Data model shared by the pipeline, the API and the frontend (see frontend/src/app/models.ts)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

SourceKind = Literal["academic", "web", "book", "law", "other"]
SourceStatus = Literal["exists", "mismatch", "not_found", "unreachable", "unchecked"]
Verdict = Literal[
    "supported",       # a verified verbatim quote backs the claim
    "contradicted",    # a verified quote says otherwise (incl. different numbers)
    "not_in_source",   # source exists and was read, the claim is not there
    "source_missing",  # the cited source does not exist
    "unverifiable",    # could not check honestly (paywall, abstract only, no evidence)
    "pending",
]
Certainty = Literal["hedged", "neutral", "assertive"]


class Citation(BaseModel):
    id: str
    raw: str = ""
    kind: SourceKind = "other"
    url: Optional[str] = None
    doi: Optional[str] = None
    title: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    year: Optional[int] = None
    venue: Optional[str] = None


class MatchedRecord(BaseModel):
    title: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    year: Optional[int] = None
    venue: Optional[str] = None
    url: Optional[str] = None


class SourceCheck(BaseModel):
    citation_id: str
    status: SourceStatus
    method: str  # e.g. "doi.org", "crossref+openalex", "http"
    detail: str  # human explanation, Russian
    matched: Optional[MatchedRecord] = None
    text_scope: Literal["full", "abstract", "none"] = "none"
    differences: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    id: str
    text: str
    span: str = ""  # exact fragment of the original answer
    start: int = -1
    end: int = -1
    citation_ids: list[str] = Field(default_factory=list)
    certainty: Certainty = "neutral"
    certainty_markers: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)  # neutral + adversarial, for uncited claims


class Evidence(BaseModel):
    source_label: str
    url: Optional[str] = None
    citation_id: Optional[str] = None
    quote: str
    quote_verified: bool
    stance: Literal["supports", "contradicts", "neutral"]


class NumberCheck(BaseModel):
    claim_numbers: list[str] = Field(default_factory=list)
    source_numbers: list[str] = Field(default_factory=list)
    mismatch: bool = False


class ClaimResult(BaseModel):
    claim_id: str
    verdict: Verdict
    mode: Literal["cited", "attack"]
    reason: str
    evidence: list[Evidence] = Field(default_factory=list)
    numbers: Optional[NumberCheck] = None
    notes: list[str] = Field(default_factory=list)


class Summary(BaseModel):
    headline: str
    counts: dict[str, int]
    sources_total: int
    sources_missing: int
    sources_mismatch: int
    danger_zone: int  # sounds certain, but not supported
    duration_ms: int


class CheckRequest(BaseModel):
    text: str = Field(min_length=20)
