"""
sentinel/ingestion/event_bus.py
================================
Asynchronous event bus for Sentinel.

All internal components communicate by putting/getting events here.
No polling loops: producers put(), consumers await get().

Event schema (dict):
    {
        "type": "sighting" | "alert" | "intercept_request" | "anomaly",
        "plate": str,
        "junction_id": str,
        "timestamp": float,          # SUMO sim time or wall clock
        "confidence": float,         # ALPR confidence 0-1
        "extra": dict,               # type-specific payload
    }
"""

import asyncio
import logging
from typing import Any

from sentinel.config import EVENT_BUS_MAX_QUEUE

logger = logging.getLogger(__name__)


class EventBus:
    """
    Simple asyncio.Queue wrapper with back-pressure handling.

    Usage:
        bus = EventBus()

        # Producer (sync or async):
        bus.put_nowait({"type": "sighting", ...})
        await bus.put({"type": "sighting", ...})

        # Consumer (async):
        event = await bus.get()
    """

    def __init__(self, maxsize: int = EVENT_BUS_MAX_QUEUE):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._dropped = 0

    async def put(self, event: dict) -> None:
        """Put an event, waiting if the queue is full."""
        await self._queue.put(event)

    def put_nowait(self, event: dict) -> bool:
        """
        Non-blocking put. Drops the event (and logs) if queue is full.
        Returns True if enqueued, False if dropped.
        """
        try:
            self._queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            self._dropped += 1
            if self._dropped % 100 == 1:
                logger.warning(
                    f"[EventBus] Queue full - dropped {self._dropped} events total."
                )
            return False

    async def get(self) -> dict:
        """Block until an event is available and return it."""
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    @property
    def size(self) -> int:
        return self._queue.qsize()

    @property
    def dropped(self) -> int:
        return self._dropped


# ---------------------------------------------------------------------------
# Event constructors (typed helpers to avoid dict typos)
# ---------------------------------------------------------------------------

def sighting_event(
    plate: str,
    junction_id: str,
    timestamp: float,
    confidence: float = 1.0,
    speed_mps: float = 0.0,
    lane_id: str = "",
) -> dict:
    return {
        "type": "sighting",
        "plate": plate.upper().strip(),
        "junction_id": junction_id,
        "timestamp": timestamp,
        "confidence": confidence,
        "extra": {
            "speed_mps": speed_mps,
            "lane_id": lane_id,
        },
    }


def alert_event(
    plate: str,
    junction_id: str,
    timestamp: float,
    reason: str,
    anomaly_score: float = 0.0,
    authority: str = "",
) -> dict:
    return {
        "type": "alert",
        "plate": plate.upper().strip(),
        "junction_id": junction_id,
        "timestamp": timestamp,
        "confidence": 1.0,
        "extra": {
            "reason": reason,
            "anomaly_score": anomaly_score,
            "authority": authority,
        },
    }


def anomaly_event(
    plate: str,
    junction_id: str,
    timestamp: float,
    anomaly_type: str,
    score: float,
    detail: str = "",
) -> dict:
    return {
        "type": "anomaly",
        "plate": plate.upper().strip(),
        "junction_id": junction_id,
        "timestamp": timestamp,
        "confidence": score,
        "extra": {
            "anomaly_type": anomaly_type,
            "score": score,
            "detail": detail,
        },
    }
