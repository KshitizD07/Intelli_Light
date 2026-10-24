"""
sentinel/main.py
=================
Sentinel entry point. Wires all components and runs the async pipeline.

Usage:
    python sentinel/main.py [--mode sumo|video] [--gui] [--seed-demo]
    python -m sentinel [same flags]

Components started (all async, concurrent):
    1. SUMOInjector         - SUMO sim driver + sighting emitter
    2. TrackerManager       - per-vehicle trace builder
    3. AnomalyEngine        - route deviation + behaviour scorer
    4. ConsoleReporter      - prints live alerts to stdout

Intelli-Light is NOT started or modified here.
"""

import asyncio
import argparse
import logging
import sys
import os

# Ensure project root is on sys.path so sibling packages resolve
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sentinel.config import LOG_LEVEL, SUMO_NET_FILE
from sentinel.registry import FlaggedVehicleRegistry
from sentinel.ingestion.event_bus import EventBus
from sentinel.ingestion.sumo_injector import SUMOInjector, CameraGrid
from sentinel.tracker.tracker import TrackerManager
from sentinel.anomaly.scorer import AnomalyEngine

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("sentinel")


# ---------------------------------------------------------------------------
# Console reporter (lightweight async consumer for demo)
# ---------------------------------------------------------------------------

async def console_reporter(bus: EventBus):
    """Drains anomaly and alert events and prints them to stdout."""
    while True:
        try:
            event = await asyncio.wait_for(bus.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue
        etype = event.get("type")
        if etype in ("alert", "anomaly"):
            plate = event.get("plate", "?")
            jid   = event.get("junction_id", "?")
            extra = event.get("extra", {})
            if etype == "alert":
                print(
                    f"\n{'='*60}\n"
                    f"  BLACKLIST ALERT\n"
                    f"  Plate    : {plate}\n"
                    f"  Junction : {jid}\n"
                    f"  Reason   : {extra.get('reason', '')}\n"
                    f"  Authority: {extra.get('authority', '')}\n"
                    f"{'='*60}\n"
                )
            elif etype == "anomaly":
                print(
                    f"\n{'~'*60}\n"
                    f"  ANOMALY DETECTED\n"
                    f"  Plate    : {plate}\n"
                    f"  Junction : {jid}\n"
                    f"  Type     : {extra.get('anomaly_type', '')}\n"
                    f"  Score    : {extra.get('score', 0.0):.3f}\n"
                    f"  Detail   : {extra.get('detail', '')}\n"
                    f"{'~'*60}\n"
                )
        bus.task_done()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run(args):
    logger.info("Sentinel starting up")

    # Registry
    registry = FlaggedVehicleRegistry()
    if args.seed_demo:
        registry.seed_demo()

    # Event bus (single shared instance)
    bus = EventBus()

    # Camera grid (read Intelli-Light's SUMO network, read-only)
    camera_grid = CameraGrid(SUMO_NET_FILE)

    # Anomaly engine
    anomaly_engine = AnomalyEngine(bus)

    # Tracker
    tracker = TrackerManager(
        bus=bus,
        registry=registry,
        camera_grid=camera_grid,
        on_update=anomaly_engine.evaluate,
    )

    # SUMO injector
    injector = SUMOInjector(
        bus=bus,
        registry=registry,
        use_gui=args.gui,
    )

    # Run all components concurrently
    logger.info("Launching all Sentinel components concurrently")
    try:
        await asyncio.gather(
            injector.run(),
            tracker.run(),
            console_reporter(bus),
        )
    except KeyboardInterrupt:
        logger.info("Sentinel shut down by user")
    except Exception as e:
        logger.error(f"Sentinel crashed: {e}", exc_info=True)
        raise


def main():
    parser = argparse.ArgumentParser(
        prog="sentinel",
        description="Sentinel: City-Wide ANPR Trajectory Tracking for Intelli-Light",
    )
    parser.add_argument(
        "--mode",
        choices=["sumo", "video"],
        default="sumo",
        help="ALPR mode: 'sumo' uses synthetic SUMO sightings (default), "
             "'video' uses real camera frames via YOLOv8 + PaddleOCR",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        default=False,
        help="Launch SUMO with GUI (sumo-gui) for visual demo",
    )
    parser.add_argument(
        "--seed-demo",
        action="store_true",
        default=False,
        help="Seed the flagged vehicle registry with demo plates",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        default=False,
        help="Run the turnkey end-to-end Grand Finale demonstration scenario",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        default=False,
        help="Launch the live Web GIS surveillance dashboard server",
    )
    args = parser.parse_args()

    if args.demo:
        from sentinel.demo import main as demo_main
        demo_main()
        return

    if args.web:
        from sentinel.server import main as server_main
        server_main()
        return

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
