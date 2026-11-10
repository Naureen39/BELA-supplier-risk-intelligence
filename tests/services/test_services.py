from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
from app.kb.embeddings import HashedNgramEmbedder
from app.resolution.clients import MentionInput, NelClient
from app.resolution.training_data import entity_rows
from fastapi.testclient import TestClient
from resolution_fixtures import catalog

from services.blink.main import create_app as blink_app
from services.nel.backends import GazetteerBackend
from services.nel.main import create_app as nel_app

TEXT = "A fire at Harborline Foods closed the plant. Northgate Metals Corporation issued a recall."


def nel_client() -> TestClient:
    backend = GazetteerBackend({"Harborline Foods": "Q1001", "Northgate Metals Corporation": "Q1003"})
    return TestClient(nel_app(backend, HashedNgramEmbedder()))


def test_nel_link_contract_and_client_roundtrip() -> None:
    with nel_client() as tc:
        health = tc.get("/health").json()
        assert health["status"] == "ok"
        body = tc.post("/v1/link", json={"items": [{"id": "a", "text": TEXT, "lang": "en"}]}).json()
        spans = {(m["surface"], m["qid"]) for m in body["results"][0]["mentions"]}
        assert spans == {("Harborline Foods", "Q1001"), ("Northgate Metals Corporation", "Q1003")}
        client = NelClient("http://testserver", client=httpx.Client(base_url="http://testserver",
                                                                    transport=_asgi(tc)))
        mentions = client.link([MentionInput("a", TEXT)])[0]
        assert mentions[0].surface == "Harborline Foods" and mentions[0].start == TEXT.find("Harborline")
        assert "nel_requests_total" in tc.get("/metrics").text


def _asgi(tc: TestClient) -> httpx.BaseTransport:
    class T(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            r = tc.request(request.method, request.url.path, content=request.content,
                           headers=dict(request.headers))
            return httpx.Response(r.status_code, content=r.content, headers=r.headers)
    return T()


def test_nel_rejects_oversized_batch_and_embeds() -> None:
    with nel_client() as tc:
        too_many = {"items": [{"id": str(i), "text": "x"} for i in range(65)]}
        assert tc.post("/v1/link", json=too_many).status_code == 422
        emb = tc.post("/v1/embed", json={"texts": ["Acme"]}).json()
        assert emb["dimensions"] == 1024 and len(emb["vectors"]) == 1


def test_blink_retrieve_rerank_and_rebuild(tmp_path: Path) -> None:
    path = tmp_path / "entities.jsonl"
    cat = catalog()
    path.write_text("\n".join(json.dumps(r) for r in entity_rows(cat)) + "\n")
    with TestClient(blink_app(entity_file=path)) as tc:
        assert tc.get("/health").json()["index_size"] == len(cat)
        r = tc.post("/v1/retrieve", json={"mention": "Northgate Metals Corp", "context": "Pittsburgh PA", "k": 3}).json()
        assert r["candidates"][0]["company_id"] in {3, 4}
        ids = [c["company_id"] for c in r["candidates"]]
        s = tc.post("/v1/rerank", json={"mention": "Northgate Metals Corp", "context": "", "candidate_ids": ids + [9999]}).json()
        assert {x["company_id"] for x in s["scores"]} == set(ids)

        # The index follows the entity file when it changes.
        time.sleep(0.01)
        extra = {"idx": 99, "company_id": 99, "title": "Zephyr Wind Turbines", "text": "Zephyr Wind Turbines. public company"}
        path.write_text(path.read_text() + json.dumps(extra) + "\n")
        r2 = tc.post("/v1/retrieve", json={"mention": "Zephyr Wind Turbines", "k": 1}).json()
        assert r2["candidates"][0]["company_id"] == 99


def test_blink_validation() -> None:
    with TestClient(blink_app(entity_file=Path("/nonexistent.jsonl"))) as tc:
        assert tc.post("/v1/retrieve", json={"mention": "x", "k": 5}).status_code == 503
        assert tc.post("/v1/retrieve", json={"mention": "", "k": 5}).status_code == 422
        assert tc.post("/v1/retrieve", json={"mention": "x", "k": 1000}).status_code == 422
