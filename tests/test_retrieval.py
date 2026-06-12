"""Tests de la fusion RRF (logique pure, sans base de donnees)."""

from __future__ import annotations

from app.retrieval import _RRF_K, rrf_fuse


def test_empty_rankings():
    assert rrf_fuse([]) == []
    assert rrf_fuse([[], []]) == []


def test_single_ranking_preserves_order():
    fused = rrf_fuse([[10, 20, 30]])
    assert [chunk_id for chunk_id, _ in fused] == [10, 20, 30]


def test_item_in_both_rankings_wins():
    # 7 est 2e partout ; 10 et 20 ne sont 1ers que dans une seule liste.
    fused = rrf_fuse([[10, 7, 30], [20, 7, 40]])
    assert fused[0][0] == 7


def test_scores_follow_rrf_formula():
    fused = rrf_fuse([[1], [1]])
    assert fused[0][1] == 2.0 / (_RRF_K + 1)
    fused = rrf_fuse([[1, 2]])
    assert dict(fused)[2] == 1.0 / (_RRF_K + 2)


def test_ties_broken_by_id_for_determinism():
    # 5 et 3 ont exactement le meme score (1er d'une liste chacun).
    fused = rrf_fuse([[5], [3]])
    assert [chunk_id for chunk_id, _ in fused] == [3, 5]


def test_disjoint_rankings_all_present():
    fused = rrf_fuse([[1, 2], [3, 4]])
    assert {chunk_id for chunk_id, _ in fused} == {1, 2, 3, 4}
