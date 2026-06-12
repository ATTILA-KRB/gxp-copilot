"""API FastAPI — Phase 1 : POST /ask (SSE) et GET /health.

Flux SSE de /ask :
  event: sources  -> JSON des citations retenues (avant generation)
  event: token    -> fragment de reponse (JSON string, streaming)
  event: done     -> JSON {interaction_id, score_confiance, latence_ms}
Chaque interaction est journalisee (audit trail, plan §6 pilier 3).
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator

import psycopg
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import rag
from app.config import get_settings
from app.providers import get_provider

DISCLAIMER = (
    "Démonstration technique. Corpus 100 % public (MHRA, FDA, PIC/S, WHO, EU GMP). "
    "Cet outil ne fournit aucun conseil réglementaire et ne se substitue ni aux "
    "textes officiels ni à un avis qualifié."
)

app = FastAPI(title="GxP Copilot", description=DISCLAIMER, version="0.1.0")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


def _sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


def _citations_payload(selection: rag.ContextSelection) -> str:
    return json.dumps(
        [
            {
                "chunk_id": c.chunk_id,
                "titre": c.titre,
                "agence": c.agence,
                "numero_page": c.numero_page,
                "section": c.section,
                "url_source": c.url_source,
            }
            for c in selection.chunks
        ],
        ensure_ascii=False,
    )


def _answer_stream(question: str) -> Iterator[str]:
    settings = get_settings()
    provider = get_provider(settings)
    start = time.perf_counter()

    with psycopg.connect(settings.database_url) as conn:
        selection = rag.select_context(conn, question, provider, settings)
        yield _sse("sources", _citations_payload(selection))

        if selection.refused:
            reponse = rag.REFUSAL
            yield _sse("token", json.dumps(reponse, ensure_ascii=False))
        else:
            parts: list[str] = []
            context = rag.build_context(selection.chunks)
            for token in provider.generate(question, context):
                parts.append(token)
                yield _sse("token", json.dumps(token, ensure_ascii=False))
            reponse = "".join(parts)

        latence_ms = int((time.perf_counter() - start) * 1000)
        interaction_id = rag.log_interaction(
            conn,
            question=question,
            reponse=reponse,
            provider_utilise=settings.provider,
            modele=settings.generation_model_name,
            score_confiance=selection.score_confiance,
            chunks_cites=[c.chunk_id for c in selection.chunks],
            latence_ms=latence_ms,
        )
        yield _sse(
            "done",
            json.dumps(
                {
                    "interaction_id": interaction_id,
                    "score_confiance": selection.score_confiance,
                    "latence_ms": latence_ms,
                }
            ),
        )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask")
def ask(payload: AskRequest) -> StreamingResponse:
    return StreamingResponse(
        _answer_stream(payload.question), media_type="text/event-stream"
    )
