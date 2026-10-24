"""
sentinel/tests/test_voter.py
=============================
Unit tests for the multi-frame voter and fuzzy match layer.
"""

import pytest
from sentinel.alpr.voter import (
    normalize_plate,
    fuzzy_match,
    PlateVoter,
    VoterPool,
)


# ---------------------------------------------------------------------------
# normalize_plate
# ---------------------------------------------------------------------------

def test_normalize_basic():
    assert normalize_plate("UP 32 AB 1234") == "UP32AB1234"

def test_normalize_hyphens():
    assert normalize_plate("UP-32-AB-1234") == "UP32AB1234"

def test_normalize_mixed():
    assert normalize_plate(" up32ab1234 ") == "UP32AB1234"

def test_normalize_already_clean():
    assert normalize_plate("MH12XY5678") == "MH12XY5678"


# ---------------------------------------------------------------------------
# fuzzy_match
# ---------------------------------------------------------------------------

def test_exact_match():
    score = fuzzy_match("UP32AB1234", "UP32AB1234")
    assert score == 100

def test_one_char_off():
    # 'UP32AB123D' vs 'UP32AB1234' - one char diff -> high similarity
    score = fuzzy_match("UP32AB123D", "UP32AB1234")
    assert score >= 85   # RapidFuzz ratio is 18/20 chars = 90

def test_ocr_substitution_0_D():
    # '0' and 'D' confusion - should still be flagged as a fuzzy match
    score = fuzzy_match("UP32DB1234", "UP320B1234")
    assert score >= 85

def test_clearly_different_plates():
    score = fuzzy_match("KA01AA0001", "TN99ZZ9999")
    assert score < 50


# ---------------------------------------------------------------------------
# PlateVoter
# ---------------------------------------------------------------------------

def test_voter_window_not_full():
    voter = PlateVoter("J_042", window=3)
    assert voter.vote("UP32AB1234", 0.9) is None
    assert voter.vote("UP32AB1234", 0.88) is None
    # third vote -> commits
    result = voter.vote("UP32AB1234", 0.92)
    assert result == "UP32AB1234"

def test_voter_majority_wins():
    voter = PlateVoter("J_001", window=3)
    voter.vote("UP32AB1234", 0.9)
    voter.vote("UP32AB1234", 0.88)
    result = voter.vote("UP32AB1235", 0.6)   # minority read
    assert result == "UP32AB1234"

def test_voter_resets_after_commit():
    voter = PlateVoter("J_002", window=3)
    for _ in range(3):
        voter.vote("MH12XY5678", 0.9)
    # after commit the buffer is cleared; next two votes return None
    assert voter.vote("MH12XY5678", 0.9) is None
    assert voter.vote("MH12XY5678", 0.9) is None

def test_voter_handles_ocr_confusion():
    """Votes where one frame confuses '0' for 'D' should still converge."""
    voter = PlateVoter("J_003", window=3)
    voter.vote("UP32AB1234", 0.9)
    voter.vote("UP32AB1234", 0.85)
    result = voter.vote("UP32AB123D", 0.7)   # OCR confusion on last char
    # majority 'UP32AB1234' should win
    assert result == "UP32AB1234"


# ---------------------------------------------------------------------------
# VoterPool
# ---------------------------------------------------------------------------

def test_voter_pool_creates_per_camera():
    pool = VoterPool(window=2)
    # Two cameras get independent voters
    pool.submit("J_010", "UP01AA0001", 0.9)
    pool.submit("J_011", "UP01AA0002", 0.9)
    r1 = pool.submit("J_010", "UP01AA0001", 0.9)  # J_010 window=2, commits
    r2 = pool.submit("J_011", "UP01AA0002", 0.9)  # J_011 window=2, commits
    assert r1 == "UP01AA0001"
    assert r2 == "UP01AA0002"

def test_voter_pool_reset_camera():
    pool = VoterPool(window=3)
    pool.submit("J_020", "KA01BB1234", 0.9)
    pool.submit("J_020", "KA01BB1234", 0.88)
    pool.reset_camera("J_020")
    # After reset, need full window again
    result = pool.submit("J_020", "KA01BB1234", 0.9)
    assert result is None
