"""
sentinel/tests/test_traffic_daemon.py
======================================
Unit tests for TrafficSimulationDaemon.
"""

import pytest
import asyncio
from sentinel.ingestion.event_bus import EventBus
from sentinel.registry import FlaggedVehicleRegistry, FlaggedVehicle
from sentinel.ingestion.sumo_injector import CameraGrid
from sentinel.config import SUMO_NET_FILE
from sentinel.anomaly.gnn_bridge import GNNTelemetryBridge
from sentinel.intercept.orchestrator import InterceptOrchestrator
from sentinel.ingestion.traffic_daemon import TrafficSimulationDaemon


@pytest.fixture
def setup_daemon(tmp_path):
    bus = EventBus()
    reg = FlaggedVehicleRegistry(db_path=str(tmp_path / "reg.db"))
    reg.seed_demo()
    grid = CameraGrid(SUMO_NET_FILE)
    gnn = GNNTelemetryBridge()
    orch = InterceptOrchestrator(registry=reg, audit_file=str(tmp_path / "audit.jsonl"))

    daemon = TrafficSimulationDaemon(
        bus=bus,
        registry=reg,
        camera_grid=grid,
        gnn_bridge=gnn,
        orchestrator=orch,
        tick_interval_s=0.1,
    )
    return daemon, bus, reg, orch, gnn


@pytest.mark.anyio
async def test_fleet_initialization(setup_daemon):
    daemon, _, reg, _, _ = setup_daemon
    assert len(daemon.vehicles) >= 15
    assert "UP32XY9999" in daemon.vehicles
    assert "UP32AB1234" in daemon.vehicles
    assert daemon.vehicles["UP32XY9999"].is_flagged is True


@pytest.mark.anyio
async def test_simulation_step_advances_vehicles(setup_daemon):
    daemon, bus, _, _, _ = setup_daemon
    v = daemon.vehicles["UP32XY9999"]
    initial_progress = v.progress

    # Step simulation multiple times
    for _ in range(5):
        await daemon._step_simulation()

    assert v.progress != initial_progress or v.current_index > 0


@pytest.mark.anyio
async def test_target_vehicle_halts_at_redwall(setup_daemon):
    daemon, bus, reg, orch, _ = setup_daemon
    target_plate = "UP32XY9999"
    v = daemon.vehicles[target_plate]

    # Find the next junction in the vehicle's route
    next_node = v.route[(v.current_index + 1) % len(v.route)]

    # Authorize & trigger intercept
    orch.request_intercept(
        plate=target_plate,
        current_junction=v.route[v.current_index],
        authorized_by="TEST_OP",
        reason="Halt verification test",
    )
    # Ensure next_node is in overridden junctions
    mission = orch.active_missions[target_plate]
    mission.overridden_junctions = [next_node]

    # Force vehicle to approach next_node
    v.progress = 0.90
    await daemon._step_simulation()

    assert v.is_halted is True
    assert "HALTED BY RED-WALL" in v.halt_reason
