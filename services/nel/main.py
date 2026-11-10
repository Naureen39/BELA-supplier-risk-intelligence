"""nel service: BELA inference (`/v1/link`) and bge-m3 embeddings (`/v1/embed`).

Internal network only. Batching limit, bounded concurrency with 503 backpressure, health and
Prometheus metrics. Model weights are loaded once at startup by the backend factory.
"""

from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

from services.nel.backends import LinkBackend, load_backend

MAX_ITEMS = int(os.environ.get("NEL_MAX_ITEMS", "64"))
MAX_CHARS = int(os.environ.get("NEL_MAX_CHARS", "6000"))
MAX_INFLIGHT = int(os.environ.get("NEL_MAX_INFLIGHT", "2"))

REQUESTS = Counter("nel_requests_total", "Requests", ["endpoint", "status"])
ITEMS = Counter("nel_items_total", "Passages or texts processed", ["endpoint"])
LATENCY = Histogram("nel_request_seconds", "Request latency", ["endpoint"])


class LinkItem(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    text: str = Field(max_length=MAX_CHARS)
    lang: str = Field(default="en", max_length=8)


class LinkRequest(BaseModel):
    items: list[LinkItem] = Field(max_length=MAX_ITEMS)


class Candidate(BaseModel):
    qid: str
    score: float


class MentionOut(BaseModel):
    start: int
    end: int
    surface: str
    qid: str | None
    md_score: float
    el_score: float
    candidates: list[Candidate] = Field(default_factory=list, max_length=10)


class LinkResult(BaseModel):
    id: str
    mentions: list[MentionOut]


class LinkResponse(BaseModel):
    model_version: str
    results: list[LinkResult]


class EmbedRequest(BaseModel):
    texts: list[str] = Field(max_length=256)


class EmbedResponse(BaseModel):
    model: str
    dimensions: int
    vectors: list[list[float]]


def create_app(backend: LinkBackend | None = None, embedder: Any | None = None) -> FastAPI:
    state: dict[str, Any] = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> Any:
        state["backend"] = backend or load_backend()
        if embedder is not None:
            state["embedder"] = embedder
        elif os.environ.get("NEL_EMBEDDER", "") == "bge-m3":
            from app.kb.embeddings import BgeM3Embedder

            state["embedder"] = BgeM3Embedder()
        state["slots"] = asyncio.Semaphore(MAX_INFLIGHT)
        state["waiting"] = 0
        yield

    app = FastAPI(title="nel", lifespan=lifespan)

    async def gated(fn: Any, *args: Any) -> Any:
        slots: asyncio.Semaphore = state["slots"]
        if state["waiting"] >= MAX_INFLIGHT * 4:
            raise HTTPException(503, "busy", headers={"Retry-After": "2"})
        state["waiting"] += 1
        try:
            async with slots:
                return await asyncio.to_thread(fn, *args)
        finally:
            state["waiting"] -= 1

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "backend": state["backend"].model_version,
                "embedder": getattr(state.get("embedder"), "model_name", None)}

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post("/v1/link", response_model=LinkResponse)
    async def link(req: LinkRequest) -> LinkResponse:
        t0 = time.perf_counter()
        be: LinkBackend = state["backend"]
        try:
            raw = await gated(be.link, [i.text for i in req.items], [i.lang for i in req.items])
        except HTTPException:
            REQUESTS.labels("link", "503").inc()
            raise
        results = []
        for item, mentions in zip(req.items, raw, strict=True):
            results.append(LinkResult(id=item.id, mentions=[
                MentionOut(**{**m, "candidates": m.get("candidates", [])[:10]}) for m in mentions]))
        ITEMS.labels("link").inc(len(req.items))
        REQUESTS.labels("link", "200").inc()
        LATENCY.labels("link").observe(time.perf_counter() - t0)
        return LinkResponse(model_version=be.model_version, results=results)

    @app.post("/v1/embed", response_model=EmbedResponse)
    async def embed(req: EmbedRequest) -> EmbedResponse:
        emb = state.get("embedder")
        if emb is None:
            raise HTTPException(501, "no embedder configured (set NEL_EMBEDDER=bge-m3)")
        t0 = time.perf_counter()
        vectors = await gated(emb.encode, req.texts)
        ITEMS.labels("embed").inc(len(req.texts))
        REQUESTS.labels("embed", "200").inc()
        LATENCY.labels("embed").observe(time.perf_counter() - t0)
        return EmbedResponse(model=emb.model_name, dimensions=len(vectors[0]) if vectors else 0,
                             vectors=vectors)

    return app


app = create_app()
