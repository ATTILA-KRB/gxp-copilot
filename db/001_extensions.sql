-- Extensions requises.
-- pgvector : stockage et recherche de vecteurs denses (recherche semantique).
-- Le plein-texte (tsvector / BM25) est natif PostgreSQL, aucune extension requise.
CREATE EXTENSION IF NOT EXISTS vector;
