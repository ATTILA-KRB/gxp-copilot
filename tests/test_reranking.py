"""Tests du reranking Cohere (API REST mockee, sans reseau)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings
from app.reranking import cohere_rerank


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, cohere_api_key="test-key", **overrides)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_empty_documents():
    assert cohere_rerank("q", [], _settings()) == []


def test_missing_api_key_rejected():
    with pytest.raises(RuntimeError, match="COHERE_API_KEY"):
        cohere_rerank("q", ["doc"], Settings(_env_file=None))


def test_results_sorted_by_score_desc():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 2, "relevance_score": 0.91},
                    {"index": 0, "relevance_score": 0.40},
                    {"index": 1, "relevance_score": 0.05},
                ]
            },
        )

    ranked = cohere_rerank("audit trail", ["a", "b", "c"], _settings(), client=_client(handler))
    assert ranked == [(2, 0.91), (0, 0.40), (1, 0.05)]


def test_request_payload_contains_model_query_documents():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"results": []})

    cohere_rerank("ma question", ["d1", "d2"], _settings(), client=_client(handler))
    assert seen["model"] == "rerank-v3.5"
    assert seen["query"] == "ma question"
    assert seen["documents"] == ["d1", "d2"]
    assert seen["auth"] == "Bearer test-key"


def test_http_error_propagated():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    with pytest.raises(httpx.HTTPStatusError):
        cohere_rerank("q", ["doc"], _settings(), client=_client(handler))
