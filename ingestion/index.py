"""Indexation : PDF -> parsing -> chunking -> embeddings -> PostgreSQL.

Idempotent : un document deja present (meme url_source) est ignore.
Livrable Phase 0 : corpus indexe, requetable en SQL.

Usage : uv run python -m ingestion.index
"""

from __future__ import annotations

import sys

import httpx
import psycopg
from pgvector.psycopg import register_vector

from app.config import get_settings
from app.embedding import embed_texts
from ingestion.chunk import Chunk, chunk_pages
from ingestion.download import download_one
from ingestion.parse import parse_pdf
from ingestion.sources import PDF_DIR, SourceDoc, load_sources


def _ensure_pdf(doc: SourceDoc) -> str:
    """Garantit la presence locale du PDF ; renvoie son sha256."""
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=httpx.Timeout(60.0)) as client:
        return download_one(doc, client)


def _document_exists(conn: psycopg.Connection, url_source: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM document WHERE url_source = %s", (url_source,)
    ).fetchone()
    return row is not None


def _insert_document(conn: psycopg.Connection, doc: SourceDoc, sha256: str) -> int:
    row = conn.execute(
        """
        INSERT INTO document
            (titre, agence, reference, version, date_publication, url_source,
             fichier_local, sha256)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            doc.titre,
            doc.agence,
            doc.reference,
            doc.version,
            doc.date_publication,
            doc.url_source,
            str(doc.local_pdf_path),
            sha256,
        ),
    ).fetchone()
    assert row is not None
    return int(row[0])


def _insert_chunks(
    conn: psycopg.Connection,
    document_id: int,
    chunks: list[Chunk],
    embeddings: list[list[float]],
) -> None:
    rows = [
        (document_id, c.texte, c.numero_page, c.section, c.ordre, emb)
        for c, emb in zip(chunks, embeddings, strict=True)
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO chunk
                (document_id, texte, numero_page, section, ordre, embedding)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            rows,
        )


def index_document(conn: psycopg.Connection, doc: SourceDoc) -> int:
    """Indexe un document. Renvoie le nombre de chunks inseres (0 si deja present)."""
    if _document_exists(conn, doc.url_source):
        print(f"[skip] {doc.slug} (deja indexe)")
        return 0

    sha256 = _ensure_pdf(doc)
    pages = parse_pdf(doc.local_pdf_path)
    chunks = chunk_pages(pages)
    if not chunks:
        print(f"[warn] {doc.slug}: aucun chunk extrait", file=sys.stderr)
        return 0

    embeddings = embed_texts([c.texte for c in chunks])

    document_id = _insert_document(conn, doc, sha256)
    _insert_chunks(conn, document_id, chunks, embeddings)
    conn.commit()
    print(f"[ok]   {doc.slug}: {len(chunks)} chunks sur {len(pages)} pages")
    return len(chunks)


def main() -> int:
    settings = get_settings()
    docs = load_sources()
    total_chunks = 0
    failures = 0

    with psycopg.connect(settings.database_url) as conn:
        register_vector(conn)
        for doc in docs:
            try:
                total_chunks += index_document(conn, doc)
            except Exception as exc:  # noqa: BLE001 - poursuivre le lot
                conn.rollback()
                failures += 1
                print(f"[FAIL] {doc.slug}: {exc}", file=sys.stderr)

    print(f"\nTermine : {total_chunks} chunks indexes, {failures} echec(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
