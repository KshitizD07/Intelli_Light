"""
sentinel/server.py
==================
FastAPI Surveillance & Intelligence Server for Sentinel.

Features:
- WebSocket endpoint `/ws/live` pushing real-time multi-camera sightings,
  reconstructed vehicle paths, and blacklist/anomaly alarms.
- REST endpoints for operator registration, intercept triggering, and O-D matrix analytics.
- Static HTML5 Leaflet map UI served directly at `/`.
"""

import os
import sys
import asyncio
import logging
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ensure root is on path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sentinel.config import SUMO_NET_FILE
from sentinel.registry import FlaggedVehicleRegistry, FlaggedVehicle
from sentinel.ingestion.event_bus import EventBus
from sentinel.ingestion.sumo_injector import CameraGrid
from sentinel.tracker.tracker import TrackerManager
from sentinel.tracker.road_snapper import RoadSnapper
from sentinel.tracker.trajectory_store import TrajectoryStore
from sentinel.anomaly.gnn_bridge import GNNTelemetryBridge
from sentinel.anomaly.scorer import AnomalyEngine
from sentinel.intercept.orchestrator import InterceptOrchestrator
from sentinel.intercept.tactical_bridge import TacticalGuidanceBridge
from sentinel.ingestion.traffic_daemon import TrafficSimulationDaemon

logger = logging.getLogger("sentinel.server")

# ---------------------------------------------------------------------------
# Global Singletons
# ---------------------------------------------------------------------------
registry = FlaggedVehicleRegistry()
bus = EventBus()
camera_grid = CameraGrid(SUMO_NET_FILE)
road_snapper = RoadSnapper(SUMO_NET_FILE)
trajectory_store = TrajectoryStore()
gnn_bridge = GNNTelemetryBridge()
anomaly_engine = AnomalyEngine(bus, gnn_bridge=gnn_bridge)
intercept_orchestrator = InterceptOrchestrator(registry)
tactical_bridge = TacticalGuidanceBridge(orchestrator=intercept_orchestrator)

traffic_daemon = TrafficSimulationDaemon(
    bus=bus,
    registry=registry,
    camera_grid=camera_grid,
    gnn_bridge=gnn_bridge,
    orchestrator=intercept_orchestrator,
    road_snapper=road_snapper,
    tick_interval_s=1.0,
)

active_websockets: List[WebSocket] = []
recent_alerts: List[dict] = []


# ---------------------------------------------------------------------------
# Background Ingestion & Broadcast Worker
# ---------------------------------------------------------------------------
async def on_trace_updated(trace):
    """Callback fired on each new sighting processed by TrackerManager."""
    await anomaly_engine.evaluate(trace)

    # Calculate road-snapped geometry
    seq = trace.junction_sequence
    coords = road_snapper.get_route_geometry(seq)
    trajectory_store.update_trajectory(trace, geometry_coords=coords)

    # Broadcast to all connected WebSocket clients
    if active_websockets:
        payload = {
            "vehicles": {
                trace.plate: {
                    "plate": trace.plate,
                    "is_flagged": trace.is_flagged,
                    "anomaly_score": trace.anomaly_score,
                    "last_sighting": {
                        "junction_id": trace.last_seen.junction_id if trace.last_seen else None,
                        "timestamp": trace.last_seen.timestamp if trace.last_seen else None,
                        "lat": trace.last_seen.lat if trace.last_seen else None,
                        "lng": trace.last_seen.lng if trace.last_seen else None,
                    },
                    "geometry": coords,
                }
            },
            "metrics": {
                "active_vehicles": tracker.active_count,
                "active_cameras": len(camera_grid.cameras),
                "avg_anomaly": sum(t.anomaly_score for t in tracker.all_traces().values()) / max(1, tracker.active_count),
            }
        }
        for ws in list(active_websockets):
            try:
                await ws.send_json(payload)
            except Exception:
                pass


tracker = TrackerManager(
    bus=bus,
    registry=registry,
    camera_grid=camera_grid,
    on_update=on_trace_updated,
)


async def event_bus_listener():
    """Subscribes to dedicated event stream, records alert history, and broadcasts alerts."""
    sub_queue = bus.subscribe()
    while True:
        try:
            event = await asyncio.wait_for(sub_queue.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue

        etype = event.get("type")
        if etype in ("alert", "anomaly"):
            recent_alerts.append(event)
            if len(recent_alerts) > 100:
                recent_alerts.pop(0)

            if active_websockets:
                payload = {
                    "alert": event,
                    "metrics": {
                        "total_alerts": len(recent_alerts),
                    }
                }
                for ws in list(active_websockets):
                    try:
                        await ws.send_json(payload)
                    except Exception:
                        pass


async def fleet_broadcaster():
    """Periodically streams fleet coordinates and signal override states to WebSockets."""
    while True:
        await asyncio.sleep(1.0)
        if active_websockets:
            fleet = traffic_daemon.get_fleet_telemetry()
            overrides = intercept_orchestrator.get_signal_overrides()
            directives = {}
            for jid, ov in overrides.items():
                d = tactical_bridge.get_directive(jid)
                if d:
                    directives[jid] = {
                        "stage": d.stage.value,
                        "target_speed_mps": d.target_speed_mps,
                        "strategy": d.stage.value,
                    }
            avg_anom = (
                sum(t.anomaly_score for t in tracker.all_traces().values()) / max(1, tracker.active_count)
                if tracker.active_count > 0 else 0.0
            )
            payload = {
                "fleet": fleet,
                "overrides": overrides,
                "directives": directives,
                "metrics": {
                    "active_vehicles": len(fleet),
                    "active_cameras": len(camera_grid.cameras),
                    "avg_anomaly": round(avg_anom, 3),
                    "total_alerts": len(recent_alerts),
                }
            }
            for ws in list(active_websockets):
                try:
                    await ws.send_json(payload)
                except Exception:
                    pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[SentinelServer] Starting background tracker, simulation daemon & broadcast worker...")
    registry.seed_demo()
    tracker_task = asyncio.create_task(tracker.run())
    listener_task = asyncio.create_task(event_bus_listener())
    daemon_task = asyncio.create_task(traffic_daemon.run())
    fleet_task = asyncio.create_task(fleet_broadcaster())
    yield
    traffic_daemon.stop()
    tracker.stop()
    tracker_task.cancel()
    listener_task.cancel()
    daemon_task.cancel()
    fleet_task.cancel()


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(title="Sentinel Intelligence Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")


@app.get("/")
def get_index():
    index_file = os.path.join(static_path, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse({"status": "Sentinel Server Online", "dashboard": "static/index.html missing"})


# ---------------------------------------------------------------------------
# REST Endpoints
# ---------------------------------------------------------------------------
class FlagVehicleRequest(BaseModel):
    plate: str
    flag_reason: str
    authority: str
    intercept_authorized: bool = False
    notes: str = ""


@app.get("/api/flagged")
def list_flagged_vehicles():
    return registry.all_flagged()


@app.post("/api/flagged")
def add_flagged_vehicle(req: FlagVehicleRequest):
    v = FlaggedVehicle(
        plate=req.plate,
        flag_reason=req.flag_reason,
        authority=req.authority,
        intercept_authorized=req.intercept_authorized,
        notes=req.notes,
    )
    registry.add(v)
    return {"status": "registered", "plate": v.plate}


@app.post("/api/flagged/{plate}/authorize")
def authorize_plate_intercept(plate: str):
    ok = registry.authorize_intercept(plate)
    if not ok:
        raise HTTPException(status_code=404, detail="Vehicle not found in registry")
    return {"status": "authorized", "plate": plate}


class InterceptRequest(BaseModel):
    plate: str
    current_junction: str
    authorized_by: str
    reason: str


@app.post("/api/intercept/trigger")
def trigger_intercept(req: InterceptRequest):
    res = intercept_orchestrator.request_intercept(
        plate=req.plate,
        current_junction=req.current_junction,
        authorized_by=req.authorized_by,
        reason=req.reason,
    )
    return res


class CancelInterceptRequest(BaseModel):
    plate: str
    cancelled_by: str


@app.post("/api/intercept/cancel")
def cancel_intercept(req: CancelInterceptRequest):
    ok = intercept_orchestrator.cancel_intercept(req.plate, req.cancelled_by)
    return {"success": ok}


@app.get("/api/intercept/overrides")
def get_active_signal_overrides():
    return intercept_orchestrator.get_signal_overrides()


@app.get("/api/intercept/directives")
def get_active_tactical_directives():
    overrides = intercept_orchestrator.get_signal_overrides()
    res = {}
    for jid, ov in overrides.items():
        directive = tactical_bridge.get_directive(jid)
        if directive:
            plan = tactical_bridge.compute_ntcip_plan(directive)
            res[jid] = {
                "mission_id": directive.mission_id,
                "target_plate": directive.target_plate,
                "stage": directive.stage.value,
                "target_speed_mps": directive.target_speed_mps,
                "ntcip_plan": plan,
                "remaining_ttl": ov.get("remaining_ttl", 0),
            }
    return res


@app.get("/api/od-matrix")
def get_origin_destination_matrix():
    return trajectory_store.get_od_matrix()


@app.get("/api/trajectories")
def get_active_trajectories():
    return trajectory_store.get_all_active_trajectories()


@app.get("/api/fleet")
def get_fleet_telemetry():
    return traffic_daemon.get_fleet_telemetry()


@app.get("/api/alerts")
def get_recent_alerts(limit: int = 50):
    return recent_alerts[-limit:]


@app.get("/api/audit")
def get_audit_trail(limit: int = 50):
    import json
    from sentinel.config import AUDIT_LOG_PATH
    if not os.path.exists(AUDIT_LOG_PATH):
        return []
    records = []
    with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    records.append(json.loads(line.strip()))
                except Exception:
                    pass
    return records[-limit:]


# ---------------------------------------------------------------------------
# WebSocket Telemetry
# ---------------------------------------------------------------------------
@app.websocket("/ws/live")
async def websocket_live_stream(ws: WebSocket):
    await ws.accept()
    active_websockets.append(ws)
    try:
        avg_anom = (
            sum(t.anomaly_score for t in tracker.all_traces().values()) / max(1, tracker.active_count)
            if tracker.active_count > 0 else 0.0
        )
        # Push initial camera topology, recent alerts, and real-time metrics
        await ws.send_json({
            "cameras": camera_grid.cameras,
            "recent_alerts": recent_alerts[-30:],
            "metrics": {
                "active_vehicles": max(len(traffic_daemon.vehicles), tracker.active_count),
                "active_cameras": len(camera_grid.cameras),
                "avg_anomaly": round(avg_anom, 2),
                "total_alerts": len(recent_alerts),
            }
        })
        while True:
            # Keepalive listener
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in active_websockets:
            active_websockets.remove(ws)
    except Exception:
        if ws in active_websockets:
            active_websockets.remove(ws)


def main():
    import uvicorn
    import argparse
    parser = argparse.ArgumentParser(description="Start Sentinel Surveillance Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host binding")
    parser.add_argument("--port", type=int, default=8888, help="Port binding")
    args = parser.parse_args()

    logger.info(f"Starting Sentinel Web Server on http://{args.host}:{args.port}")
    uvicorn.run("sentinel.server:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
