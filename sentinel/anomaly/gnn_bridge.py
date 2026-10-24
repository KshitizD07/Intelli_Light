"""
sentinel/anomaly/gnn_bridge.py
===============================
GNN Congestion Telemetry Bridge.

Extracts real-time queue lengths, wait pressures, and congestion levels
from the road network so the AnomalyEngine can verify whether a route detour
was rational (due to traffic jams) or suspicious (empty roads bypassed).
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class GNNTelemetryBridge:
    """
    Supplies live congestion metrics per intersection node.
    """

    def __init__(self):
        self._cached_queue_lengths: Dict[str, int] = {}
        self._cached_pressures: Dict[str, float] = {}

    def update_telemetry(self, junction_id: str, queue_length: int, pressure: float = 0.0):
        self._cached_queue_lengths[junction_id] = max(0, queue_length)
        self._cached_pressures[junction_id] = pressure

    def get_queue_length(self, junction_id: str) -> int:
        return self._cached_queue_lengths.get(junction_id, 0)

    def get_pressure(self, junction_id: str) -> float:
        return self._cached_pressures.get(junction_id, 0.0)

    def is_congested(self, junction_id: str, queue_threshold: int = 15) -> bool:
        """True if the intersection queue exceeds normal operational bounds."""
        return self.get_queue_length(junction_id) >= queue_threshold

    def calculate_detour_justification(
        self, bypassed_junctions: list[str], detour_ratio: float
    ) -> float:
        """
        Determines how justified a detour is based on bypassed intersection congestion.
        Returns justification multiplier in [0.0, 1.0]:
          - 1.0 = Completely justified (the direct route was heavily jammed).
          - 0.0 = Completely unjustified (the direct route was clear; high suspicion).
        """
        if not bypassed_junctions:
            return 0.0

        max_queue = max([self.get_queue_length(j) for j in bypassed_junctions] + [0])

        if max_queue >= 25:
            # Severe traffic jam on direct route - detour makes sense
            return 1.0
        elif max_queue >= 10:
            # Moderate traffic
            return 0.5
        else:
            # Completely clear route bypassed without reason
            return 0.0
