-- ============================================================
-- Index pour la recherche hybride (Phase 1) et les jointures.
-- ============================================================

-- Dense : HNSW + distance cosinus (vecteurs normalises -> cosinus pertinent).
-- Cree maintenant ; reste valide meme si les embeddings sont remplis ensuite.
CREATE INDEX IF NOT EXISTS chunk_embedding_hnsw
    ON chunk USING hnsw (embedding vector_cosine_ops);

-- Sparse : GIN sur le tsvector (recherche plein-texte BM25).
CREATE INDEX IF NOT EXISTS chunk_tsv_gin
    ON chunk USING gin (tsv);

-- Jointure chunk -> document.
CREATE INDEX IF NOT EXISTS chunk_document_id
    ON chunk (document_id);

-- Filtres frequents sur le journal d'audit.
CREATE INDEX IF NOT EXISTS interaction_horodatage
    ON interaction (horodatage DESC);
