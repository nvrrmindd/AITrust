"""Deterministic text helpers: normalization, chunking, lexical retrieval, numbers, hedging.

Everything here is pure Python and unit-tested: these are the parts of the verdict that do
NOT depend on an LLM.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

import snowballstemmer
from rapidfuzz import fuzz

_STEM_RU = snowballstemmer.stemmer("russian")
_STEM_EN = snowballstemmer.stemmer("english")

_WORD = re.compile(r"[\w\-]+", re.UNICODE)
_CYR = re.compile(r"[а-яёәғқңөұүһі]", re.IGNORECASE)

_STOP = set(
    """и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне было
    вот от меня еще нет о из ему теперь когда даже ну вдруг ли если уже или ни быть был него до вас нибудь
    опять уж вам ведь там потом себя ничего ей может они тут где есть надо ней для мы тебя их чем была сам
    чтоб без будто чего раз тоже себе под будет ж тогда кто этот того потому этого какой совсем ним здесь
    этом один почти мой тем чтобы нее сейчас были куда зачем всех никогда можно при наконец два об другой
    хоть после над больше тот через эти нас про всего них какая много разве три эту моя впрочем хорошо
    свою этой перед иногда лучше чуть том нельзя такой им более всегда конечно всю между это также
    the a an and or of to in on for with by is are was were be been as at from that this it its which
    who whom than then there their they them these those has have had not but also into about over such
    can could may might will would should""".split()
)


def normalize(text: str) -> str:
    """Lowercase, unify quotes/dashes/whitespace, NFKC. Used before any fuzzy comparison."""
    t = unicodedata.normalize("NFKC", text or "").lower()
    t = t.replace("ё", "е")
    t = re.sub(r"[«»“”„\"']", "", t)
    t = re.sub(r"[‐‑‒–—−]", "-", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def stem(word: str) -> str:
    w = word.lower().replace("ё", "е")
    return _STEM_RU.stemWord(w) if _CYR.search(w) else _STEM_EN.stemWord(w)


def tokens(text: str) -> list[str]:
    return [stem(w) for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1]


_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[A-ZА-ЯЁ0-9«\"(\[])")


def sentences(text: str) -> list[str]:
    parts: list[str] = []
    for block in re.split(r"\n\s*\n|\n(?=[-•*\d])", text):
        block = block.strip()
        if block:
            parts.extend(s.strip() for s in _SENT_SPLIT.split(block) if s.strip())
    return parts


def chunk(text: str, window: int = 3, max_chars: int = 900) -> list[str]:
    """Overlapping windows of sentences; overlap keeps numbers next to their context."""
    sents = sentences(text)
    if not sents:
        return []
    chunks: list[str] = []
    step = max(1, window - 1)
    for i in range(0, len(sents), step):
        piece = " ".join(sents[i : i + window])
        chunks.append(piece[:max_chars])
        if i + window >= len(sents):
            break
    return chunks


# ---------------------------------------------------------------- numbers

_NUM = re.compile(
    r"(?<![\w.])(\d{1,3}(?:[   ]\d{3})+|\d+(?:[.,]\d+)?)\s*(%|процент\w*|percent|млн|млрд|тыс\w*|million|billion|thousand)?",
    re.IGNORECASE,
)


def numbers(text: str) -> list[str]:
    """Extract comparable numbers. '60 %' -> '60%', '1,5 млн' -> '1.5млн', '4 841' -> '4841'."""
    out: list[str] = []
    for m in _NUM.finditer(text or ""):
        raw, unit = m.group(1), (m.group(2) or "").lower()
        val = re.sub(r"[   ]", "", raw).replace(",", ".")
        try:
            f = float(val)
        except ValueError:
            continue
        val = str(int(f)) if f.is_integer() else str(f)
        if unit.startswith(("процент", "percent")) or unit == "%":
            unit = "%"
        elif unit.startswith(("тыс", "thousand")):
            unit = "тыс"
        elif unit in ("million",):
            unit = "млн"
        elif unit in ("billion",):
            unit = "млрд"
        out.append(val + unit)
    return out


def _bare(n: str) -> str:
    return re.sub(r"[^\d.]", "", n)


def number_mismatch(claim: str, source_text: str) -> tuple[list[str], list[str], bool]:
    """True if the claim contains a salient number (percent / big number) that the source text
    never mentions while the source does mention other numbers of the same kind."""
    cn = numbers(claim)
    sn = numbers(source_text)
    salient = [n for n in cn if n.endswith("%") or n.endswith(("млн", "млрд", "тыс")) or (len(_bare(n)) >= 3 and not _is_year(n))]
    if not salient:
        return cn, sn, False
    s_bare = {_bare(n) for n in sn}
    missing = [n for n in salient if _bare(n) not in s_bare]
    if not missing:
        return cn, sn, False
    kinds = {("%" if n.endswith("%") else "n") for n in missing}
    has_same_kind = any(("%" if n.endswith("%") else "n") in kinds for n in sn if not _is_year(n))
    return cn, sn, bool(has_same_kind)


def _is_year(n: str) -> bool:
    return n.isdigit() and 1800 <= int(n) <= 2100


# ---------------------------------------------------------------- retrieval

def rank_passages(query: str, passages: list[str], k: int = 5) -> list[tuple[int, float]]:
    """BM25 over stemmed tokens + a bonus for shared numbers. Returns [(index, score)]."""
    q = tokens(query)
    if not passages or not q:
        return [(i, 0.0) for i in range(min(k, len(passages)))]
    docs = [tokens(p) for p in passages]
    n = len(docs)
    avg = sum(len(d) for d in docs) / max(n, 1) or 1.0
    df: Counter[str] = Counter()
    for d in docs:
        df.update(set(d))
    qn = {_bare(x) for x in numbers(query)}
    scores = []
    for i, d in enumerate(docs):
        tf = Counter(d)
        s = 0.0
        for term in set(q):
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            f = tf[term]
            s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * len(d) / avg))
        if qn:
            pn = {_bare(x) for x in numbers(passages[i])}
            s += 1.5 * len(qn & pn)
        scores.append((i, s))
    scores.sort(key=lambda x: -x[1])
    return scores[:k]


# ---------------------------------------------------------------- quote validation

def quote_in_text(quote: str, text: str, threshold: int = 90) -> bool:
    """The anti-hallucination guard for our own judge: a quote only counts if it is (almost)
    verbatim in the source. Tolerates whitespace/quote-style differences and tiny OCR noise."""
    q, t = normalize(quote), normalize(text)
    if len(q) < 12:
        return False
    # fuzzy matching must never let a changed number through ("40 percent" vs "60 percent")
    if not {_bare(n) for n in numbers(quote)} <= {_bare(n) for n in numbers(text)}:
        return False
    if q in t:
        return True
    return fuzz.partial_ratio(q, t) >= threshold


def locate(fragment: str, text: str) -> tuple[int, int]:
    """Find a fragment of the original answer (exact, then fuzzy). Returns (start, end) or (-1, -1)."""
    if not fragment:
        return -1, -1
    i = text.find(fragment)
    if i >= 0:
        return i, i + len(fragment)
    al = fuzz.partial_ratio_alignment(fragment, text)
    if al and al.score >= 85:
        return al.dest_start, al.dest_end
    return -1, -1


# ---------------------------------------------------------------- certainty of tone

HEDGES = [
    "возможно", "вероятно", "по-видимому", "предположительно", "может быть", "могут", "может",
    "по некоторым данным", "по оценкам", "около", "примерно", "порядка", "считается", "как правило",
    "скорее всего", "не исключено", "по-моему",
    "may", "might", "could", "possibly", "probably", "likely", "approximately", "roughly",
    "estimated", "suggests", "some studies", "it is believed", "reportedly",
]
ASSERTIVE = [
    "доказано", "точно", "всегда", "никогда", "однозначно", "безусловно", "бесспорно", "исследования показывают",
    "установлено", "известно, что", "факт", "ровно",
    "proven", "definitely", "always", "never", "clearly", "certainly", "studies show", "it is a fact",
    "undoubtedly", "exactly",
]


def certainty(sentence: str) -> tuple[str, list[str]]:
    s = " " + normalize(sentence) + " "
    hedges = [h for h in HEDGES if re.search(rf"(?<![\w]){re.escape(h)}(?![\w])", s)]
    if hedges:
        return "hedged", hedges
    strong = [a for a in ASSERTIVE if re.search(rf"(?<![\w]){re.escape(a)}(?![\w])", s)]
    precise = [n for n in numbers(sentence) if not _is_year(n)]
    if strong or precise:
        return "assertive", strong + [f"точное число {n}" for n in precise[:2]]
    return "neutral", []


# ---------------------------------------------------------------- deterministic citation spotting

URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.IGNORECASE)


def clean_doi(doi: str) -> str:
    d = doi.strip().rstrip(".,;)]}")
    d = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", d, flags=re.IGNORECASE)
    return d


def find_urls(text: str) -> list[str]:
    return [u.rstrip(".,;)]}") for u in URL_RE.findall(text)]


def find_dois(text: str) -> list[str]:
    return [clean_doi(d) for d in DOI_RE.findall(text)]
