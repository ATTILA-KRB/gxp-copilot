"""Tests d'integration de la recherche hybride contre un vrai PostgreSQL+pgvector.

Skippes sans GXP_TEST_DATABASE_URL (executes en CI via le service pgvector).
Le schema est applique depuis db/*.sql — les tests valident donc aussi le DDL.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.retrieval import dense_search, hybrid_search, sparse_search

_DB_URL = os.environ.get("GXP_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not _DB_URL, reason="GXP_TEST_DATABASE_URL non defini (Postgres requis)"
)

_DIM = 1024


def _vec(direction: int) -> list[float]:
    """Vecteur unitaire jouet : seule la composante `direction` vaut 1."""
    v = [0.0] * _DIM
    v[direction] = 1.0
    return v


@pytest.fixture
def conn():
    import psycopg

    project_root = Path(__file__).resolve().parent.parent
    with psycopg.connect(_DB_URL) as conn:
        for sql_file in sorted((project_root / "db").glob("*.sql")):
            conn.execute(sql_file.read_text(encoding="utf-8"))
        conn.execute("TRUNCATE document RESTART IDENTITY CASCADE")
        doc_id = conn.execute(
            """
            INSERT INTO document (titre, agence, url_source, fichier_local)
            VALUES ('Annex 11 Test', 'EU', 'https://example.org/a11', 'a11.pdf')
            RETURNING id
            """
        ).fetchone()[0]
        rows = [
            (doc_id, "Audit trails must record all changes to critical data.", 1, "12.4", 0),
            (doc_id, "Access controls restrict system entry to authorised persons.", 2, "12.1", 1),
            (doc_id, "Backup of data should be checked during validation.", 3, "7.2", 2),
        ]
        for i, (d, texte, page, section, ordre) in enumerate(rows):
            conn.execute(
                """
                INSERT INTO chunk (document_id, texte, numero_page, section, ordre, embedding)
                VALUES (%s, %s, %s, %s, %s, %s::vector)
                """,
                (d, texte, page, section, ordre, str(_vec(i))),
            )
        conn.commit()
        yield conn


def test_dense_search_orders_by_cosine(conn):
    # Requete alignee sur la direction 1 -> le chunk 'Access controls' d'abord.
    ids = dense_search(conn, _vec(1))
    assert ids[0] == 2


def test_sparse_search_matches_keywords(conn):
    ids = sparse_search(conn, "audit trail critical data")
    assert ids and ids[0] == 1


def test_sparse_search_no_match_returns_empty(conn):
    assert sparse_search(conn, "zzz introuvable xyz") == []


def test_hybrid_search_returns_hydrated_chunks(conn, monkeypatch):
    # L'embedder est mocke : pas d'Ollama dans l'environnement de test.
    import app.retrieval

    monkeypatch.setattr(
        app.retrieval, "embed_texts", lambda texts, settings=None: [_vec(0)]
    )
    results = hybrid_search(conn, "audit trail critical data", top_k=3)
    assert results
    top = results[0]
    assert top.chunk_id == 1  # gagnant des deux moteurs
    assert top.titre == "Annex 11 Test"
    assert top.agence == "EU"
    assert top.numero_page == 1
    assert top.section == "12.4"
    assert top.score_rrf > 0
