"""Settings read from environment variables. Nothing secret is stored in the code."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


def _list(name: str, default: str) -> tuple[str, ...]:
    raw = os.environ.get(name, default)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    documents_dir: Path = ROOT / "documents"
    index_dir: Path = ROOT / "data" / "index"
    web_dir: Path = ROOT / "web"

    # Providers: "gemini", or "openai" for any OpenAI-compatible endpoint (OpenAI, Groq, Azure OpenAI, Ollama, vLLM).
    embedding_provider: str = "gemini"
    # Answer providers in order of preference; the next one is used when one fails or hits its quota.
    generators: tuple[str, ...] = ("gemini",)
    gemini_api_key: str = ""
    gemini_models: tuple[str, ...] = ("gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.7-flash")
    gemini_embedding_model: str = "gemini-embedding-001"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = ""
    openai_reasoning_effort: str = ""
    openai_embedding_model: str = ""
    embedding_dim: int = 768

    top_k: int = 5
    max_question_chars: int = 500
    requests_per_minute: int = 6
    daily_limit: int = 300
    daily_limit_per_visitor: int = 20
    client_ip_header: str = ""  # header with the visitor's address, set by the proxy in front of the app
    allowed_origins: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_env(cls) -> Settings:
        base = cls()
        return cls(
            documents_dir=Path(os.environ.get("DOCUMENTS_DIR", base.documents_dir)),
            index_dir=Path(os.environ.get("INDEX_DIR", base.index_dir)),
            web_dir=Path(os.environ.get("WEB_DIR", base.web_dir)),
            embedding_provider=os.environ.get("EMBEDDING_PROVIDER", base.embedding_provider).strip().lower(),
            generators=tuple(g.lower() for g in _list("GENERATORS", ",".join(base.generators))),
            gemini_api_key=os.environ.get("GEMINI_API_KEY", "").strip(),
            gemini_models=_list("GEMINI_MODELS", ",".join(base.gemini_models)),
            gemini_embedding_model=os.environ.get("GEMINI_EMBEDDING_MODEL", base.gemini_embedding_model),
            openai_base_url=os.environ.get("OPENAI_BASE_URL", base.openai_base_url).rstrip("/"),
            openai_api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
            openai_model=os.environ.get("OPENAI_MODEL", base.openai_model),
            openai_reasoning_effort=os.environ.get("OPENAI_REASONING_EFFORT", "").strip().lower(),
            openai_embedding_model=os.environ.get("OPENAI_EMBEDDING_MODEL", base.openai_embedding_model),
            embedding_dim=_int("EMBEDDING_DIM", base.embedding_dim),
            top_k=_int("TOP_K", base.top_k),
            max_question_chars=_int("MAX_QUESTION_CHARS", base.max_question_chars),
            requests_per_minute=_int("REQUESTS_PER_MINUTE", base.requests_per_minute),
            daily_limit=_int("DAILY_LIMIT", base.daily_limit),
            daily_limit_per_visitor=_int("DAILY_LIMIT_PER_VISITOR", base.daily_limit_per_visitor),
            client_ip_header=os.environ.get("CLIENT_IP_HEADER", "").strip().lower(),
            allowed_origins=_list("ALLOWED_ORIGINS", ""),
        )
