"""Configuration centralisee, lue depuis l'environnement (.env).

Une seule source de verite pour la base de donnees et le choix du provider.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Selection du fournisseur de modeles.
    provider: Literal["cloud", "local"] = "cloud"

    # Base de donnees.
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "gxp"
    postgres_user: str = "gxp"
    postgres_password: str = "changeme"

    # Embedding : FIXE, hors abstraction provider (plan §4). bge-m3 via Ollama
    # dans les deux modes ; la dimension doit correspondre au schema SQL (vector(1024)).
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024

    # Fournisseur cloud (Mistral).
    mistral_api_key: str = ""
    mistral_generation_model: str = "mistral-large-latest"

    # Reranking cloud (Cohere) + garde-fou de refus (plan §6, pilier 2).
    cohere_api_key: str = ""
    cohere_rerank_model: str = "rerank-v3.5"
    retrieval_candidates: int = 20  # candidats hybrides envoyes au reranker
    rerank_top_k: int = 5           # chunks conserves pour la generation
    rerank_score_threshold: float = 0.3  # sous ce score : refus controle

    # Fournisseur local (Ollama) — sert aussi a l'embedding en mode cloud.
    ollama_base_url: str = "http://localhost:11434"
    ollama_generation_model: str = "llama3.1"

    @property
    def generation_model_name(self) -> str:
        if self.provider == "cloud":
            return self.mistral_generation_model
        return self.ollama_generation_model

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
