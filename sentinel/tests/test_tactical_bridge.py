"""
sentinel/tests/test_tactical_bridge.py
======================================
Unit tests for TacticalGuidanceBridge and kinematic signal regulation.
"""

import pytest
from sentinel.registry import FlaggedVehicleRegistry, FlaggedVehicle
from sentinel.intercept.orchestrator import InterceptOrchestrator
from sentinel.intercept.failsafe_bridge import SentinelFailsafeBridge
from sentinel.intercept.tactical_bridge import (
    TacticalGuidanceBridge,
    TacticalDirective,
    TacticalStage,
)


@pytest.fixture
def setup_bridge(tmp_path):
    reg = FlaggedVehicleRegistry(db_path=str(tmp_path / "reg.db"))
    reg.seed_demo()
    orch = InterceptOrchestrator(registry=reg, audit_file=str(tmp_path / "audit.jsonl"))
    fs_bridge = SentinelFailsafeBridge(orchestrator=orch)
    t_bridge = TacticalGuidanceBridge(orchestrator=orch, failsafe_bridge=fs_bridge)
    return t_bridge, orch, reg


def test_no_directive_without_active_intercept(setup_bridge):
    bridge, _, _ = setup_bridge
    d = bridge.get_directive("J1", plate="UP32XY9999")
    assert d is None


def test_tactical_directive_created_on_intercept(setup_bridge):
    bridge, orch, _ = setup_bridge
    plate = "UP32XY9999"
    res = orch.request_intercept(
        plate=plate,
        current_junction="J1",
        authorized_by="TEST_OP",
        reason="Pursuit",
    )
    assert res["success"] is True
    locked_j = res["overridden_junctions"][0]

    directive = bridge.get_directive(locked_j, plate=plate, distance_to_junction_m=300.0)
    assert directive is not None
    assert directive.target_plate == plate
    assert directive.stage == TacticalStage.METERING
    assert directive.pedestrian_clearance_s >= 15
    assert directive.max_red_hold_s <= 120


def test_stage_progression_by_distance(setup_bridge):
    bridge, orch, _ = setup_bridge
    plate = "UP32XY9999"
    orch.request_intercept(plate=plate, current_junction="J1", authorized_by="TEST_OP", reason="Test")
    mission = orch.active_missions[plate]
    locked_j = mission.overridden_junctions[0]

    # > 250m -> METERING
    d_far = bridge.get_directive(locked_j, plate=plate, distance_to_junction_m=400.0)
    assert d_far.stage == TacticalStage.METERING
    assert d_far.target_speed_mps > 5.0

    # 100m -> CHOKE
    d_mid = bridge.get_directive(locked_j, plate=plate, distance_to_junction_m=100.0)
    assert d_mid.stage == TacticalStage.CHOKE
    assert d_mid.target_speed_mps < 5.0

    # 20m -> CONTAINMENT
    d_close = bridge.get_directive(locked_j, plate=plate, distance_to_junction_m=20.0)
    assert d_close.stage == TacticalStage.CONTAINMENT
    assert d_close.target_speed_mps == 0.0


def test_kinematic_target_speed_deceleration_profile(setup_bridge):
    bridge, orch, _ = setup_bridge
    plate = "UP32XY9999"
    orch.request_intercept(plate=plate, current_junction="J1", authorized_by="TEST_OP", reason="Test")
    mission = orch.active_missions[plate]
    target_node = mission.overridden_junctions[0]

    base_v = 16.5  # ~60 km/h

    # 1. Early approach: full cruising speed
    v1, status1 = bridge.get_kinematic_target_speed(plate, target_node, progress=0.20, base_speed_mps=base_v)
    assert v1 == base_v
    assert "APPROACHING" in status1

    # 2. Downstream queue visible: progressive deceleration
    v2, status2 = bridge.get_kinematic_target_speed(plate, target_node, progress=0.55, base_speed_mps=base_v)
    assert v2 < base_v
    assert v2 >= 5.0
    assert "METERING" in status2

    # 3. Queue approach: braking down to crawl
    v3, status3 = bridge.get_kinematic_target_speed(plate, target_node, progress=0.80, base_speed_mps=base_v)
    assert v3 < 5.0
    assert "BRAKING" in status3

    # 4. Containment: complete stop
    v4, status4 = bridge.get_kinematic_target_speed(plate, target_node, progress=0.90, base_speed_mps=base_v)
    assert v4 == 0.0
    assert "CONTAINED" in status4


def test_emergency_vehicle_preemption_suspends_directive(setup_bridge):
    bridge, orch, _ = setup_bridge
    plate = "UP32XY9999"
    orch.request_intercept(plate=plate, current_junction="J1", authorized_by="TEST_OP", reason="Test")
    mission = orch.active_missions[plate]
    target_node = mission.overridden_junctions[0]

    # Without emergency vehicle: directive active
    d_normal = bridge.get_directive(target_node, plate=plate, emergency_vehicle_present=False)
    assert d_normal is not None

    # With ambulance / fire engine: directive immediately suspended
    d_evp = bridge.get_directive(target_node, plate=plate, emergency_vehicle_present=True)
    assert d_evp is None


def test_ntcip_plan_encoding(setup_bridge):
    bridge, orch, _ = setup_bridge
    plate = "UP32XY9999"
    orch.request_intercept(plate=plate, current_junction="J1", authorized_by="TEST_OP", reason="Test")
    mission = orch.active_missions[plate]
    target_node = mission.overridden_junctions[0]

    directive = bridge.get_directive(target_node, plate=plate, distance_to_junction_m=50.0)
    plan = bridge.compute_ntcip_plan(directive)

    assert "phase_hold_mask" in plan
    assert "phase_force_off_mask" in plan
    assert "phase_omit_mask" in plan
    assert plan["pedestrian_clearance_s"] >= 15
    assert plan["split_seconds"] <= 120
