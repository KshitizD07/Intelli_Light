"""
sentinel/anomaly/scorer.py
===========================
Anomaly Engine: scores vehicle traces for suspicious behaviour.

Runs as an async callback attached to the TrackerManager's on_update hook.
Every time a trace is updated, the scorer re-evaluates it and updates
trace.anomaly_score. If the score exceeds the threshold, an anomaly event
is emitted on the EventBus.

Scoring components (0.0 to 1.0, higher = more suspicious):
  1. route_deviation:  How much longer was the actual path vs. shortest?
  2. loop_detection:   Has the vehicle revisited the same junction >= N times?
  3. extended_stop:    Was there an unusually long gap between consecutive sightings?
  4. speed_anomaly:    Did the vehicle move implausibly fast between two cameras?

All components are normalized and combined as a weighted average.
Weights are defined in config.py.

No Intelli-Light source file is imported or modified here.
"""

import asyncio
import logging
import math
from typing import Dict, Optional

from sentinel.tracker.vehicle_trace import VehicleTrace
from sentinel.ingestion.event_bus import EventBus, anomaly_event
from sentinel.config import (
    ANOMALY_DEVIATION_THRESHOLD,
    ANOMALY_LOOP_MIN_VISITS,
    ANOMALY_STOP_THRESHOLD_S,
    ANOMALY_SPEED_LIMIT_FACTOR,
)

logger = logging.getLogger(__name__)

# Scoring weights (must sum to 1.0)
_W_DEVIATION = 0.40
_W_LOOP      = 0.25
_W_STOP      = 0.20
_W_SPEED     = 0.15

# Assumed average road speed limit in Lucknow network (m/s) for speed anomaly check
# 50 km/h = 13.9 m/s
_DEFAULT_SPEED_LIMIT_MPS = 13.9


class AnomalyScorer:
    """
    Stateless scorer: given a VehicleTrace, returns a score in [0, 1].
    """

    def score(self, trace: VehicleTrace) -> float:
        """
        Compute the overall anomaly score for a trace.
        Returns a float in [0.0, 1.0].
        """
        if len(trace.sightings) < 2:
            return 0.0  # not enough data yet

        components = {
            "route_deviation": self._score_route_deviation(trace),
            "loop":            self._score_loop(trace),
            "extended_stop":   self._score_extended_stop(trace),
            "speed_anomaly":   self._score_speed_anomaly(trace),
        }

        weighted = (
            _W_DEVIATION * components["route_deviation"] +
            _W_LOOP      * components["loop"]            +
            _W_STOP      * components["extended_stop"]   +
            _W_SPEED     * components["speed_anomaly"]
        )
        score = min(1.0, max(0.0, weighted))
        return score

    def explain(self, trace: VehicleTrace) -> dict:
        """Return per-component breakdown for dashboard display."""
        if len(trace.sightings) < 2:
            return {"total": 0.0}
        return {
            "route_deviation": round(self._score_route_deviation(trace), 3),
            "loop":            round(self._score_loop(trace), 3),
            "extended_stop":   round(self._score_extended_stop(trace), 3),
            "speed_anomaly":   round(self._score_speed_anomaly(trace), 3),
            "total":           round(self.score(trace), 3),
        }

    # ------------------------------------------------------------------
    # Component scorers
    # ------------------------------------------------------------------

    def _score_route_deviation(self, trace: VehicleTrace) -> float:
        """
        Score based on path length vs. minimum possible path.
        Minimum possible = number of unique junctions visited.
        Actual = len(junction_sequence) (includes revisits).
        Deviation ratio = (actual - min) / min.
        Capped at 1.0.
        """
        seq = trace.junction_sequence
        if len(seq) < 2:
            return 0.0
        unique = trace.unique_junctions
        actual = len(seq)
        if unique == 0:
            return 0.0
        deviation_ratio = (actual - unique) / max(unique, 1)
        # Scale: a ratio of 1.0 (double the necessary hops) = full score
        return min(1.0, deviation_ratio)

    def _score_loop(self, trace: VehicleTrace) -> float:
        """1.0 if a loop is detected, 0.0 otherwise."""
        detected, _ = trace.loop_detected(min_visits=ANOMALY_LOOP_MIN_VISITS)
        return 1.0 if detected else 0.0

    def _score_extended_stop(self, trace: VehicleTrace) -> float:
        """
        Score based on the longest gap between consecutive sightings.
        Gap >= ANOMALY_STOP_THRESHOLD_S -> score = 1.0.
        Linear interpolation below threshold.
        """
        gap = trace.max_gap_s()
        if gap <= 0:
            return 0.0
        return min(1.0, gap / ANOMALY_STOP_THRESHOLD_S)

    def _score_speed_anomaly(self, trace: VehicleTrace) -> float:
        """
        Check for implausibly fast hops (impossible vehicle teleportation
        or cloned plate). Uses haversine distance / time gap.
        If speed > speed_limit * ANOMALY_SPEED_LIMIT_FACTOR -> flag.
        """
        max_speed = _DEFAULT_SPEED_LIMIT_MPS * ANOMALY_SPEED_LIMIT_FACTOR
        worst = 0.0
        for i in range(len(trace.sightings) - 1):
            speed = trace.speed_on_hop(i)
            if speed is None:
                continue
            if speed > max_speed:
                # Normalize: 2x limit = full score
                ratio = min(1.0, (speed - max_speed) / max_speed)
                worst = max(worst, ratio)
        return worst


# ---------------------------------------------------------------------------
# Async engine wrapper
# ---------------------------------------------------------------------------

class AnomalyEngine:
    """
    Wraps AnomalyScorer and integrates with TrackerManager via on_update hook.

    Usage:
        engine = AnomalyEngine(bus)
        tracker = TrackerManager(..., on_update=engine.evaluate)
    """

    def __init__(self, bus: EventBus):
        self.bus = bus
        self._scorer = AnomalyScorer()
        self._last_scores: Dict[str, float] = {}
        logger.info("[AnomalyEngine] Initialized")

    async def evaluate(self, trace: VehicleTrace) -> None:
        """
        Called by TrackerManager.on_update every time a trace is updated.
        Re-scores the trace and emits anomaly events if the threshold is crossed.
        """
        score = self._scorer.score(trace)
        trace.anomaly_score = score
        prev_score = self._last_scores.get(trace.plate, 0.0)
        self._last_scores[trace.plate] = score

        if score >= ANOMALY_DEVIATION_THRESHOLD:
            # Only log/emit on significant score change (>= 0.05 delta)
            if abs(score - prev_score) >= 0.05 or prev_score < ANOMALY_DEVIATION_THRESHOLD:
                breakdown = self._scorer.explain(trace)
                dominant = max(
                    ["route_deviation", "loop", "extended_stop", "speed_anomaly"],
                    key=lambda k: breakdown.get(k, 0.0)
                )
                detail = (
                    f"Score={score:.3f} | Dominant={dominant} | "
                    f"Junctions={trace.unique_junctions} | "
                    f"Hops={len(trace.junction_sequence)} | "
                    f"TotalTime={trace.total_time_s:.0f}s"
                )
                last_junction = trace.last_seen.junction_id if trace.last_seen else "?"
                event = anomaly_event(
                    plate=trace.plate,
                    junction_id=last_junction,
                    timestamp=trace.last_seen.timestamp if trace.last_seen else 0.0,
                    anomaly_type=dominant,
                    score=score,
                    detail=detail,
                )
                self.bus.put_nowait(event)
                logger.warning(
                    f"[AnomalyEngine] ANOMALY | {trace.plate} | {detail}"
                )

    def explain(self, trace: VehicleTrace) -> dict:
        return self._scorer.explain(trace)
