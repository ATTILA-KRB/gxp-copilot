"""Reranking cloud via l'API REST Cohere (pas de SDK supplementaire : httpx suffit).

Les scores du cross-encoder sont exploitables pour le garde-fou de refus
(plan §6, pilier 2) : contrairement aux similarites cosinus brutes, ils sont
calibres dans [0, 1] et un seuil y a un sens.
"""

from __future__ import annotations

import httpx

from app.config import Settings

_COHERE_RERANK_URL = "https://api.cohere.com/v2/rerank"
_TIMEOUT = httpx.Timeout(30.0)


def cohere_rerank(
    query: str,
    documents: list[str],
    settings: Settings,
    client: httpx.Client | None = None,
) -> list[tuple[int, float]]:
    """Reordonne les documents : [(index d'origine, score)] tries par score decroissant."""
    if not documents:
        return []
    if not settings.cohere_api_key:
        raise RuntimeError(
            "COHERE_API_KEY est vide. Renseigner la cle dans .env pour le reranking cloud."
        )

    own_client = client is None
    client = client or httpx.Client(timeout=_TIMEOUT)
    try:
        response = client.post(
            _COHERE_RERANK_URL,
            headers={"Authorization": f"Bearer {settings.cohere_api_key}"},
            json={
                "model": settings.cohere_rerank_model,
                "query": query,
                "documents": documents,
            },
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        ranked = [(int(r["index"]), float(r["relevance_score"])) for r in results]
        # L'API renvoie deja trie ; on garantit l'invariant localement.
        ranked.sort(key=lambda pair: -pair[1])
        return ranked
    finally:
        if own_client:
            client.close()
