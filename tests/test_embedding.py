"""Tests de l'embedder fixe bge-m3 (Ollama mocke, sans reseau)."""

from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.embedding import _BATCH_SIZE, embed_texts

_DIM = 1024


def _settings() -> Settings:
    return Settings(_env_file=None)


def _client_returning(dim: int, calls: list[int] | None = None) -> httpx.Client:
    """Client mocke : renvoie un vecteur de dimension `dim` par texte recu."""

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        payload = json.loads(request.content)
        n = len(payload["input"])
        if calls is not None:
            calls.append(n)
        return httpx.Response(200, json={"embeddings": [[0.1] * dim for _ in range(n)]})

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")


def test_empty_input():
    assert embed_texts([], settings=_settings()) == []


def test_returns_one_vector_per_text_in_order():
    client = _client_returning(_DIM)
    vectors = embed_texts(["a", "b", "c"], settings=_settings(), client=client)
    assert len(vectors) == 3
    assert all(len(v) == _DIM for v in vectors)


def test_batching_respects_batch_size():
    calls: list[int] = []
    client = _client_returning(_DIM, calls)
    texts = [f"texte {i}" for i in range(_BATCH_SIZE + 5)]
    vectors = embed_texts(texts, settings=_settings(), client=client)
    assert len(vectors) == len(texts)
    assert calls == [_BATCH_SIZE, 5]


def test_wrong_dimension_rejected():
    client = _client_returning(768)  # != vector(1024) du schema SQL
    with pytest.raises(ValueError, match="Dimension embedding"):
        embed_texts(["a"], settings=_settings(), client=client)


def test_missing_vectors_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": []})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    with pytest.raises(ValueError, match="vecteurs"):
        embed_texts(["a"], settings=_settings(), client=client)


def test_http_error_propagated():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    with pytest.raises(httpx.HTTPStatusError):
        embed_texts(["a"], settings=_settings(), client=client)
