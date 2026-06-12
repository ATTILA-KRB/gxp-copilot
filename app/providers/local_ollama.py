"""Implementation locale : Ollama (aucune donnee ne quitte la machine).

Cloud-first en V1 : l'interface est en place mais la validation reelle est
reportee (necessite GPU/RAM, cf. plan section 8). Le but est de garantir que le
code metier ne se couple jamais au cloud.
"""

from __future__ import annotations

from collections.abc import Iterator

from app.config import Settings
from app.providers.base import LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def generate(self, prompt: str, context: str) -> Iterator[str]:
        raise NotImplementedError(
            "Provider local non encore implemente (cloud-first en V1). "
            "Utiliser PROVIDER=cloud."
        )

    def rerank(self, query: str, candidates: list[str]) -> list[tuple[int, float]]:
        raise NotImplementedError(
            "Reranking local (BGE-reranker-v2) prevu apres la baseline cloud."
        )
