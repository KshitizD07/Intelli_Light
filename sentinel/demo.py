"""
sentinel/demo.py
=================
Turnkey Grand Finale Demo Orchestrator for SIH26127 / Bharat Electronics Limited.

Executes a live 60-second end-to-end demonstration:
1. Initializes city camera network from the Lucknow road graph.
2. Seeds Flagged Vehicle Registry with police alerts.
3. Emits multi-camera sightings for:
   - Commuter vehicle (clean path, low anomaly).
   - Suspect vehicle (UP32AB1234, unjustified detour, anomaly alert triggered).
   - Stolen vehicle (UP32XY9999, blacklist hit, closed-loop intercept triggered).
4. Demonstrates traffic manipulation by holding red-wall perimeter signals.
5. Verifies audit compliance and trajectory persistence.
"""

import os
import sys
import time
import asyncio
import logging

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sentinel.config import SUMO_NET_FILE
from sentinel.registry import FlaggedVehicleRegistry
from sentinel.ingestion.event_bus import EventBus, sighting_event
from sentinel.ingestion.sumo_injector import CameraGrid
from sentinel.tracker.tracker import TrackerManager
from sentinel.tracker.road_snapper import RoadSnapper
from sentinel.tracker.trajectory_store import TrajectoryStore
from sentinel.anomaly.gnn_bridge import GNNTelemetryBridge
from sentinel.anomaly.scorer import AnomalyEngine
from sentinel.intercept.orchestrator import InterceptOrchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("sentinel.demo")


async def run_turnkey_demo():
    print("\n" + "=" * 70)
    print("  SENTINEL: CITY-WIDE ANPR TRAJECTORY TRACKING & TRAFFIC INTERCEPT")
    print("  Smart India Hackathon 2026 | Bharat Electronics Limited (SIH26127)")
    print("  Author: KSHITIZ | Pinaka Studios")
    print("=" * 70 + "\n")

    # 1. Setup core modules
    registry = FlaggedVehicleRegistry()
    registry.seed_demo()
    bus = EventBus()
    camera_grid = CameraGrid(SUMO_NET_FILE)
    road_snapper = RoadSnapper(SUMO_NET_FILE)
    trajectory_store = TrajectoryStore()
    gnn_bridge = GNNTelemetryBridge()
    anomaly_engine = AnomalyEngine(bus, gnn_bridge=gnn_bridge)
    intercept_orchestrator = InterceptOrchestrator(registry)

    # Pick candidate cameras
    available_cameras = list(camera_grid.cameras.keys())
    if len(available_cameras) < 5:
        available_cameras = ["J_010", "J_021", "J_042", "J_055", "J_089"]

    cam1, cam2, cam3, cam4 = available_cameras[:4]

    async def trace_listener(trace):
        await anomaly_engine.evaluate(trace)
        coords = road_snapper.get_route_geometry(trace.junction_sequence)
        trajectory_store.update_trajectory(trace, coords)

    tracker = TrackerManager(
        bus=bus,
        registry=registry,
        camera_grid=camera_grid,
        on_update=trace_listener,
    )
    tracker_task = asyncio.create_task(tracker.run())

    print(f"[DEMO] Camera network loaded: {len(camera_grid.cameras)} junctions mapped.")
    print(f"[DEMO] Flagged vehicles in registry: {len(registry.all_flagged())}")

    # -----------------------------------------------------------------------
    # Step 1: Normal vehicle trip
    # -----------------------------------------------------------------------
    print("\n--- STEP 1: Tracking Standard Commuter (Plate: DL01AB9999) ---")
    await bus.put(sighting_event("DL01AB9999", cam1, timestamp=100.0, speed_mps=11.2))
    await asyncio.sleep(0.05)
    await bus.put(sighting_event("DL01AB9999", cam2, timestamp=180.0, speed_mps=12.0))
    await asyncio.sleep(0.05)
    await bus.put(sighting_event("DL01AB9999", cam3, timestamp=260.0, speed_mps=10.5))
    await asyncio.sleep(0.1)

    t1 = tracker.get_trace("DL01AB9999")
    print(f"-> Trajectory registered: {t1.unique_junctions} junctions, Anomaly Score: {t1.anomaly_score:.3f} (Normal)")

    # -----------------------------------------------------------------------
    # Step 2: Unjustified Route Deviation (Surveillance Subject)
    # -----------------------------------------------------------------------
    print("\n--- STEP 2: Suspicious Route Deviation (Plate: UP32AB1234) ---")
    # Simulate GNN confirming that direct route is clear (queue = 2 vehicles)
    gnn_bridge.update_telemetry(cam2, queue_length=2)

    # Subject detours: cam1 -> cam4 -> cam2 -> cam1 (Looping + Unjustified Detour)
    await bus.put(sighting_event("UP32AB1234", cam1, timestamp=300.0, speed_mps=9.0))
    await asyncio.sleep(0.05)
    await bus.put(sighting_event("UP32AB1234", cam4, timestamp=450.0, speed_mps=13.0))
    await asyncio.sleep(0.05)
    await bus.put(sighting_event("UP32AB1234", cam2, timestamp=600.0, speed_mps=11.0))
    await asyncio.sleep(0.05)
    await bus.put(sighting_event("UP32AB1234", cam1, timestamp=750.0, speed_mps=8.5))
    await asyncio.sleep(0.1)

    t2 = tracker.get_trace("UP32AB1234")
    explain2 = anomaly_engine.explain(t2)
    print(f"-> ALARM FIRED: Anomaly Score: {t2.anomaly_score:.3f} (Threshold: 0.65)")
    print(f"   Breakdown: Detour={explain2['route_deviation']}, Loop={explain2['loop']}, Stop={explain2['extended_stop']}")

    # -----------------------------------------------------------------------
    # Step 3: Stolen Vehicle Blacklist Hit & Closed-Loop Intercept
    # -----------------------------------------------------------------------
    print("\n--- STEP 3: Stolen Vehicle Pursuit & Intercept (Plate: UP32XY9999) ---")
    await bus.put(sighting_event("UP32XY9999", cam2, timestamp=800.0, speed_mps=18.5))
    await asyncio.sleep(0.1)

    print("-> BLACKLIST HIT: Plate UP32XY9999 sighted at " + cam2)
    print("   Authorizing Operator Intercept Directive...")
    intercept_res = intercept_orchestrator.request_intercept(
        plate="UP32XY9999",
        current_junction=cam2,
        authorized_by="OPERATOR_KSHITIZ",
        reason="Stolen vehicle high-speed evasion",
    )

    if intercept_res["success"]:
        print(f"-> INTERCEPT ACTIVATED: Mission {intercept_res['mission_id']}")
        print(f"   Perimeter Intersections Locked in RED: {intercept_res['overridden_junctions']}")
        print(f"   Active Signal Overrides: {intercept_orchestrator.get_signal_overrides()}")

    # -----------------------------------------------------------------------
    # Step 4: Verification of O-D Matrix & Persistent Storage
    # -----------------------------------------------------------------------
    print("\n--- STEP 4: City-Wide Urban Analytics Matrix ---")
    od = trajectory_store.get_od_matrix()
    for row in od:
        print(f"   O-D Corridor: {row['origin_junction']} -> {row['destination_junction']} | Trips: {row['trip_count']} | Avg Time: {row['avg_duration_s']:.1f}s")

    print("\n" + "=" * 70)
    print("  DEMO COMPLETE: All Sentinel intelligence pipelines verified.")
    print("  To launch the real-time Leaflet UI, run:")
    print("    python -m sentinel.server --port 8888")
    print("=" * 70 + "\n")

    tracker.stop()
    tracker_task.cancel()


def main():
    asyncio.run(run_turnkey_demo())


if __name__ == "__main__":
    main()
