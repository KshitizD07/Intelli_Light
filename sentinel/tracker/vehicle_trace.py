"""
sentinel/tracker/vehicle_trace.py
===================================
VehicleTrace: per-vehicle movement log.

Stores the full ordered sequence of (junction_id, timestamp, speed)
tuples for a single plate. Provides helpers for path analysis used
by the anomaly engine.

No Intelli-Light source file is imported or modified here.
"""

import math
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class Sighting:
    """A single camera sighting of a vehicle."""
    junction_id: str
    timestamp: float       # SUMO sim time or wall clock (seconds)
    speed_mps: float = 0.0
    confidence: float = 1.0
    lat: float = 0.0
    lng: float = 0.0


class VehicleTrace:
    """
    Ordered trajectory log for one vehicle plate.

    Thread-safety: caller must serialize access if using from multiple
    coroutines. In Sentinel's single-thread async model this is safe as-is.
    """

    def __init__(self, plate: str):
        self.plate: str = plate.upper().strip()
        self.sightings: List[Sighting] = []
        self.anomaly_score: float = 0.0
        self.is_flagged: bool = False
        self.intercept_active: bool = False

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_sighting(self, sighting: Sighting) -> None:
        """Append a new sighting. Maintains chronological order."""
        self.sightings.append(sighting)

    # ------------------------------------------------------------------
    # Path queries
    # ------------------------------------------------------------------

    @property
    def first_seen(self) -> Optional[Sighting]:
        return self.sightings[0] if self.sightings else None

    @property
    def last_seen(self) -> Optional[Sighting]:
        return self.sightings[-1] if self.sightings else None

    @property
    def junction_sequence(self) -> List[str]:
        """Ordered list of junction IDs visited (with consecutive duplicates collapsed)."""
        if not self.sightings:
            return []
        result = [self.sightings[0].junction_id]
        for s in self.sightings[1:]:
            if s.junction_id != result[-1]:
                result.append(s.junction_id)
        return result

    @property
    def total_time_s(self) -> float:
        """Elapsed time from first to last sighting (seconds)."""
        if len(self.sightings) < 2:
            return 0.0
        return self.sightings[-1].timestamp - self.sightings[0].timestamp

    @property
    def unique_junctions(self) -> int:
        return len(set(s.junction_id for s in self.sightings))

    def inter_sighting_gap(self, idx: int) -> float:
        """
        Time gap between sighting[idx] and sighting[idx+1].
        Returns 0.0 if idx is out of range.
        """
        if idx < 0 or idx >= len(self.sightings) - 1:
            return 0.0
        return self.sightings[idx + 1].timestamp - self.sightings[idx].timestamp

    def max_gap_s(self) -> float:
        """Longest gap between any two consecutive sightings."""
        if len(self.sightings) < 2:
            return 0.0
        return max(
            self.inter_sighting_gap(i) for i in range(len(self.sightings) - 1)
        )

    def loop_detected(self, min_visits: int = 3) -> Tuple[bool, str]:
        """
        Detect if the vehicle has revisited a junction >= min_visits times.
        Returns (True, junction_id) or (False, "").
        """
        from collections import Counter
        counts = Counter(s.junction_id for s in self.sightings)
        for jid, count in counts.most_common():
            if count >= min_visits:
                return True, jid
        return False, ""

    def speed_on_hop(self, idx: int) -> Optional[float]:
        """
        Estimate average speed (m/s) between sighting[idx] and sighting[idx+1]
        using geo distance divided by time delta.
        Returns None if coordinates are not set or time delta is zero.
        """
        if idx < 0 or idx >= len(self.sightings) - 1:
            return None
        a, b = self.sightings[idx], self.sightings[idx + 1]
        dt = b.timestamp - a.timestamp
        if dt <= 0:
            return None
        if a.lat == 0.0 and a.lng == 0.0:
            return None
        # Haversine distance in metres
        R = 6_371_000.0
        phi1, phi2 = math.radians(a.lat), math.radians(b.lat)
        dphi = math.radians(b.lat - a.lat)
        dlam = math.radians(b.lng - a.lng)
        ha = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        dist_m = 2 * R * math.asin(math.sqrt(ha))
        return dist_m / dt

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        return {
            "plate": self.plate,
            "sightings": len(self.sightings),
            "unique_junctions": self.unique_junctions,
            "first_seen_junction": self.first_seen.junction_id if self.first_seen else None,
            "last_seen_junction": self.last_seen.junction_id if self.last_seen else None,
            "total_time_s": round(self.total_time_s, 1),
            "anomaly_score": round(self.anomaly_score, 3),
            "is_flagged": self.is_flagged,
            "intercept_active": self.intercept_active,
        }

    def __repr__(self) -> str:
        return (
            f"VehicleTrace(plate={self.plate!r}, "
            f"sightings={len(self.sightings)}, "
            f"anomaly={self.anomaly_score:.3f})"
        )
