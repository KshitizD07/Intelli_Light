"""
sentinel/ingestion/traffic_daemon.py
====================================
Continuous Kinematic Traffic Simulation Daemon.

Provides a live, realistic municipal vehicle fleet driving on the physical
Lucknow road network in real-time. Eliminates static dashboards by supplying
continuous camera detections, queue dynamics, and reactive vehicle behaviors.

Key Features:
- 20-vehicle simulated fleet traversing topological road paths.
- Incorporates active actors (normal commuters, surveillance targets, stolen vehicles).
- Closed-loop physical reaction: When an intercept is triggered via InterceptOrchestrator,
  target vehicles reaching the red-wall perimeter actually halt, simulating gridlock capture.
- Dynamically updates GNNTelemetryBridge queue lengths based on local vehicle clusters.
"""

import math
import random
import asyncio
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field

from sentinel.ingestion.event_bus import EventBus, sighting_event, alert_event
from sentinel.registry import FlaggedVehicleRegistry
from sentinel.ingestion.sumo_injector import CameraGrid
from sentinel.anomaly.gnn_bridge import GNNTelemetryBridge
from sentinel.intercept.orchestrator import InterceptOrchestrator

logger = logging.getLogger(__name__)


@dataclass
class SimulatedVehicle:
    plate: str
    route: List[str]            # list of junction IDs
    current_index: int = 0
    speed_mps: float = 12.0     # ~43 km/h
    progress: float = 0.0       # 0.0 to 1.0 between current and next node
    lat: float = 0.0
    lng: float = 0.0
    is_flagged: bool = False
    is_halted: bool = False
    halt_reason: str = ""
    anomaly_pattern: Optional[str] = None  # 'detour' | 'loop' | None


class TrafficSimulationDaemon:
    """
    Simulates continuous multi-vehicle traffic movement on the road graph.
    """

    def __init__(
        self,
        bus: EventBus,
        registry: FlaggedVehicleRegistry,
        camera_grid: CameraGrid,
        gnn_bridge: Optional[GNNTelemetryBridge] = None,
        orchestrator: Optional[InterceptOrchestrator] = None,
        tick_interval_s: float = 1.0,
    ):
        self.bus = bus
        self.registry = registry
        self.camera_grid = camera_grid
        self.gnn_bridge = gnn_bridge
        self.orchestrator = orchestrator
        self.tick_interval_s = tick_interval_s

        self.vehicles: Dict[str, SimulatedVehicle] = {}
        self._camera_junctions = list(camera_grid.cameras.keys())
        self._running = False
        self._sim_time = 0.0

        self._init_fleet()

    def _init_fleet(self):
        """Spawns an authentic mix of normal commuters and flagged surveillance targets."""
        if not self._camera_junctions:
            logger.warning("[TrafficDaemon] No camera junctions available.")
            return

        # 1. Flagged Stolen Vehicle (Key target for intercept demo)
        self._spawn_vehicle(
            plate="UP32XY9999",
            start_junc=self._camera_junctions[0],
            is_flagged=True,
            speed=16.5,
        )

        # 2. Flagged Surveillance Target (Anomalous detour actor)
        self._spawn_vehicle(
            plate="UP32AB1234",
            start_junc=self._camera_junctions[1 % len(self._camera_junctions)],
            is_flagged=True,
            anomaly_pattern="loop",
            speed=11.0,
        )

        # 3. Regular city commuters
        standard_plates = [
            "DL01AB9999", "UP32BC1001", "UP32EF4520", "MH12XY7841",
            "KA05MN2314", "UP32RT8890", "HR26BC3310", "UP32LK5500",
            "DL04CD8210", "UP41AA6622", "UP32GH9012", "WB02JK3456",
            "UP32ZZ1122", "DL08MN4433", "UP32PQ7788", "MH01AB5566",
        ]

        for i, plate in enumerate(standard_plates):
            start_j = self._camera_junctions[i % len(self._camera_junctions)]
            self._spawn_vehicle(
                plate=plate,
                start_junc=start_j,
                is_flagged=False,
                speed=random.uniform(9.0, 14.5),
            )

        logger.info(f"[TrafficDaemon] Fleet initialized: {len(self.vehicles)} active vehicles.")

    def _spawn_vehicle(
        self,
        plate: str,
        start_junc: str,
        is_flagged: bool,
        speed: float = 12.0,
        anomaly_pattern: Optional[str] = None,
    ):
        # Build an initial cyclic or linear route through available cameras
        juncs = list(self._camera_junctions)
        start_idx = juncs.index(start_junc) if start_junc in juncs else 0
        ordered = juncs[start_idx:] + juncs[:start_idx]

        if anomaly_pattern == "loop":
            # Intentional loop: J1 -> J2 -> J1 -> J2 -> J1
            if len(ordered) >= 2:
                route = [ordered[0], ordered[1], ordered[0], ordered[1], ordered[0]]
            else:
                route = ordered * 2
        else:
            route = ordered + [ordered[0]]

        start_cam = self.camera_grid.camera_info(route[0]) or {}
        v = SimulatedVehicle(
            plate=plate,
            route=route,
            current_index=0,
            speed_mps=speed,
            lat=start_cam.get("lat", 26.85),
            lng=start_cam.get("lng", 80.95),
            is_flagged=is_flagged,
            anomaly_pattern=anomaly_pattern,
        )
        self.vehicles[plate] = v

    async def run(self):
        """Continuous simulation stepping loop."""
        self._running = True
        logger.info("[TrafficDaemon] Traffic engine started.")

        while self._running:
            self._sim_time += self.tick_interval_s
            await self._step_simulation()
            await asyncio.sleep(self.tick_interval_s)

    def stop(self):
        self._running = False

    async def _step_simulation(self):
        active_overrides = self.orchestrator.get_signal_overrides() if self.orchestrator else {}
        junction_counts: Dict[str, int] = {j: 0 for j in self._camera_junctions}

        for plate, v in list(self.vehicles.items()):
            current_node = v.route[v.current_index]
            next_index = (v.current_index + 1) % len(v.route)
            next_node = v.route[next_index]

            # 1. Closed-Loop Reaction: Check if next junction is locked by an intercept
            if (
                self.orchestrator
                and next_node in active_overrides
                and active_overrides[next_node].get("target_plate") == plate
            ):
                if v.progress >= 0.85 and not v.is_halted:
                    v.is_halted = True
                    v.halt_reason = f"HALTED BY RED-WALL INTERCEPT AT {next_node}"
                    logger.warning(
                        f"[TrafficDaemon] TARGET VEHICLE {plate} TRAPPED & HALTED at {next_node}"
                    )
                if v.is_halted:
                    continue  # Frozen in traffic
            else:
                if v.is_halted:
                    v.is_halted = False
                    v.halt_reason = ""

            # 2. Advance movement
            cam_curr = self.camera_grid.camera_info(current_node) or {}
            cam_next = self.camera_grid.camera_info(next_node) or {}

            # Approximate physical distance in metres
            lat1, lng1 = cam_curr.get("lat", 26.85), cam_curr.get("lng", 80.95)
            lat2, lng2 = cam_next.get("lat", 26.85), cam_next.get("lng", 80.95)

            # Haversine distance
            dist_m = max(100.0, math.hypot(lat2 - lat1, lng2 - lng1) * 111_000)
            step_distance = v.speed_mps * self.tick_interval_s
            progress_delta = step_distance / dist_m

            v.progress += progress_delta

            # Interpolate position
            v.lat = lat1 + (lat2 - lat1) * min(1.0, v.progress)
            v.lng = lng1 + (lng2 - lng1) * min(1.0, v.progress)

            # 3. Check junction arrival
            if v.progress >= 1.0:
                v.current_index = next_index
                v.progress = 0.0
                arrived_junction = v.route[v.current_index]

                # Emit camera sighting
                event = sighting_event(
                    plate=v.plate,
                    junction_id=arrived_junction,
                    timestamp=self._sim_time,
                    confidence=0.96,
                    speed_mps=v.speed_mps,
                )
                self.bus.put_nowait(event)

                # Blacklist hit alert
                if self.registry.is_flagged(v.plate):
                    entry = self.registry.lookup(v.plate)
                    reason = entry.flag_reason if entry else "Flagged Vehicle"
                    self.bus.put_nowait(alert_event(
                        plate=v.plate,
                        junction_id=arrived_junction,
                        timestamp=self._sim_time,
                        reason=f"SURVEILLANCE HIT: {reason}",
                        authority=entry.authority if entry else "Central Ops",
                    ))

            # Count vehicles near junction for GNN queue telemetry
            nearest_j = current_node if v.progress < 0.5 else next_node
            junction_counts[nearest_j] = junction_counts.get(nearest_j, 0) + 1

        # 4. Push dynamic queue telemetry into GNN bridge
        if self.gnn_bridge:
            for jid, count in junction_counts.items():
                self.gnn_bridge.update_telemetry(jid, queue_length=count, pressure=count * 0.1)

    def get_fleet_telemetry(self) -> List[Dict]:
        """Provides instant snapshot for web visualizer."""
        return [
            {
                "plate": v.plate,
                "lat": round(v.lat, 6),
                "lng": round(v.lng, 6),
                "speed_mps": round(v.speed_mps, 1),
                "is_flagged": v.is_flagged,
                "is_halted": v.is_halted,
                "halt_reason": v.halt_reason,
                "current_junction": v.route[v.current_index],
            }
            for v in self.vehicles.values()
        ]
