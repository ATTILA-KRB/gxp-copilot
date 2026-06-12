"""Pipeline RAG : selection de contexte (avec garde-fou), prompt et audit trail.

Garde-fou (plan §6, pilier 2) : le refus controle repose sur le score du
cross-encoder de reranking — en ligne, rapide. La groundedness LLM-as-judge
releve de l'evaluation offline (pilier 4), pas du chemin de requete.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from app.config import Settings, get_settings
from app.providers.base import LLMProvider
from app.retrieval import RetrievedChunk, hybrid_search

REFUSAL = "Information non trouvée dans le corpus."


@dataclass(frozen=True)
class ContextSelection:
    chunks: list[RetrievedChunk]
    score_confiance: float  # meilleur score du reranker (0.0 si aucun candidat)
    refused: bool


def select_context(
    conn: psycopg.Connection,
    question: str,
    provider: LLMProvider,
    settings: Settings | None = None,
) -> ContextSelection:
    """Recherche hybride -> reranking -> seuil de refus -> top-k chunks."""
    settings = settings or get_settings()
    candidates = hybrid_search(
        conn, question, top_k=settings.retrieval_candidates, settings=settings
    )
    if not candidates:
        return ContextSelection(chunks=[], score_confiance=0.0, refused=True)

    ranked = provider.rerank(question, [c.texte for c in candidates])
    if not ranked:
        return ContextSelection(chunks=[], score_confiance=0.0, refused=True)

    best_score = ranked[0][1]
    if best_score < settings.rerank_score_threshold:
        return ContextSelection(chunks=[], score_confiance=best_score, refused=True)

    kept = [
        candidates[index]
        for index, score in ranked[: settings.rerank_top_k]
        if score >= settings.rerank_score_threshold
    ]
    return ContextSelection(chunks=kept, score_confiance=best_score, refused=False)


def build_context(chunks: list[RetrievedChunk]) -> str:
    """Contexte numerote pour la generation ancree : [n] source -> texte."""
    blocks: list[str] = []
    for n, chunk in enumerate(chunks, start=1):
        page = f", p. {chunk.numero_page}" if chunk.numero_page else ""
        section = f", section {chunk.section}" if chunk.section else ""
        blocks.append(f"[{n}] {chunk.titre} ({chunk.agence}{page}{section})\n{chunk.texte}")
    return "\n\n".join(blocks)


def log_interaction(
    conn: psycopg.Connection,
    question: str,
    reponse: str,
    provider_utilise: str,
    modele: str,
    score_confiance: float,
    chunks_cites: list[int],
    latence_ms: int,
) -> int:
    """Journal d'audit (plan §6, pilier 3). Renvoie l'id de l'interaction."""
    row = conn.execute(
        """
        INSERT INTO interaction
            (question, reponse, provider_utilise, modele, score_confiance,
             chunks_cites, latence_ms)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (question, reponse, provider_utilise, modele, score_confiance, chunks_cites, latence_ms),
    ).fetchone()
    conn.commit()
    assert row is not None
    return int(row[0])
