"""Tests for confidence metadata computation."""

from src.services.query.response_utils import compute_confidence_metadata


def test_confidence_no_sources():
    result = compute_confidence_metadata([], min_score_threshold=0.10)
    assert result["level"] == "none"
    assert result["is_low_confidence"] is True
    assert result["source_count"] == 0


def test_confidence_high_reranker_scores():
    sources = [{"score": 0.85}, {"score": 0.72}]
    result = compute_confidence_metadata(sources, min_score_threshold=0.10)
    assert result["level"] == "high"
    assert result["is_low_confidence"] is False
    assert result["source_count"] == 2


def test_confidence_low_scores():
    sources = [{"score": 0.25}, {"score": 0.18}]
    result = compute_confidence_metadata(sources, min_score_threshold=0.10)
    assert result["level"] == "very_low"
    assert result["is_low_confidence"] is True
