"""Test d'integration du journal d'audit (Postgres requis, comme test_retrieval_db)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.rag import log_interaction

_DB_URL = os.environ.get("GXP_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not _DB_URL, reason="GXP_TEST_DATABASE_URL non defini (Postgres requis)"
)


@pytest.fixture
def conn():
    import psycopg

    project_root = Path(__file__).resolve().parent.parent
    with psycopg.connect(_DB_URL) as conn:
        for sql_file in sorted((project_root / "db").glob("*.sql")):
            conn.execute(sql_file.read_text(encoding="utf-8"))
        conn.execute("TRUNCATE interaction RESTART IDENTITY")
        conn.commit()
        yield conn


def test_interaction_logged_and_replayable(conn):
    interaction_id = log_interaction(
        conn,
        question="Que dit l'annexe 11 sur les audit trails ?",
        reponse="Les modifications de donnees critiques doivent etre tracees [1].",
        provider_utilise="cloud",
        modele="mistral-large-latest",
        score_confiance=0.92,
        chunks_cites=[101, 102],
        latence_ms=1840,
    )
    assert interaction_id == 1

    row = conn.execute(
        """
        SELECT question, reponse, provider_utilise, modele, score_confiance,
               chunks_cites, latence_ms, horodatage
        FROM interaction WHERE id = %s
        """,
        (interaction_id,),
    ).fetchone()
    assert row is not None
    assert row[0].startswith("Que dit l'annexe 11")
    assert row[2] == "cloud"
    assert row[4] == pytest.approx(0.92)
    assert list(row[5]) == [101, 102]
    assert row[6] == 1840
    assert row[7] is not None  # horodatage automatique
