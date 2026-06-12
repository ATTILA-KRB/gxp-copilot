"""Abstraction provider : isole tout le code metier des fournisseurs de modeles.

Patron Strategy/Adapter. Une interface unique, deux implementations commutables
par la variable d'environnement PROVIDER (cloud | local). Argument metier :
en mode local, aucune donnee ne quitte la machine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from app.config import Settings, get_settings


class LLMProvider(ABC):
    """Contrat commun a tous les fournisseurs.

    L'embedding n'en fait PAS partie : il est fixe (bge-m3, cf. app.embedding
    et plan §4) car en changer imposerait une reindexation complete du corpus.
    """

    @abstractmethod
    def generate(self, prompt: str, context: str) -> Iterator[str]:
        """Genere une reponse ancree sur le contexte, en streaming (tokens)."""

    @abstractmethod
    def rerank(self, query: str, candidates: list[str]) -> list[tuple[int, float]]:
        """Reordonne les candidats : [(index d'origine, score calibre)] tries
        par score decroissant. Le score alimente le garde-fou de refus."""


def get_provider(settings: Settings | None = None) -> LLMProvider:
    """Fabrique : retourne l'implementation selon PROVIDER.

    Import differe pour ne charger que le SDK reellement utilise.
    """
    settings = settings or get_settings()
    if settings.provider == "cloud":
        from app.providers.cloud_mistral import MistralProvider

        return MistralProvider(settings)
    if settings.provider == "local":
        from app.providers.local_ollama import OllamaProvider

        return OllamaProvider(settings)
    raise ValueError(f"PROVIDER inconnu : {settings.provider!r} (attendu 'cloud' ou 'local')")
