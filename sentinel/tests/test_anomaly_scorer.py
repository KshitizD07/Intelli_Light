"""
sentinel/tests/test_anomaly_scorer.py
=======================================
Unit tests for AnomalyScorer components.
"""

import pytest
from sentinel.tracker.vehicle_trace import VehicleTrace, Sighting
from sentinel.anomaly.scorer import AnomalyScorer
from sentinel.config import ANOMALY_DEVIATION_THRESHOLD


def _s(jid, ts, lat=26.85, lng=80.95, speed=10.0):
    return Sighting(junction_id=jid, timestamp=ts, speed_mps=speed, lat=lat, lng=lng)


def _make_scorer():
    return AnomalyScorer()


# ---------------------------------------------------------------------------
# Empty / single sighting -> score 0
# ---------------------------------------------------------------------------

def test_empty_trace_score_zero():
    t = VehicleTrace("UP32AB1234")
    scorer = _make_scorer()
    assert scorer.score(t) == 0.0


def test_single_sighting_score_zero():
    t = VehicleTrace("UP32AB1234")
    t.add_sighting(_s("J_010", 0.0))
    scorer = _make_scorer()
    assert scorer.score(t) == 0.0


# ---------------------------------------------------------------------------
# Normal straight-line route -> low score
# ---------------------------------------------------------------------------

def test_straight_route_low_score():
    t = VehicleTrace("MH12XY5678")
    for jid, ts in [("J_010", 0), ("J_021", 120), ("J_042", 240), ("J_055", 360)]:
        t.add_sighting(_s(jid, ts))
    scorer = _make_scorer()
    score = scorer.score(t)
    assert score < ANOMALY_DEVIATION_THRESHOLD, f"Expected low score, got {score}"


# ---------------------------------------------------------------------------
# Loop detection -> elevated score
# ---------------------------------------------------------------------------

def test_looping_vehicle_high_score():
    t = VehicleTrace("UP32XY9999")
    junctions = ["J_010", "J_021", "J_010", "J_021", "J_010", "J_021"]
    for i, jid in enumerate(junctions):
        t.add_sighting(_s(jid, float(i * 60)))
    scorer = _make_scorer()
    score = scorer.score(t)
    assert score >= ANOMALY_DEVIATION_THRESHOLD, f"Expected high score for loop, got {score}"


# ---------------------------------------------------------------------------
# Extended stop -> elevated score
# ---------------------------------------------------------------------------

def test_extended_stop_elevated_score():
    t = VehicleTrace("UP41BC5678")
    # Route that revisits J_010 three times (loop) AND has a long stop.
    # Combined score should exceed the threshold.
    junctions = ["J_010", "J_021", "J_010", "J_021", "J_010"]
    timestamps = [0.0, 60.0, 120.0, 180.0, 10980.0]   # last hop has a 3-hr gap
    for jid, ts in zip(junctions, timestamps):
        t.add_sighting(_s(jid, ts))
    scorer = _make_scorer()
    score = scorer.score(t)
    assert score >= ANOMALY_DEVIATION_THRESHOLD, f"Expected high score, got {score}"


# ---------------------------------------------------------------------------
# explain() returns all keys
# ---------------------------------------------------------------------------

def test_explain_keys():
    t = VehicleTrace("DL01AB9999")
    t.add_sighting(_s("J_010", 0.0))
    t.add_sighting(_s("J_021", 120.0))
    scorer = _make_scorer()
    breakdown = scorer.explain(t)
    for key in ("route_deviation", "loop", "extended_stop", "speed_anomaly", "total"):
        assert key in breakdown


def test_explain_values_in_range():
    t = VehicleTrace("KA01AA0001")
    for jid, ts in [("J_010", 0), ("J_010", 30), ("J_010", 60), ("J_021", 180)]:
        t.add_sighting(_s(jid, ts))
    scorer = _make_scorer()
    breakdown = scorer.explain(t)
    for key, val in breakdown.items():
        assert 0.0 <= val <= 1.0, f"Score out of range: {key}={val}"


# ---------------------------------------------------------------------------
# Route deviation component
# ---------------------------------------------------------------------------

def test_route_deviation_no_revisits():
    """A route with no repeated junctions has zero deviation."""
    t = VehicleTrace("TEST0001")
    for jid, ts in [("J_001", 0), ("J_002", 60), ("J_003", 120)]:
        t.add_sighting(_s(jid, ts))
    scorer = _make_scorer()
    assert scorer._score_route_deviation(t) == pytest.approx(0.0)


def test_route_deviation_with_revisits():
    """A route that backtracks has positive deviation."""
    t = VehicleTrace("TEST0002")
    for jid, ts in [("J_001", 0), ("J_002", 60), ("J_001", 120), ("J_003", 180)]:
        t.add_sighting(_s(jid, ts))
    scorer = _make_scorer()
    assert scorer._score_route_deviation(t) > 0.0
