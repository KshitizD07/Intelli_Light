"""
sentinel/tracker/tracker.py
============================
TrackerManager: manages per-vehicle VehicleTrace instances.

Consumes "sighting" events from the EventBus and maintains
a live dict of active traces. Emits traces to the AnomalyEngine.

No Intelli-Light source file is imported or modified here.
"""

import asyncio
import logging
from typing import Dict, Optional

from sentinel.tracker.vehicle_trace import VehicleTrace, Sighting
from sentinel.ingestion.event_bus import EventBus
from sentinel.registry import FlaggedVehicleRegistry
from sentinel.ingestion.sumo_injector import CameraGrid

logger = logging.getLogger(__name__)


class TrackerManager:
    """
    Listens for sighting events on the EventBus and maintains live
    per-vehicle VehicleTrace objects.

    Also enriches sightings with geo coordinates from the camera grid.

    Args:
        bus:          EventBus to consume sighting events from.
        registry:     FlaggedVehicleRegistry for flagging vehicle traces.
        camera_grid:  CameraGrid for junction -> (lat, lng) lookup.
        on_update:    Optional async callback called with (trace) on each update.
    """

    def __init__(
        self,
        bus: EventBus,
        registry: FlaggedVehicleRegistry,
        camera_grid: CameraGrid,
        on_update=None,
    ):
        self.bus = bus
        self.registry = registry
        self.camera_grid = camera_grid
        self.on_update = on_update   # async callable(trace: VehicleTrace)

        self._traces: Dict[str, VehicleTrace] = {}
        self._running = False

    # ------------------------------------------------------------------
    # Main async loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """
        Consume events from the EventBus forever.
        Handles "sighting" and "alert" event types.
        """
        self._running = True
        logger.info("[TrackerManager] Started")

        while self._running:
            try:
                event = await asyncio.wait_for(self.bus.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            etype = event.get("type")
            if etype == "sighting":
                await self._handle_sighting(event)
            elif etype == "alert":
                self._handle_alert(event)
            # Other event types (anomaly, intercept_request) are handled
            # by other consumers; we just ignore them here.

            self.bus.task_done()

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def _handle_sighting(self, event: dict) -> None:
        plate = event["plate"]
        junction_id = event["junction_id"]
        timestamp = event["timestamp"]
        confidence = event.get("confidence", 1.0)
        extra = event.get("extra", {})

        cam_info = self.camera_grid.camera_info(junction_id) or {}

        sighting = Sighting(
            junction_id=junction_id,
            timestamp=timestamp,
            speed_mps=extra.get("speed_mps", 0.0),
            confidence=confidence,
            lat=cam_info.get("lat", 0.0),
            lng=cam_info.get("lng", 0.0),
        )

        if plate not in self._traces:
            self._traces[plate] = VehicleTrace(plate)
            self._traces[plate].is_flagged = self.registry.is_flagged(plate)
            if self._traces[plate].is_flagged:
                logger.info(f"[Tracker] New trace for FLAGGED vehicle: {plate}")
            else:
                logger.debug(f"[Tracker] New trace: {plate}")

        trace = self._traces[plate]
        trace.add_sighting(sighting)

        logger.debug(
            f"[Tracker] {plate} | junction={junction_id} | "
            f"t={timestamp:.1f}s | sightings={len(trace.sightings)}"
        )

        if self.on_update:
            await self.on_update(trace)

    def _handle_alert(self, event: dict) -> None:
        plate = event["plate"]
        if plate in self._traces:
            self._traces[plate].is_flagged = True
        logger.warning(
            f"[Tracker] Alert received for {plate}: {event.get('extra', {}).get('reason', '')}"
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_trace(self, plate: str) -> Optional[VehicleTrace]:
        return self._traces.get(plate.upper().strip())

    def all_traces(self) -> Dict[str, VehicleTrace]:
        return dict(self._traces)

    def flagged_traces(self) -> Dict[str, VehicleTrace]:
        return {p: t for p, t in self._traces.items() if t.is_flagged}

    @property
    def active_count(self) -> int:
        return len(self._traces)
