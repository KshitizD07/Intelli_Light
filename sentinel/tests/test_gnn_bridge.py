"""
sentinel/tests/test_gnn_bridge.py
==================================
Unit tests for GNNTelemetryBridge and congestion-aware scoring.
"""

from sentinel.anomaly.gnn_bridge import GNNTelemetryBridge
from sentinel.anomaly.scorer import AnomalyScorer
from sentinel.tracker.vehicle_trace import VehicleTrace, Sighting


def test_gnn_bridge_telemetry_cache():
    bridge = GNNTelemetryBridge()
    bridge.update_telemetry("J1", queue_length=18, pressure=0.75)
    assert bridge.get_queue_length("J1") == 18
    assert bridge.get_pressure("J1") == 0.75
    assert bridge.is_congested("J1", queue_threshold=15) is True
    assert bridge.is_congested("J1", queue_threshold=20) is False


def test_detour_justification():
    bridge = GNNTelemetryBridge()
    # High congestion on bypassed junctions
    bridge.update_telemetry("J_MAIN", queue_length=30)
    assert bridge.calculate_detour_justification(["J_MAIN"], detour_ratio=1.5) == 1.0

    # Low congestion on bypassed junctions
    bridge.update_telemetry("J_CLEAR", queue_length=3)
    assert bridge.calculate_detour_justification(["J_CLEAR"], detour_ratio=1.5) == 0.0


def test_congestion_adjusted_anomaly_score():
    bridge = GNNTelemetryBridge()
    # Case A: Main road is JAMMED -> detour score is reduced
    bridge.update_telemetry("J_001", queue_length=40)
    bridge.update_telemetry("J_002", queue_length=40)
    scorer_justified = AnomalyScorer(gnn_bridge=bridge)

    trace = VehicleTrace("TEST_DETOUR")
    for jid, ts in [("J_001", 0), ("J_002", 60), ("J_001", 120), ("J_003", 180)]:
        trace.add_sighting(Sighting(junction_id=jid, timestamp=ts))

    score_justified = scorer_justified._score_route_deviation(trace)
    assert score_justified == 0.0

    # Case B: Main road is CLEAR -> detour is suspicious
    bridge.update_telemetry("J_001", queue_length=1)
    bridge.update_telemetry("J_002", queue_length=1)
    scorer_unjustified = AnomalyScorer(gnn_bridge=bridge)
    score_unjustified = scorer_unjustified._score_route_deviation(trace)
    assert score_unjustified > 0.0
