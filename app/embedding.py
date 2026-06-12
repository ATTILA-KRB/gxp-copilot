"""Embedding fixe bge-m3 via Ollama — hors abstraction provider (plan §4).

Decision structurante : changer de modele d'embedding change l'espace vectoriel
et imposerait une reindexation complete du corpus. L'embedding n'est donc PAS
commutable : bge-m3 (1024 dims, multilingue FR/EN) dans les deux modes, pour
l'indexation comme pour la requete.
"""

from __future__ import annotations

import httpx

from app.config import Settings, get_settings

# Taille de lot : limite la charge utile par requete vers Ollama.
_BATCH_SIZE = 32
_TIMEOUT = httpx.Timeout(120.0)


def embed_texts(
    texts: list[str],
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> list[list[float]]:
    """Encode les textes avec bge-m3 (meme ordre que l'entree).

    Leve une erreur si Ollama est injoignable ou si la dimension ne
    correspond pas au schema SQL (vector(1024)).
    """
    if not texts:
        return []
    settings = settings or get_settings()

    own_client = client is None
    client = client or httpx.Client(base_url=settings.ollama_base_url, timeout=_TIMEOUT)
    try:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[start : start + _BATCH_SIZE]
            response = client.post(
                "/api/embed",
                json={"model": settings.embedding_model, "input": batch},
            )
            response.raise_for_status()
            embeddings = response.json().get("embeddings", [])
            if len(embeddings) != len(batch):
                raise ValueError(
                    f"Ollama a renvoye {len(embeddings)} vecteurs pour {len(batch)} textes."
                )
            for vector in embeddings:
                if len(vector) != settings.embedding_dim:
                    raise ValueError(
                        f"Dimension embedding {len(vector)} != EMBEDDING_DIM "
                        f"{settings.embedding_dim}. Verifier le modele et le schema SQL."
                    )
                vectors.append(vector)
        return vectors
    finally:
        if own_client:
            client.close()
