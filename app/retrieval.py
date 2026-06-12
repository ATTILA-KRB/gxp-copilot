"""Recherche hybride : dense (pgvector) + plein-texte BM25 (tsvector), fusion RRF.

Pipeline plan §3 : les deux moteurs renvoient chacun leurs candidats ordonnes,
la fusion Reciprocal Rank Fusion (RRF) combine les rangs — robuste car elle ne
compare jamais les scores bruts (cosinus et ts_rank ne sont pas commensurables).
Le reranking cross-encoder (Phase 1, etape suivante) s'applique apres.

La question peut etre en francais sur un corpus anglophone : c'est l'embedding
multilingue bge-m3 qui porte la recuperation cross-lingue ; le BM25 anglais
n'apporte alors rien, ce que la fusion par rangs tolere par construction.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from app.config import Settings, get_settings
from app.embedding import embed_texts

# Constante standard de la litterature RRF (Cormack et al.).
_RRF_K = 60
# Candidats par moteur avant fusion ; le reranker reduira ensuite.
_CANDIDATES_PER_ENGINE = 50
_DEFAULT_TOP_K = 8


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int
    document_id: int
    texte: str
    numero_page: int | None
    section: str | None
    titre: str
    agence: str
    url_source: str
    score_rrf: float


def rrf_fuse(rankings: list[list[int]], k: int = _RRF_K) -> list[tuple[int, float]]:
    """Fusionne des listes ordonnees d'ids : score(d) = somme 1 / (k + rang).

    Renvoie les (id, score) tries par score decroissant ; egalite departagee
    par id croissant pour rester deterministe.
    """
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def dense_search(
    conn: psycopg.Connection,
    query_embedding: list[float],
    limit: int = _CANDIDATES_PER_ENGINE,
) -> list[int]:
    """Top-N par similarite cosinus (pgvector). Renvoie les ids ordonnes."""
    rows = conn.execute(
        """
        SELECT id
        FROM chunk
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (str(query_embedding), limit),
    ).fetchall()
    return [int(row[0]) for row in rows]


def sparse_search(
    conn: psycopg.Connection,
    query: str,
    limit: int = _CANDIDATES_PER_ENGINE,
) -> list[int]:
    """Top-N plein-texte (tsvector/BM25). Renvoie les ids ordonnes."""
    rows = conn.execute(
        """
        SELECT id
        FROM chunk
        WHERE tsv @@ websearch_to_tsquery('english', %s)
        ORDER BY ts_rank_cd(tsv, websearch_to_tsquery('english', %s)) DESC
        LIMIT %s
        """,
        (query, query, limit),
    ).fetchall()
    return [int(row[0]) for row in rows]


def _fetch_chunks(
    conn: psycopg.Connection, ids_scores: list[tuple[int, float]]
) -> list[RetrievedChunk]:
    """Hydrate les chunks retenus (avec leur document), dans l'ordre de fusion."""
    if not ids_scores:
        return []
    ids = [chunk_id for chunk_id, _ in ids_scores]
    rows = conn.execute(
        """
        SELECT c.id, c.document_id, c.texte, c.numero_page, c.section,
               d.titre, d.agence, d.url_source
        FROM chunk c
        JOIN document d ON d.id = c.document_id
        WHERE c.id = ANY(%s)
        """,
        (ids,),
    ).fetchall()
    by_id = {int(row[0]): row for row in rows}
    return [
        RetrievedChunk(
            chunk_id=int(row[0]),
            document_id=int(row[1]),
            texte=row[2],
            numero_page=row[3],
            section=row[4],
            titre=row[5],
            agence=row[6],
            url_source=row[7],
            score_rrf=score,
        )
        for chunk_id, score in ids_scores
        if (row := by_id.get(chunk_id)) is not None
    ]


def hybrid_search(
    conn: psycopg.Connection,
    question: str,
    top_k: int = _DEFAULT_TOP_K,
    settings: Settings | None = None,
) -> list[RetrievedChunk]:
    """Recherche hybride complete : embed -> dense + BM25 -> fusion RRF -> top-k."""
    settings = settings or get_settings()
    (query_embedding,) = embed_texts([question], settings=settings)
    dense_ids = dense_search(conn, query_embedding)
    sparse_ids = sparse_search(conn, question)
    fused = rrf_fuse([dense_ids, sparse_ids])[:top_k]
    return _fetch_chunks(conn, fused)
