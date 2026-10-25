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
from typing import Any, List

from sentinel.config import EVENT_BUS_MAX_QUEUE

logger = logging.getLogger(__name__)


class EventBus:
    """
    Asynchronous Publish-Subscribe EventBus supporting multiple concurrent subscribers.
    Each subscriber receives every published event, preventing race-condition event theft.

    Usage:
        bus = EventBus()

        # Producer:
        bus.put_nowait({"type": "sighting", ...})
        await bus.put({"type": "sighting", ...})

        # Consumer (default stream):
        event = await bus.get()

        # Dedicated Subscriber (separate stream):
        sub_queue = bus.subscribe()
        event = await sub_queue.get()
    """

    def __init__(self, maxsize: int = EVENT_BUS_MAX_QUEUE):
        self._maxsize = maxsize
        self._subscribers: List[asyncio.Queue] = []
        self._default_queue = asyncio.Queue(maxsize=maxsize)
        self._subscribers.append(self._default_queue)
        self._dropped = 0

    def subscribe(self, maxsize: int = EVENT_BUS_MAX_QUEUE) -> asyncio.Queue:
        """Create a dedicated subscriber queue that receives all published events."""
        q = asyncio.Queue(maxsize=maxsize)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove a subscriber queue."""
        if q in self._subscribers:
            self._subscribers.remove(q)

    async def put(self, event: dict) -> None:
        """Put an event, delivering it to all subscribers."""
        for q in list(self._subscribers):
            try:
                await q.put(event)
            except Exception:
                pass

    def put_nowait(self, event: dict) -> bool:
        """
        Non-blocking put. Dispatches event to all subscribers.
        Returns True if delivered to at least one subscriber.
        """
        delivered = False
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
                delivered = True
            except asyncio.QueueFull:
                self._dropped += 1
                if self._dropped % 100 == 1:
                    logger.warning(
                        f"[EventBus] Subscriber queue full - dropped {self._dropped} events total."
                    )
        return delivered

    async def get(self) -> dict:
        """Block until an event is available on the default subscriber queue."""
        return await self._default_queue.get()

    def task_done(self) -> None:
        try:
            self._default_queue.task_done()
        except ValueError:
            pass

    @property
    def size(self) -> int:
        return self._default_queue.qsize()

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
