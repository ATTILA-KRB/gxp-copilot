"""Tests du pipeline RAG : garde-fou de refus, top-k, construction du contexte."""

from __future__ import annotations

import pytest

import app.rag as rag
from app.config import Settings
from app.retrieval import RetrievedChunk


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def _chunk(chunk_id: int, texte: str = "texte") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=1,
        texte=texte,
        numero_page=chunk_id,
        section=f"{chunk_id}.1",
        titre="Annex 11",
        agence="EU",
        url_source="https://example.org/a11",
        score_rrf=0.05,
    )


class _StubProvider:
    """Provider de test : rerank fixe, generation non utilisee ici."""

    def __init__(self, ranked: list[tuple[int, float]]) -> None:
        self._ranked = ranked

    def rerank(self, query: str, candidates: list[str]) -> list[tuple[int, float]]:
        return self._ranked

    def generate(self, prompt: str, context: str):  # pragma: no cover
        raise AssertionError("generate ne doit pas etre appele dans ces tests")


@pytest.fixture
def candidates(monkeypatch: pytest.MonkeyPatch) -> list[RetrievedChunk]:
    chunks = [_chunk(1), _chunk(2), _chunk(3)]
    monkeypatch.setattr(rag, "hybrid_search", lambda conn, q, top_k, settings: chunks)
    return chunks


def test_refusal_when_no_candidates(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(rag, "hybrid_search", lambda conn, q, top_k, settings: [])
    selection = rag.select_context(None, "q", _StubProvider([]), _settings())
    assert selection.refused
    assert selection.chunks == []
    assert selection.score_confiance == 0.0


def test_refusal_when_best_score_below_threshold(candidates):
    provider = _StubProvider([(0, 0.10), (1, 0.05)])
    selection = rag.select_context(None, "q", provider, _settings(rerank_score_threshold=0.3))
    assert selection.refused
    assert selection.chunks == []
    assert selection.score_confiance == 0.10  # score loggue meme en cas de refus


def test_acceptance_keeps_top_k_above_threshold(candidates):
    provider = _StubProvider([(2, 0.95), (0, 0.50), (1, 0.10)])
    settings = _settings(rerank_score_threshold=0.3, rerank_top_k=5)
    selection = rag.select_context(None, "q", provider, settings)
    assert not selection.refused
    assert selection.score_confiance == 0.95
    # Le chunk sous le seuil (index 1) est ecarte ; l'ordre suit le reranker.
    assert [c.chunk_id for c in selection.chunks] == [3, 1]


def test_top_k_limit_applied(candidates):
    provider = _StubProvider([(0, 0.9), (1, 0.8), (2, 0.7)])
    settings = _settings(rerank_score_threshold=0.3, rerank_top_k=2)
    selection = rag.select_context(None, "q", provider, settings)
    assert [c.chunk_id for c in selection.chunks] == [1, 2]


def test_build_context_numbers_and_cites_sources():
    context = rag.build_context([_chunk(1, "Premier texte."), _chunk(2, "Second texte.")])
    assert "[1] Annex 11 (EU, p. 1, section 1.1)" in context
    assert "Premier texte." in context
    assert "[2] Annex 11 (EU, p. 2, section 2.1)" in context


def test_build_context_omits_missing_page_and_section():
    chunk = RetrievedChunk(
        chunk_id=9,
        document_id=1,
        texte="Texte.",
        numero_page=None,
        section=None,
        titre="Doc",
        agence="FDA",
        url_source="https://example.org",
        score_rrf=0.01,
    )
    context = rag.build_context([chunk])
    assert "[1] Doc (FDA)" in context
    assert "p. " not in context


def test_refusal_message_is_exact():
    # Le message est contractuel (prompt systeme + UI + tests d'evaluation).
    assert rag.REFUSAL == "Information non trouvée dans le corpus."
