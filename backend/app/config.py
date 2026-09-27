"""Runtime settings, all from environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    """Tiny .env loader (repo root or backend/), so local runs need no extra package."""
    here = Path(__file__).resolve().parent.parent
    for p in (here / ".env", here.parent / ".env"):
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.split(" #")[0].strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5",
    "groq": "openai/gpt-oss-120b",
    "openrouter": "openai/gpt-4o-mini",
    "gemini": "gemini-3.7-flash",
}
_DEFAULT_BASE = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
}


@dataclass
class Settings:
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "openai").lower())
    llm_api_key: str = field(default_factory=lambda: _env("LLM_API_KEY"))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL"))
    llm_base_url: str = field(default_factory=lambda: _env("LLM_BASE_URL"))
    # a fast model for parsing, the strongest one for verdicts (both default to LLM_MODEL)
    llm_model_extract: str = field(default_factory=lambda: _env("LLM_MODEL_EXTRACT"))
    llm_model_judge: str = field(default_factory=lambda: _env("LLM_MODEL_JUDGE"))
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY"))
    tavily_api_key: str = field(default_factory=lambda: _env("TAVILY_API_KEY"))
    # free key from openalex.org: anonymous search gets paused under load
    openalex_api_key: str = field(default_factory=lambda: _env("OPENALEX_API_KEY"))
    contact_email: str = field(default_factory=lambda: _env("CONTACT_EMAIL", "pruf@example.com"))
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(Path(__file__).resolve().parent.parent / "data"))))
    static_dir: Path = field(default_factory=lambda: Path(_env("STATIC_DIR", str(Path(__file__).resolve().parent.parent / "static"))))
    max_text_chars: int = field(default_factory=lambda: int(_env("MAX_TEXT_CHARS", "12000")))
    max_claims: int = field(default_factory=lambda: int(_env("MAX_CLAIMS", "12")))
    rate_limit_per_hour: int = field(default_factory=lambda: int(_env("RATE_LIMIT_PER_HOUR", "30")))
    llm_concurrency: int = field(default_factory=lambda: int(_env("LLM_CONCURRENCY", "0")))
    http_timeout: float = field(default_factory=lambda: float(_env("HTTP_TIMEOUT", "12")))

    def __post_init__(self) -> None:
        if self.llm_provider == "gemini" and self.gemini_api_key:
            self.llm_api_key = self.gemini_api_key  # LLM_API_KEY may still hold another provider's key
        if not self.llm_model:
            self.llm_model = _DEFAULT_MODELS.get(self.llm_provider, "gpt-4o-mini")
        self.llm_model_extract = self.llm_model_extract or self.llm_model
        self.llm_model_judge = self.llm_model_judge or self.llm_model
        if self.llm_concurrency <= 0:
            self.llm_concurrency = 1 if self.llm_provider == "groq" else 4
        if not self.llm_base_url:
            self.llm_base_url = _DEFAULT_BASE.get(self.llm_provider, _DEFAULT_BASE["openai"])
        (self.data_dir / "cache").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "reports").mkdir(parents=True, exist_ok=True)

    @property
    def user_agent(self) -> str:
        # Crossref/OpenAlex "polite pool" asks for a contact address.
        return f"PrufFactCheck/1.0 (+mailto:{self.contact_email})"


settings = Settings()
