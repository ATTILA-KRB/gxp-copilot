-- ============================================================
-- Schema logique GxP Copilot (cf. plan de projet, section 5)
-- IMPORTANT : la dimension des embeddings est figee a 1024 ici
-- et DOIT correspondre a EMBEDDING_DIM dans .env (bge-m3, fixe — plan §4).
-- ============================================================

-- ---------- Documents sources (corpus public) ----------
CREATE TABLE IF NOT EXISTS document (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    titre            TEXT NOT NULL,
    agence           TEXT NOT NULL
        CHECK (agence IN ('MHRA', 'FDA', 'PICS', 'WHO', 'EU', 'EMA', 'ANSM', 'ICH')),
    reference        TEXT,
    version          TEXT,
    date_publication DATE,
    url_source       TEXT NOT NULL,
    fichier_local    TEXT NOT NULL,
    -- Empreinte du fichier telecharge : evite la double ingestion.
    sha256           TEXT,
    cree_le          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT document_url_unique UNIQUE (url_source)
);

-- ---------- Fragments indexes (dense + sparse sur la meme ligne) ----------
CREATE TABLE IF NOT EXISTS chunk (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id  BIGINT NOT NULL REFERENCES document (id) ON DELETE CASCADE,
    texte        TEXT   NOT NULL,
    numero_page  INTEGER,
    section      TEXT,
    ordre        INTEGER NOT NULL,                 -- position du chunk dans le document
    embedding    vector(1024),                     -- dense ; NULL tant que non encode
    -- Vecteur plein-texte (BM25) calcule automatiquement a partir du texte.
    tsv          tsvector GENERATED ALWAYS AS (to_tsvector('english', texte)) STORED,
    CONSTRAINT chunk_ordre_unique UNIQUE (document_id, ordre)
);

-- ---------- Journal d'audit : chaque interaction est rejouable ----------
CREATE TABLE IF NOT EXISTS interaction (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    horodatage       TIMESTAMPTZ NOT NULL DEFAULT now(),
    question         TEXT NOT NULL,
    reponse          TEXT,
    provider_utilise TEXT,            -- 'cloud' | 'local'
    modele           TEXT,
    score_confiance  REAL,
    chunks_cites     BIGINT[],        -- ids des chunks cites dans la reponse
    latence_ms       INTEGER
);

-- ---------- Evaluation continue (RAGAS) ----------
CREATE TABLE IF NOT EXISTS eval_run (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    horodatage        TIMESTAMPTZ NOT NULL DEFAULT now(),
    jeu_de_test       TEXT,
    groundedness      REAL,
    context_adherence REAL,
    answer_relevance  REAL
);
