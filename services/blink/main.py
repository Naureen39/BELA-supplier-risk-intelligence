"""blink service: custom-KB retrieval (`/v1/retrieve`) and re-ranking (`/v1/rerank`).

The index is built from the entity catalog file (`data/training/entities.jsonl`). A rebuild runs at
startup, on `POST /v1/index/rebuild`, and automatically when the file changes (the company table
export is refreshed by the ETL job). Internal network only.
"""

from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field

from services.blink.index import CompanyIndex, read_entities
from services.blink.models import BlinkModels, load_models

ENTITY_FILE = Path(os.environ.get("BLINK_ENTITIES", "data/training/entities.jsonl"))
MAX_K = 100
MAX_RERANK = 100

REQUESTS = Counter("blink_requests_total", "Requests", ["endpoint", "status"])
LATENCY = Histogram("blink_request_seconds", "Latency", ["endpoint"])
INDEX_SIZE = Gauge("blink_index_size", "Companies in the index")


class RetrieveRequest(BaseModel):
    mention: str = Field(min_length=1, max_length=300)
    context: str = Field(default="", max_length=2000)
    k: int = Field(default=30, ge=1, le=MAX_K)


class RetrievedOut(BaseModel):
    company_id: int
    title: str
    score: float


class RetrieveResponse(BaseModel):
    biencoder_version: str
    candidates: list[RetrievedOut]


class RerankRequest(BaseModel):
    mention: str = Field(min_length=1, max_length=300)
    context: str = Field(default="", max_length=2000)
    candidate_ids: list[int] = Field(max_length=MAX_RERANK)


class ScoreOut(BaseModel):
    company_id: int
    score: float


class RerankResponse(BaseModel):
    crossencoder_version: str
    scores: list[ScoreOut]


def create_app(models: BlinkModels | None = None, entity_file: Path | None = None) -> FastAPI:
    state: dict[str, Any] = {"index": CompanyIndex(), "build_lock": asyncio.Lock()}
    path = entity_file or ENTITY_FILE

    def build() -> int:
        entities = read_entities(path)
        mdl: BlinkModels = state["models"]
        vectors = mdl.encode_entities([e["text"] for e in entities])
        state["index"].build(entities, vectors)
        state["index"].source_mtime = path.stat().st_mtime
        INDEX_SIZE.set(len(entities))
        return len(entities)

    async def rebuild_if_changed() -> None:
        if path.exists() and path.stat().st_mtime > state["index"].source_mtime:
            async with state["build_lock"]:
                if path.stat().st_mtime > state["index"].source_mtime:
                    await asyncio.to_thread(build)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> Any:
        state["models"] = models or load_models()
        if path.exists():
            await asyncio.to_thread(build)
        yield

    app = FastAPI(title="blink", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok" if state["index"].size else "empty_index",
                "index_size": state["index"].size,
                "biencoder": state["models"].biencoder_version,
                "crossencoder": state["models"].crossencoder_version}

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post("/v1/index/rebuild")
    async def rebuild() -> dict[str, int]:
        async with state["build_lock"]:
            return {"size": await asyncio.to_thread(build)}

    @app.post("/v1/retrieve", response_model=RetrieveResponse)
    async def retrieve(req: RetrieveRequest) -> RetrieveResponse:
        await rebuild_if_changed()
        if not state["index"].size:
            REQUESTS.labels("retrieve", "503").inc()
            raise HTTPException(503, "index not built")
        t0 = time.perf_counter()
        mdl: BlinkModels = state["models"]
        vec = (await asyncio.to_thread(mdl.encode_mentions, [req.mention], [req.context]))[0]
        hits = state["index"].search(vec, req.k)
        REQUESTS.labels("retrieve", "200").inc()
        LATENCY.labels("retrieve").observe(time.perf_counter() - t0)
        return RetrieveResponse(
            biencoder_version=mdl.biencoder_version,
            candidates=[RetrievedOut(company_id=e["company_id"], title=e["title"],
                                     score=max(0.0, min(1.0, s)))
                        for e, s in hits])

    @app.post("/v1/rerank", response_model=RerankResponse)
    async def rerank(req: RerankRequest) -> RerankResponse:
        t0 = time.perf_counter()
        mdl: BlinkModels = state["models"]
        entities = [state["index"].by_company(cid) for cid in req.candidate_ids]
        known = [(cid, e) for cid, e in zip(req.candidate_ids, entities, strict=True) if e]
        if not known:
            return RerankResponse(crossencoder_version=mdl.crossencoder_version, scores=[])
        scores = await asyncio.to_thread(
            mdl.score_pairs, req.mention, req.context, [e["text"] for _cid, e in known])
        REQUESTS.labels("rerank", "200").inc()
        LATENCY.labels("rerank").observe(time.perf_counter() - t0)
        return RerankResponse(
            crossencoder_version=mdl.crossencoder_version,
            scores=[ScoreOut(company_id=cid, score=float(s)) for (cid, _e), s in
                    zip(known, scores, strict=True)])

    return app


app = create_app()
