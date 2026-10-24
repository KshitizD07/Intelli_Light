"""
sentinel/ingestion/sumo_injector.py
=====================================
SUMO TraCI sighting injector for Sentinel.

Launches its own SUMO instance (separate from Intelli-Light's) using
the Lucknow map, iterates the simulation, and emits a "sighting" event
whenever a vehicle passes within CAMERA_RADIUS_M of a junction that has
a virtual camera assigned.

Key design:
- Reads Intelli-Light's SUMO files (read-only) - does NOT modify them.
- Runs as an asyncio coroutine: yields control back to the event loop
  between steps so Sentinel's other components run concurrently.
- Plates are the SUMO vehicle IDs in SUMO mode (perfect accuracy).
  In production, they come from the ALPR pipeline instead.

Usage:
    injector = SUMOInjector(event_bus, registry)
    await injector.run()
"""

import os
import sys
import asyncio
import logging
import subprocess
import math
from typing import Dict, List, Optional, Set

from sentinel.config import (
    SUMO_BINARY,
    SUMO_NET_FILE,
    SUMO_CFG_FILE,
    SUMO_PORT,
    SUMO_STEP_LENGTH,
    SUMO_MAX_STEPS,
    CAMERA_RADIUS_M,
)
from sentinel.ingestion.event_bus import EventBus, sighting_event, alert_event
from sentinel.registry import FlaggedVehicleRegistry
from sentinel.tracker.road_snapper import get_shared_sumo_net

logger = logging.getLogger(__name__)

# Guard: traci is always available (it's in the venv)
import traci
import sumolib


class CameraGrid:
    """
    Parses the SUMO network and places virtual cameras at every
    traffic-light controlled junction. Exposes a fast radius-check.
    """

    def __init__(self, net_file: str):
        self._net = get_shared_sumo_net(net_file)
        if self._net is None:
            raise FileNotFoundError(
                f"SUMO network file not found or invalid: {net_file}\n"
                "Make sure the Lucknow map is present at simulation/lucknow_map/"
            )
        self.cameras: Dict[str, Dict] = {}  # junction_id -> {x, y, lng, lat}
        self._build()

    def _build(self):
        """Place a camera at every traffic-light junction."""
        tls_ids: Set[str] = {tls.getID() for tls in self._net.getTrafficLights()}
        count = 0
        for node in self._net.getNodes():
            node_id = node.getID()
            if node_id not in tls_ids:
                continue
            x, y = node.getCoord()
            try:
                lng, lat = self._net.convertXY2LonLat(x, y)
            except Exception:
                lng, lat = x / 1e5, y / 1e5  # fallback rough conversion
            self.cameras[node_id] = {"x": x, "y": y, "lng": round(lng, 6), "lat": round(lat, 6)}
            count += 1
        logger.info(f"[CameraGrid] {count} cameras placed at TLS junctions")

    def nearest_camera(
        self, vx: float, vy: float, radius_m: float = CAMERA_RADIUS_M
    ) -> Optional[str]:
        """
        Return the ID of the nearest camera junction within radius_m,
        or None if no camera is close enough.
        Fast O(N) scan - acceptable for city-scale grids in sim.
        """
        best_id = None
        best_dist = radius_m
        for jid, cam in self.cameras.items():
            dist = math.hypot(cam["x"] - vx, cam["y"] - vy)
            if dist < best_dist:
                best_dist = dist
                best_id = jid
        return best_id

    def camera_info(self, junction_id: str) -> Optional[Dict]:
        return self.cameras.get(junction_id)


class SUMOInjector:
    """
    Drives a standalone SUMO simulation and converts vehicle positions
    into plate sighting events on the EventBus.

    Args:
        bus:      Sentinel EventBus to push sighting events onto.
        registry: FlaggedVehicleRegistry for immediate blacklist lookup.
        net_file: Path to lucknow.net.xml (default from config).
        cfg_file: Path to lucknow.sumocfg (default from config).
        max_steps: Max simulation steps before injector stops.
        use_gui:   Set True to open SUMO GUI for visual demo.
    """

    def __init__(
        self,
        bus: EventBus,
        registry: FlaggedVehicleRegistry,
        net_file: str = SUMO_NET_FILE,
        cfg_file: str = SUMO_CFG_FILE,
        max_steps: int = SUMO_MAX_STEPS,
        use_gui: bool = False,
    ):
        self.bus = bus
        self.registry = registry
        self.net_file = net_file
        self.cfg_file = cfg_file
        self.max_steps = max_steps
        self.use_gui = use_gui
        self.binary = "sumo-gui" if use_gui else SUMO_BINARY

        self._camera_grid: Optional[CameraGrid] = None
        self._step = 0
        self._running = False

        # Track which vehicles have been seen at which junction (to avoid
        # spamming sighting events for the same vehicle in consecutive ticks)
        self._last_sighted: Dict[str, str] = {}  # vehicle_id -> last junction_id

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _resolve_binary(self) -> str:
        """Locates the SUMO executable across PATH and standard installation trees."""
        import shutil
        target = self.binary
        if shutil.which(target):
            return target

        candidates = [
            os.path.join(os.environ.get("SUMO_HOME", ""), "bin", f"{target}.exe"),
            os.path.join(r"C:\Program Files\Eclipse\Sumo\bin", f"{target}.exe"),
            os.path.join(r"C:\Program Files (x86)\Eclipse\Sumo\bin", f"{target}.exe"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                logger.info(f"[SUMOInjector] Resolved binary at: {c}")
                return c

        raise FileNotFoundError(
            f"SUMO executable '{target}' not found in PATH or standard directories.\n"
            "To run without a local SUMO installation, use turnkey demo mode:\n"
            "  python main.py sentinel-demo\n"
            "or start the web server with live traffic daemon:\n"
            "  python main.py sentinel-web"
        )

    def _start_sumo(self) -> None:
        """Launch SUMO via subprocess and connect TraCI."""
        bin_path = self._resolve_binary()
        sumo_cmd = [
            bin_path,
            "-c", self.cfg_file,
            "--remote-port", str(SUMO_PORT),
            "--step-length", str(SUMO_STEP_LENGTH),
            "--no-warnings", "true",
            "--no-step-log", "true",
            "--quit-on-end", "true",
        ]
        logger.info(f"[SUMOInjector] Starting SUMO: {' '.join(sumo_cmd)}")
        self._sumo_proc = subprocess.Popen(
            sumo_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Give SUMO time to open the TraCI port
        import time; time.sleep(2.0)
        traci.init(SUMO_PORT)
        logger.info(f"[SUMOInjector] TraCI connected on port {SUMO_PORT}")

    def _stop_sumo(self) -> None:
        """Gracefully close TraCI and terminate SUMO."""
        try:
            traci.close()
        except Exception:
            pass
        try:
            self._sumo_proc.terminate()
            self._sumo_proc.wait(timeout=5)
        except Exception:
            pass
        logger.info("[SUMOInjector] SUMO stopped")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """
        Main async loop. Starts SUMO, iterates steps, emits sighting
        events, yields control back to the event loop every tick.
        """
        self._camera_grid = CameraGrid(self.net_file)

        try:
            self._start_sumo()
            self._running = True
            logger.info(f"[SUMOInjector] Running up to {self.max_steps} steps")

            while self._running and self._step < self.max_steps:
                sim_time = traci.simulation.getTime()
                vehicle_ids: List[str] = traci.vehicle.getIDList()

                for vid in vehicle_ids:
                    try:
                        vx, vy = traci.vehicle.getPosition(vid)
                    except traci.exceptions.TraCIException:
                        continue  # vehicle teleported or left between calls

                    junction_id = self._camera_grid.nearest_camera(vx, vy)
                    if junction_id is None:
                        continue  # not near any camera

                    # Debounce: skip if same vehicle at same junction as last tick
                    if self._last_sighted.get(vid) == junction_id:
                        continue
                    self._last_sighted[vid] = junction_id

                    try:
                        speed = traci.vehicle.getSpeed(vid)
                        lane  = traci.vehicle.getLaneID(vid)
                    except traci.exceptions.TraCIException:
                        speed, lane = 0.0, ""

                    # In SUMO mode the vehicle ID is used directly as the plate
                    plate = vid.upper()

                    event = sighting_event(
                        plate=plate,
                        junction_id=junction_id,
                        timestamp=sim_time,
                        confidence=1.0,   # perfect in sim mode
                        speed_mps=speed,
                        lane_id=lane,
                    )
                    self.bus.put_nowait(event)

                    # Immediate blacklist hit check
                    if self.registry.is_flagged(plate):
                        entry = self.registry.lookup(plate)
                        alert = alert_event(
                            plate=plate,
                            junction_id=junction_id,
                            timestamp=sim_time,
                            reason=f"BLACKLIST HIT: {entry.flag_reason}",
                            authority=entry.authority,
                        )
                        self.bus.put_nowait(alert)
                        logger.warning(
                            f"[ALERT] Blacklisted vehicle spotted: {plate} "
                            f"at {junction_id} t={sim_time:.1f}s"
                        )

                traci.simulationStep()
                self._step += 1

                # Yield to the asyncio event loop every tick
                await asyncio.sleep(0)

        except Exception as e:
            logger.error(f"[SUMOInjector] Fatal error at step {self._step}: {e}", exc_info=True)
            raise
        finally:
            self._running = False
            self._stop_sumo()

    def stop(self) -> None:
        """Signal the run loop to stop after the current step."""
        self._running = False

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def steps_completed(self) -> int:
        return self._step

    @property
    def is_running(self) -> bool:
        return self._running
