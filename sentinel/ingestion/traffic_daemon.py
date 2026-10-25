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
from sentinel.intercept.tactical_bridge import TacticalGuidanceBridge
from sentinel.tracker.road_snapper import RoadSnapper
from sentinel.config import SUMO_NET_FILE

logger = logging.getLogger(__name__)


@dataclass
class SimulatedVehicle:
    plate: str
    route: List[str]            # list of junction IDs
    current_index: int = 0
    speed_mps: float = 12.0     # ~43 km/h
    base_speed_mps: float = 12.0 # Cruise speed
    progress: float = 0.0       # 0.0 to 1.0 between current and next node
    lat: float = 0.0
    lng: float = 0.0
    is_flagged: bool = False
    is_halted: bool = False
    halt_reason: str = ""
    guidance_status: str = "NORMAL"
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
        road_snapper: Optional[RoadSnapper] = None,
        tick_interval_s: float = 1.0,
    ):
        self.bus = bus
        self.registry = registry
        self.camera_grid = camera_grid
        self.gnn_bridge = gnn_bridge
        self.orchestrator = orchestrator
        self.tactical_bridge = TacticalGuidanceBridge(orchestrator=orchestrator) if orchestrator else None
        self.road_snapper = road_snapper or RoadSnapper(SUMO_NET_FILE)
        self.tick_interval_s = tick_interval_s

        self.vehicles: Dict[str, SimulatedVehicle] = {}
        self._camera_junctions = list(camera_grid.cameras.keys())
        self._running = False
        self._sim_time = 0.0
        self._path_cache: Dict[Tuple[str, str], Tuple[List[Tuple[float, float]], List[float], float]] = {}
        self._last_camera_trigger: Dict[Tuple[str, str], float] = {}

        self._init_fleet()

    def _get_path_info(self, from_node: str, to_node: str) -> Tuple[List[Tuple[float, float]], List[float], float]:
        """
        Returns (points, cumulative_distances_m, total_distance_m) along the road network.
        Points are [(lng, lat), ...].
        """
        cache_key = (from_node, to_node)
        if cache_key in self._path_cache:
            return self._path_cache[cache_key]

        coords = self.road_snapper.get_route_geometry([from_node, to_node])
        if not coords or len(coords) < 2:
            cam_curr = self.camera_grid.camera_info(from_node) or {}
            cam_next = self.camera_grid.camera_info(to_node) or {}
            c1 = (cam_curr.get("lng", 80.95), cam_curr.get("lat", 26.85))
            c2 = (cam_next.get("lng", 80.95), cam_next.get("lat", 26.85))
            coords = [c1, c2]

        cum_dists = [0.0]
        total = 0.0
        for i in range(len(coords) - 1):
            lng1, lat1 = coords[i]
            lng2, lat2 = coords[i + 1]
            dx = (lng2 - lng1) * 99300.0  # meters per deg lon at ~26.85 N
            dy = (lat2 - lat1) * 110800.0 # meters per deg lat
            seg_len = math.hypot(dx, dy)
            total += max(0.5, seg_len)
            cum_dists.append(total)

        if total <= 0.0:
            total = 100.0
            cum_dists[-1] = total

        res = (coords, cum_dists, total)
        self._path_cache[cache_key] = res
        return res

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
            base_speed_mps=speed,
            lat=start_cam.get("lat", 26.85),
            lng=start_cam.get("lng", 80.95),
            is_flagged=is_flagged,
            anomaly_pattern=anomaly_pattern,
        )
        self.vehicles[plate] = v

        # Emit initial checkpoint sighting & alert at spawn
        s_event = sighting_event(
            plate=plate,
            junction_id=route[0],
            timestamp=self._sim_time,
            confidence=0.98,
            speed_mps=speed,
        )
        self.bus.put_nowait(s_event)
        self._last_camera_trigger[(plate, route[0])] = self._sim_time

        if is_flagged and self.registry.is_flagged(plate):
            entry = self.registry.lookup(plate)
            reason = entry.flag_reason if entry else "Flagged Vehicle"
            authority = entry.authority if entry else "Central Intelligence"
            a_event = alert_event(
                plate=plate,
                junction_id=route[0],
                timestamp=self._sim_time,
                reason=f"OPTICAL ALPR HIT: {reason}",
                authority=authority,
            )
            a_event["extra"]["lat"] = v.lat
            a_event["extra"]["lng"] = v.lng
            a_event["extra"]["distance_m"] = 0.0
            self.bus.put_nowait(a_event)

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

            # 1. Closed-Loop Tactical Reaction & Kinematic Deceleration
            if self.tactical_bridge:
                target_v, guidance_status = self.tactical_bridge.get_kinematic_target_speed(
                    plate=v.plate,
                    next_junction=next_node,
                    progress=v.progress,
                    base_speed_mps=v.base_speed_mps,
                )
                v.guidance_status = guidance_status

                # Physical deceleration (brake rate ~2.5 m/s^2)
                if v.speed_mps > target_v:
                    brake_step = 2.5 * self.tick_interval_s
                    v.speed_mps = max(target_v, round(v.speed_mps - brake_step, 2))
                elif v.speed_mps < target_v:
                    accel_step = 1.8 * self.tick_interval_s
                    v.speed_mps = min(target_v, round(v.speed_mps + accel_step, 2))

                # Check queue containment halt
                is_target = (
                    next_node in active_overrides
                    and active_overrides[next_node].get("target_plate") == plate
                )
                if is_target and v.progress >= 0.85:
                    v.is_halted = True
                    v.speed_mps = 0.0
                    v.halt_reason = f"HALTED BY RED-WALL INTERCEPT AT {next_node}"
                else:
                    if v.is_halted and not is_target:
                        v.is_halted = False
                        v.halt_reason = ""
            else:
                if (
                    self.orchestrator
                    and next_node in active_overrides
                    and active_overrides[next_node].get("target_plate") == plate
                ):
                    if v.progress >= 0.85 and not v.is_halted:
                        v.is_halted = True
                        v.speed_mps = 0.0
                        v.halt_reason = f"HALTED BY RED-WALL INTERCEPT AT {next_node}"
                    if v.is_halted:
                        v.speed_mps = 0.0
                else:
                    if v.is_halted:
                        v.is_halted = False
                        v.halt_reason = ""

            # 2. Advance movement along physical road polyline
            coords, cum_dists, dist_m = self._get_path_info(current_node, next_node)
            if v.is_halted or v.speed_mps <= 0.0:
                step_distance = 0.0
                progress_delta = 0.0
            else:
                step_distance = v.speed_mps * self.tick_interval_s
                progress_delta = step_distance / dist_m
                v.progress += progress_delta

            # Interpolate position along physical street curves
            clamped_progress = min(1.0, max(0.0, v.progress))
            target_dist = clamped_progress * dist_m

            seg_idx = 0
            for i in range(len(cum_dists) - 1):
                if cum_dists[i] <= target_dist <= cum_dists[i + 1]:
                    seg_idx = i
                    break
                if target_dist > cum_dists[i + 1]:
                    seg_idx = i

            p1 = coords[seg_idx]
            p2 = coords[min(seg_idx + 1, len(coords) - 1)]
            seg_len = cum_dists[min(seg_idx + 1, len(cum_dists) - 1)] - cum_dists[seg_idx]
            seg_ratio = (target_dist - cum_dists[seg_idx]) / seg_len if seg_len > 1e-4 else 0.0

            v.lng = round(p1[0] + (p2[0] - p1[0]) * seg_ratio, 6)
            v.lat = round(p1[1] + (p2[1] - p1[1]) * seg_ratio, 6)

            # 3. Continuous Optical Proximity & ALPR Detection
            for cam_id, cam_info in self.camera_grid.cameras.items():
                cam_lat = cam_info.get("lat")
                cam_lng = cam_info.get("lng")
                if cam_lat is None or cam_lng is None:
                    continue

                dx = (v.lng - cam_lng) * 99300.0
                dy = (v.lat - cam_lat) * 110800.0
                dist_m = math.hypot(dx, dy)

                if dist_m <= 65.0:  # Within optical camera cone
                    last_trigger = self._last_camera_trigger.get((v.plate, cam_id), -999.0)
                    if (self._sim_time - last_trigger) >= 15.0:  # Debounce per camera
                        self._last_camera_trigger[(v.plate, cam_id)] = self._sim_time

                        # Optical sighting
                        conf = round(random.uniform(0.94, 0.99), 2)
                        s_event = sighting_event(
                            plate=v.plate,
                            junction_id=cam_id,
                            timestamp=self._sim_time,
                            confidence=conf,
                            speed_mps=v.speed_mps,
                        )
                        self.bus.put_nowait(s_event)

                        # Threat alert if flagged
                        if self.registry.is_flagged(v.plate):
                            entry = self.registry.lookup(v.plate)
                            reason = entry.flag_reason if entry else "Flagged Vehicle"
                            authority = entry.authority if entry else "Central Intelligence"
                            a_event = alert_event(
                                plate=v.plate,
                                junction_id=cam_id,
                                timestamp=self._sim_time,
                                reason=f"OPTICAL ALPR HIT: {reason}",
                                authority=authority,
                            )
                            a_event["extra"]["lat"] = cam_lat
                            a_event["extra"]["lng"] = cam_lng
                            a_event["extra"]["distance_m"] = round(dist_m, 1)
                            self.bus.put_nowait(a_event)
                            logger.warning(
                                f"[TrafficDaemon] OPTICAL HIT: Camera {cam_id[:16]} detected {v.plate} ({reason}, {dist_m:.1f}m)"
                            )

            # 4. Check route checkpoint arrival
            if v.progress >= 1.0:
                v.current_index = next_index
                v.progress = 0.0

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
                "guidance_status": v.guidance_status,
                "current_junction": v.route[v.current_index],
            }
            for v in self.vehicles.values()
        ]
