"""Tests de l'API FastAPI : /health et le flux SSE de /ask (pipeline stubbe)."""

from __future__ import annotations

import contextlib
import json

import pytest
from fastapi.testclient import TestClient

import app.main as main
import app.rag as rag
from app.main import app
from app.retrieval import RetrievedChunk


def _chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=7,
        document_id=1,
        texte="Audit trails must record changes.",
        numero_page=4,
        section="12.4",
        titre="Annex 11",
        agence="EU",
        url_source="https://example.org/a11",
        score_rrf=0.05,
    )


class _StubProvider:
    def rerank(self, query, candidates):  # pragma: no cover - non appele (select stubbe)
        return []

    def generate(self, prompt, context):
        yield "Les audit trails "
        yield "sont obligatoires."


def _parse_sse(body: str) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], lines["data"]))
    return events


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    @contextlib.contextmanager
    def fake_connect(_url):
        yield None

    monkeypatch.setattr(main.psycopg, "connect", fake_connect)
    monkeypatch.setattr(main, "get_provider", lambda settings: _StubProvider())
    monkeypatch.setattr(
        rag, "log_interaction", lambda conn, **kwargs: 42
    )
    return TestClient(app)


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ask_streams_sources_tokens_done(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    selection = rag.ContextSelection(chunks=[_chunk()], score_confiance=0.92, refused=False)
    monkeypatch.setattr(rag, "select_context", lambda conn, q, p, s: selection)

    response = client.post("/ask", json={"question": "Que disent les audit trails ?"})
    assert response.status_code == 200
    events = _parse_sse(response.text)

    assert events[0][0] == "sources"
    sources = json.loads(events[0][1])
    assert sources[0]["chunk_id"] == 7
    assert sources[0]["numero_page"] == 4

    tokens = [json.loads(data) for event, data in events if event == "token"]
    assert "".join(tokens) == "Les audit trails sont obligatoires."

    assert events[-1][0] == "done"
    done = json.loads(events[-1][1])
    assert done["interaction_id"] == 42
    assert done["score_confiance"] == 0.92
    assert done["latence_ms"] >= 0


def test_ask_refusal_streams_refusal_message(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    selection = rag.ContextSelection(chunks=[], score_confiance=0.05, refused=True)
    monkeypatch.setattr(rag, "select_context", lambda conn, q, p, s: selection)

    response = client.post("/ask", json={"question": "Question hors corpus ?"})
    events = _parse_sse(response.text)

    assert json.loads(events[0][1]) == []  # aucune source
    tokens = [json.loads(data) for event, data in events if event == "token"]
    assert "".join(tokens) == rag.REFUSAL


def test_ask_validates_question_length(client: TestClient):
    response = client.post("/ask", json={"question": "ab"})
    assert response.status_code == 422
