# GxP Copilot *(nom de travail)*

Assistant qui répond en langage naturel à des questions réglementaires
(**intégrité des données / ALCOA+**) en s'appuyant **exclusivement** sur un corpus
de documents **publics** (MHRA, FDA, PIC/S, WHO, EU GMP), avec **citation
systématique des sources** (document, agence, page) et **journal d'audit** de
chaque interaction.

> ⚠️ **Disclaimer.** Ceci est une **démonstration technique**. Le corpus est
> **100 % public**, aucune donnée interne ni confidentielle n'est utilisée. Cet
> outil **ne fournit aucun conseil réglementaire** et ne se substitue pas aux
> textes officiels ni à un avis qualifié.

## État du projet

**Phase 0 — Socle & corpus** (en cours). Livrable : corpus indexé, requêtable en
SQL. Le service RAG (FastAPI) et l'UI (SvelteKit) arrivent en Phase 1.

## Architecture (cible)

Ingestion hors-ligne (PDF → parsing → chunking structurel → embeddings) vers
**PostgreSQL + pgvector** (vecteurs denses) **+ tsvector** (BM25 plein-texte) dans
la même table. Recherche **hybride** (dense + BM25, fusion RRF) puis **reranking**
cross-encoder, garde-fou de *groundedness*, génération ancrée avec citations.
Une **abstraction provider** isole le code métier des fournisseurs de modèles
(local Ollama / cloud Mistral), commutable par `PROVIDER=local|cloud`.

## Prérequis

- [uv](https://docs.astral.sh/uv/) (gestion des dépendances Python)
- Docker + Docker Compose (PostgreSQL + pgvector)
- [Ollama](https://ollama.com) + `ollama pull bge-m3` — l'embedding est **fixe**
  (bge-m3, plan §4) et passe par Ollama dans les **deux** modes, y compris cloud
- Une clé `MISTRAL_API_KEY` pour la génération en mode cloud (défaut V1)

## Démarrage (Phase 0)

```bash
# 1. Configuration
cp .env.example .env        # renseigner MISTRAL_API_KEY et POSTGRES_PASSWORD

# 2. Base de données (Postgres + pgvector + schéma)
docker compose up -d

# 3. Dépendances Python
uv sync

# 4. Ingestion du corpus public
uv run python -m ingestion.download    # télécharge les PDF (sources.yaml)
uv run python -m ingestion.index       # parse, chunk, embed, insère en base

# 5. API RAG (Phase 1) — nécessite MISTRAL_API_KEY et COHERE_API_KEY
uv run uvicorn app.main:app --reload
# POST /ask {"question": "..."} -> SSE (sources, tokens, audit) ; GET /health

# 6. UI de chat (SvelteKit + Tailwind, proxy /ask -> :8000 en dev)
cd frontend && npm install && npm run dev
```

## Corpus de départ (intégrité des données)

Documents publics, URL officielles vérifiées (voir `ingestion/sources.yaml`) :
MHRA *GxP Data Integrity Guidance* (2018), FDA *Data Integrity and Compliance
with Drug CGMP — Q&A* (2018), FDA *21 CFR Part 11 — Scope and Application* (2003),
PIC/S *PI 041-1* (2021), WHO *TRS 1033 Annex 4 — Data Integrity* (2021), EU GMP
*Annex 11 — Computerised Systems* et *Chapter 4 — Documentation*.

## Budgets latence / coût (cible V1)

La récupération, pas la génération, est le goulot d'étranglement. Ordres de
grandeur 2026 :

| Architecture | Coût indicatif / requête | Latence |
|---|---|---|
| RAG naïf | ~0,001–0,01 $ | < 1 s |
| **Advanced RAG (hybride + rerank) — cible V1** | ~0,003–0,01 $ | 1–3 s |
| Agentic RAG (Phase 4, optionnel) | ~0,01–0,10 $ | 5–15 s |

En mode local, le coût par requête est nul mais demande GPU/RAM.

## Structure

```
db/          schéma PostgreSQL (extensions, tables, index)
ingestion/   pipeline : download → parse → chunk → index ; registre sources.yaml
app/         configuration + abstraction provider (cloud Mistral / local Ollama)
```
