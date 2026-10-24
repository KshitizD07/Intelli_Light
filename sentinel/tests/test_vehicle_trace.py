"""
sentinel/tests/test_vehicle_trace.py
======================================
Unit tests for VehicleTrace path analysis.
"""

import pytest
from sentinel.tracker.vehicle_trace import VehicleTrace, Sighting


def _make_trace(plate="UP32AB1234"):
    return VehicleTrace(plate)


def _s(junction_id, timestamp, speed=10.0, lat=26.85, lng=80.95):
    return Sighting(
        junction_id=junction_id,
        timestamp=timestamp,
        speed_mps=speed,
        lat=lat,
        lng=lng,
    )


# ---------------------------------------------------------------------------
# Basic properties
# ---------------------------------------------------------------------------

def test_empty_trace():
    t = _make_trace()
    assert t.first_seen is None
    assert t.last_seen is None
    assert t.total_time_s == 0.0
    assert t.unique_junctions == 0
    assert t.junction_sequence == []


def test_single_sighting():
    t = _make_trace()
    t.add_sighting(_s("J_010", 100.0))
    assert t.first_seen.junction_id == "J_010"
    assert t.last_seen.junction_id == "J_010"
    assert t.total_time_s == 0.0
    assert t.unique_junctions == 1


def test_multi_sighting_sequence():
    t = _make_trace()
    for jid, ts in [("J_010", 0), ("J_021", 120), ("J_042", 300)]:
        t.add_sighting(_s(jid, ts))
    assert t.total_time_s == 300.0
    assert t.unique_junctions == 3
    assert t.junction_sequence == ["J_010", "J_021", "J_042"]


def test_junction_sequence_collapses_consecutive_duplicates():
    t = _make_trace()
    for jid, ts in [("J_010", 0), ("J_010", 5), ("J_021", 120)]:
        t.add_sighting(_s(jid, ts))
    # consecutive J_010 should be collapsed to one
    assert t.junction_sequence == ["J_010", "J_021"]


def test_inter_sighting_gap():
    t = _make_trace()
    t.add_sighting(_s("J_010", 0.0))
    t.add_sighting(_s("J_021", 100.0))
    t.add_sighting(_s("J_042", 250.0))
    assert t.inter_sighting_gap(0) == pytest.approx(100.0)
    assert t.inter_sighting_gap(1) == pytest.approx(150.0)
    assert t.inter_sighting_gap(2) == 0.0   # out of range


def test_max_gap():
    t = _make_trace()
    for jid, ts in [("J_010", 0), ("J_021", 50), ("J_042", 300)]:
        t.add_sighting(_s(jid, ts))
    assert t.max_gap_s() == pytest.approx(250.0)


# ---------------------------------------------------------------------------
# Loop detection
# ---------------------------------------------------------------------------

def test_no_loop():
    t = _make_trace()
    for jid, ts in [("J_010", 0), ("J_021", 60), ("J_042", 120)]:
        t.add_sighting(_s(jid, ts))
    detected, jid = t.loop_detected(min_visits=3)
    assert detected is False


def test_loop_detected():
    t = _make_trace()
    junctions = ["J_010", "J_021", "J_010", "J_021", "J_010"]
    for i, jid in enumerate(junctions):
        t.add_sighting(_s(jid, float(i * 60)))
    detected, loop_jid = t.loop_detected(min_visits=3)
    assert detected is True
    assert loop_jid == "J_010"


# ---------------------------------------------------------------------------
# Plate normalization
# ---------------------------------------------------------------------------

def test_plate_normalized_on_init():
    t = VehicleTrace("up32ab1234")
    assert t.plate == "UP32AB1234"


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def test_summary_keys():
    t = _make_trace()
    t.add_sighting(_s("J_010", 0))
    t.add_sighting(_s("J_021", 120))
    s = t.summary()
    assert "plate" in s
    assert "sightings" in s
    assert "anomaly_score" in s
    assert "total_time_s" in s
