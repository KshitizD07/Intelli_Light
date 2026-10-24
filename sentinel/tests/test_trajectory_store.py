"""
sentinel/tests/test_trajectory_store.py
========================================
Unit tests for TrajectoryStore.
"""

import os
import pytest
from sentinel.tracker.trajectory_store import TrajectoryStore
from sentinel.tracker.vehicle_trace import VehicleTrace, Sighting


@pytest.fixture
def store(tmp_path):
    db = str(tmp_path / "test_traces.db")
    return TrajectoryStore(db_path=db)


def test_record_sighting_and_retrieve(store):
    s = Sighting(junction_id="J1", timestamp=100.0, speed_mps=12.5, lat=26.85, lng=80.95)
    store.record_sighting("UP32AB1234", s)

    trace = VehicleTrace("UP32AB1234")
    trace.add_sighting(s)
    store.update_trajectory(trace, [(80.95, 26.85)])

    traj = store.get_trajectory("UP32AB1234")
    assert traj is not None
    assert traj["plate"] == "UP32AB1234"
    assert traj["start_junction"] == "J1"
    assert len(traj["geometry"]) == 1


def test_od_matrix_accumulation(store):
    t = VehicleTrace("MH12XY0001")
    t.add_sighting(Sighting(junction_id="ORIGIN_J", timestamp=10.0))
    t.add_sighting(Sighting(junction_id="DEST_J", timestamp=60.0))
    store.update_trajectory(t)

    od = store.get_od_matrix()
    assert len(od) == 1
    assert od[0]["origin_junction"] == "ORIGIN_J"
    assert od[0]["destination_junction"] == "DEST_J"
    assert od[0]["trip_count"] == 1
    assert od[0]["avg_duration_s"] == 50.0


def test_plausibility_check(store):
    plate = "DL01TEST"
    s1 = Sighting(junction_id="J1", timestamp=100.0, lat=26.8500, lng=80.9500)
    store.record_sighting(plate, s1)

    # Plausible hop: 100m in 10s (10 m/s)
    s2 = Sighting(junction_id="J2", timestamp=110.0, lat=26.8508, lng=80.9500)
    ok, reason = store.verify_plausibility(plate, s2, max_speed_mps=30.0)
    assert ok is True

    # Impossible hop: 50km in 10s (5000 m/s)
    s_teleport = Sighting(junction_id="J_FAR", timestamp=110.0, lat=27.5000, lng=81.5000)
    ok_bad, reason_bad = store.verify_plausibility(plate, s_teleport, max_speed_mps=30.0)
    assert ok_bad is False
    assert "Impossible hop" in reason_bad
