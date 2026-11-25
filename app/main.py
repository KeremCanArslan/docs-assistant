"""HTTP API and static web page.

    uvicorn app.main:app --reload

Questions and answers are not logged or stored; the access log only contains
method, path, status code and duration.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.answer import answer_question
from app.config import Settings
from app.index import Index
from app.providers import Embedder, Generator, ProviderError, build_providers
from app.ratelimit import RateLimiter

log = logging.getLogger("app")

MAX_BODY_BYTES = 16_384  # a question is at most a few hundred characters


@dataclass
class Services:
    settings: Settings
    index: Index
    embedder: Embedder
    generator: Generator
    limiter: RateLimiter


class AskRequest(BaseModel):
    question: str


class CitationOut(BaseModel):
    number: int
    document: str
    title: str
    location: str
    page: int | None
    url: str
    excerpt: str


class AskResponse(BaseModel):
    answer: str
    found: bool
    citations: list[CitationOut]
    model: str
    retrieval_ms: int
    generation_ms: int


def default_services() -> Services:
    settings = Settings.from_env()
    index = Index.load(settings.index_dir)
    if index.is_stale(settings.documents_dir):
        log.warning("The index does not match the files in %s. Run: python -m app.ingest", settings.documents_dir)
    embedder, generator = build_providers(settings)
    if embedder.name != index.embedder_name:
        raise RuntimeError(
            f"Index was built with {index.embedder_name}, but the configured embedder is {embedder.name}"
        )
    limiter = RateLimiter(settings.requests_per_minute, settings.daily_limit, settings.daily_limit_per_visitor)
    return Services(settings, index, embedder, generator, limiter)


def client_id(request: Request, trust_proxy: bool) -> str:
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def create_app(services_factory=default_services) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.services = services_factory()
        yield

    app = FastAPI(
        title="Document Q&A assistant",
        description="Answers questions from a company's documents and cites the page it used.",
        version="1.0.0",
        lifespan=lifespan,
    )
    origins = list(Settings.from_env().allowed_origins)
    if origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"]
        )

    @app.middleware("http")
    async def limit_body_size(request: Request, call_next):
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > MAX_BODY_BYTES:
            return JSONResponse({"error": "The request is too large."}, status_code=413)
        return await call_next(request)

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        log.info(
            "%s %s %s %dms",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
        )
        return response

    def services(request: Request) -> Services:
        return request.app.state.services

    @app.get("/healthz")
    def healthz(request: Request) -> dict:
        s = services(request)
        return {"ok": True, "documents": len(s.index.documents), "chunks": len(s.index.chunks)}

    @app.get("/api/documents")
    def documents(request: Request) -> list[dict]:
        s = services(request)
        pages: dict[str, int] = {}
        titles: dict[str, str] = {}
        for chunk in s.index.chunks:
            titles.setdefault(chunk.doc_id, chunk.title)
            pages[chunk.doc_id] = max(pages.get(chunk.doc_id, 0), chunk.page or 0)
        return [
            {
                "document": name,
                "title": titles.get(name, name),
                "pages": pages.get(name) or None,
                "url": f"/documents/{name}",
            }
            for name in sorted(s.index.documents)
        ]

    @app.post("/api/ask", response_model=AskResponse)
    def ask(body: AskRequest, request: Request) -> AskResponse:
        s = services(request)
        question = body.question.strip()
        if not question:
            raise HTTPException(422, "The question is empty.")
        if len(question) > s.settings.max_question_chars:
            raise HTTPException(422, f"The question is longer than {s.settings.max_question_chars} characters.")
        limit = s.limiter.check(client_id(request, s.settings.trust_proxy))
        if limit == "minute":
            raise HTTPException(429, "Too many questions in a minute. Please wait a moment.")
        if limit == "client-day":
            raise HTTPException(
                429, "You have reached your daily question limit for this demo. Please try again tomorrow."
            )
        if limit == "day":
            raise HTTPException(429, "The daily question limit of this demo is reached. Please try again tomorrow.")
        try:
            result = answer_question(question, s.index, s.embedder, s.generator, top_k=s.settings.top_k)
        except ProviderError:
            raise HTTPException(503, "The language model is not available right now. Please try again.") from None
        return AskResponse(
            answer=result.text,
            found=result.found,
            citations=[
                CitationOut(
                    number=c.number,
                    document=c.doc_id,
                    title=c.title,
                    location=c.location,
                    page=c.page,
                    url=f"/documents/{c.doc_id}" + (f"#page={c.page}" if c.page else ""),
                    excerpt=c.excerpt,
                )
                for c in result.citations
            ],
            model=result.model,
            retrieval_ms=result.retrieval_ms,
            generation_ms=result.generation_ms,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"error": 'Send JSON like {"question": "..."}.'}, status_code=422)

    settings = Settings.from_env()
    if settings.documents_dir.is_dir():
        app.mount("/documents", StaticFiles(directory=settings.documents_dir), name="documents")
    if settings.web_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
app = create_app()
