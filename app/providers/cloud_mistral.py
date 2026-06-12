"""Implementation cloud : Mistral (angle souverain EU). Defaut V1.

Fournit la generation ancree. Le reranking cloud (Cohere / Voyage, cf. plan
section 4) sera branche en Phase 1. L'embedding est fixe hors provider
(bge-m3, cf. app.embedding).
"""

from __future__ import annotations

from collections.abc import Iterator

from app.config import Settings
from app.providers.base import LLMProvider

# Instruction systeme : ancrage strict + refus controle (pilier reglementaire).
_SYSTEM_PROMPT = (
    "Tu reponds UNIQUEMENT a partir du contexte fourni, qui provient de documents "
    "reglementaires publics. Cite systematiquement tes sources. Si le contexte ne "
    "contient pas l'information, reponds exactement : "
    "\"Information non trouvée dans le corpus.\" N'invente jamais."
)


class MistralProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        if not settings.mistral_api_key:
            raise RuntimeError(
                "MISTRAL_API_KEY est vide. Renseigner la cle dans .env pour le mode cloud."
            )
        # Import differe : le SDK n'est charge que si le provider cloud est utilise.
        try:  # SDK mistralai >= 2.x
            from mistralai.client import Mistral
        except ImportError:  # SDK 1.x
            from mistralai import Mistral

        self._settings = settings
        self._client = Mistral(api_key=settings.mistral_api_key)

    def generate(self, prompt: str, context: str) -> Iterator[str]:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Contexte :\n{context}\n\nQuestion : {prompt}"},
        ]
        stream = self._client.chat.stream(
            model=self._settings.mistral_generation_model,
            messages=messages,
        )
        for event in stream:
            delta = event.data.choices[0].delta.content
            if delta:
                yield delta

    def rerank(self, query: str, candidates: list[str]) -> list[tuple[int, float]]:
        from app.reranking import cohere_rerank

        return cohere_rerank(query, candidates, self._settings)
