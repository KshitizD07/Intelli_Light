"""
dashboard_backend.py
====================
FastAPI application that serves as the real-time bridge between our SUMO traffic
simulation (with GNN-based traffic AI) and the web dashboard.

Run with:
    python -m uvicorn webapp.dashboard_backend:app --reload --port 8000
"""

import os
import sys
import math
import json
import time
import random
import asyncio
import logging
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(ROOT_DIR, "webapp", "static")
NET_FILE = os.path.join(ROOT_DIR, "simulation", "lucknow_map", "lucknow.net.xml")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("dashboard_backend")

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------
# Connected WebSocket clients
connected_clients: List[WebSocket] = []

# Simulation state
sim_state: Dict[str, Any] = {
    "paused": False,
    "tick": 0,
    "sim_time": 0.0,
    "overrides": {},        # junction_id -> phase
    "events_log": [],       # recent events
}

# Parsed network topology (populated on startup)
network_topology: Dict[str, Any] = {
    "junctions": [],
    "edges": [],
    "traffic_lights": [],
}


# ---------------------------------------------------------------------------
# SUMO Network Parser
# ---------------------------------------------------------------------------
def parse_sumo_network(net_file: str) -> Dict[str, Any]:
    """Parse a SUMO .net.xml file using sumolib and return topology data.
    Only returns traffic-light controlled junctions (not every road vertex).
    Converts SUMO internal x/y to geographic lng/lat."""
    try:
        sys.path.append(os.path.join(os.environ.get("SUMO_HOME", ""), "tools"))
        import sumolib
    except (ImportError, Exception) as e:
        logger.warning(f"sumolib not available ({e}), will use mock data")
        return {}

    if not os.path.isfile(net_file):
        logger.warning(f"Network file not found: {net_file}")
        return {}

    logger.info(f"Parsing SUMO network: {net_file}")
    try:
        net = sumolib.net.readNet(net_file)
    except Exception as e:
        logger.error(f"Failed to parse network file: {e}")
        return {}

    # Only extract traffic-light controlled junctions
    tls_ids = [tls.getID() for tls in net.getTrafficLights()]
    
    # Also include major priority junctions that have >= 3 incoming edges
    junctions = []
    tls_id_set = set(tls_ids)
    
    # Collect all candidate junctions
    tls_junctions = []
    other_junctions = []
    
    for node in net.getNodes():
        node_type = node.getType()
        node_id = node.getID()
        
        if node_type in ("internal", "dead_end"):
            continue
        
        is_tls = node_id in tls_id_set or node_type == "traffic_light"
        incoming_count = len(node.getIncoming())
        
        x, y = node.getCoord()
        try:
            lng, lat = net.convertXY2LonLat(x, y)
        except Exception:
            lng, lat = x, y
        
        entry = {
            "id": node_id,
            "lng": round(lng, 6),
            "lat": round(lat, 6),
            "type": node_type,
            "name": getattr(node, "getName", lambda: "")() or node_id,
            "has_tls": is_tls,
            "_incoming": incoming_count,
        }
        
        if is_tls:
            tls_junctions.append(entry)
        elif incoming_count >= 4:
            other_junctions.append(entry)
    
    # Sort non-TLS by importance (incoming edge count) and take the top ones
    other_junctions.sort(key=lambda j: j["_incoming"], reverse=True)
    MAX_DISPLAY = 100
    remaining_slots = max(0, MAX_DISPLAY - len(tls_junctions))
    junctions = tls_junctions + other_junctions[:remaining_slots]
    
    # Remove internal field
    for j in junctions:
        j.pop("_incoming", None)
    
    logger.info(f"Filtered to {len(junctions)} display junctions ({len(tls_junctions)} TLS + {min(remaining_slots, len(other_junctions))} major)")

    edges = []
    junction_ids = {j["id"] for j in junctions}
    for edge in net.getEdges():
        from_id = edge.getFromNode().getID()
        to_id = edge.getToNode().getID()
        if from_id in junction_ids and to_id in junction_ids:
            edges.append({
                "id": edge.getID(),
                "from_junction": from_id,
                "to_junction": to_id,
                "name": edge.getName() or edge.getID(),
                "lanes": edge.getLaneNumber(),
            })

    return {
        "junctions": junctions,
        "edges": edges,
        "traffic_lights": tls_ids,
    }


def generate_mock_network() -> Dict[str, Any]:
    """Generate a mock network topology with 41 junctions spread across
    a realistic coordinate space resembling Lucknow's road network."""

    random.seed(42)  # Reproducible layout

    # Grid-ish layout with some randomness — 6 columns × 7 rows ≈ 42, trim to 41
    junctions: List[Dict[str, Any]] = []
    tls_ids: List[str] = []

    junction_names = [
        "Hazratganj", "Aminabad", "Charbagh", "Alambagh", "Gomti Nagar",
        "Indira Nagar", "Aliganj", "Mahanagar", "Rajajipuram", "Vikas Nagar",
        "Chinhat", "Cantt", "Hussainabad", "Kaiserbagh", "Naka Hindola",
        "Chowk", "Daliganj", "Jankipuram", "Faizabad Rd", "Sitapur Rd",
        "Ashiyana", "Eldeco", "Munshipulia", "Telibagh", "Sushant Golf City",
        "Saharaganj", "Lalbagh", "Nishatganj", "Bangla Bazaar", "Polytechnic",
        "IT Crossing", "Lekhraj", "Awadh", "Riverside", "Transport Nagar",
        "Bhootnath", "Kalidas Marg", "Patel Nagar", "Balaganj", "Thakurganj",
        "Gudamba",
    ]

    # Geographic coordinates centered on Lucknow
    cols, rows = 6, 7
    base_lng, base_lat = 80.92, 26.82
    spacing_lng, spacing_lat = 0.012, 0.009

    idx = 0
    for r in range(rows):
        for c in range(cols):
            if idx >= 41:
                break
            jid = f"j_{idx}"
            lng = base_lng + c * spacing_lng + random.uniform(-0.002, 0.002)
            lat = base_lat + r * spacing_lat + random.uniform(-0.0015, 0.0015)
            jtype = "traffic_light" if random.random() < 0.65 else "priority"
            junctions.append({
                "id": jid,
                "lng": round(lng, 6),
                "lat": round(lat, 6),
                "type": jtype,
                "name": junction_names[idx] if idx < len(junction_names) else f"Junction {idx}",
                "has_tls": jtype == "traffic_light",
            })
            if jtype == "traffic_light":
                tls_ids.append(jid)
            idx += 1

    # Build edges: connect neighbours in the grid + a few diagonals
    edges: List[Dict[str, Any]] = []
    edge_id = 0

    def add_edge(from_idx: int, to_idx: int, lanes: int = 2):
        nonlocal edge_id
        fj = f"j_{from_idx}"
        tj = f"j_{to_idx}"
        edges.append({
            "id": f"e_{edge_id}",
            "from_junction": fj,
            "to_junction": tj,
            "name": f"{junction_names[from_idx] if from_idx < len(junction_names) else fj} → "
                    f"{junction_names[to_idx] if to_idx < len(junction_names) else tj}",
            "lanes": lanes,
        })
        edge_id += 1

    for r in range(rows):
        for c in range(cols):
            i = r * cols + c
            if i >= 41:
                break
            # Right neighbour
            if c + 1 < cols and i + 1 < 41:
                add_edge(i, i + 1, lanes=random.choice([2, 3, 4]))
            # Bottom neighbour
            if r + 1 < rows and i + cols < 41:
                add_edge(i, i + cols, lanes=random.choice([2, 3]))
            # Diagonal (occasional)
            if c + 1 < cols and r + 1 < rows and i + cols + 1 < 41 and random.random() < 0.25:
                add_edge(i, i + cols + 1, lanes=2)

    return {
        "junctions": junctions,
        "edges": edges,
        "traffic_lights": tls_ids,
    }


# ---------------------------------------------------------------------------
# Mock Live Data Generator
# ---------------------------------------------------------------------------
PHASE_NAMES = [
    "GGGGrrrr", "rrrrGGGG", "GGrrGGrr", "rrGGrrGG",
    "GrGrGrGr", "rGrGrGrG", "GGGGGrrr", "rrrGGGGG",
]

# Per-junction mock state — initialised after network is loaded
_junction_mock_state: Dict[str, Dict[str, Any]] = {}


def _init_junction_mock_states():
    """Initialise per-junction random state for realistic mock data."""
    for junc in network_topology["junctions"]:
        jid = junc["id"]
        _junction_mock_state[jid] = {
            "base_queue": random.randint(3, 25),
            "phase_idx": random.randint(0, len(PHASE_NAMES) - 1),
            "phase_timer": random.uniform(0, 30),
            "phase_duration": random.uniform(20, 60),
            "control_mode": random.choice(["GNN", "GNN", "GNN", "FIXED", "MANUAL"]),
            "backpressure": random.uniform(0.1, 0.9),
            "trend": random.choice([-1, 1]),  # queue growing or shrinking
        }


def generate_mock_snapshot(tick: int, sim_time: float) -> Dict[str, Any]:
    """Produce one snapshot of mock traffic data."""
    nodes = []
    events = []

    total_vehicles = 0
    total_wait = 0.0
    active_failsafes = 0
    active_ev = 0
    throughput = 0

    for junc in network_topology["junctions"]:
        jid = junc["id"]
        state = _junction_mock_state.get(jid)
        if state is None:
            continue

        # Evolve queue with some randomness
        if random.random() < 0.1:
            state["trend"] *= -1  # flip trend occasionally

        queue_delta = state["trend"] * random.uniform(0, 3) + random.gauss(0, 1.5)
        queue = max(0, int(state["base_queue"] + queue_delta))
        state["base_queue"] = max(1, state["base_queue"] + state["trend"] * 0.15)

        # Clamp queue to realistic range
        queue = max(0, min(queue, 80))
        state["base_queue"] = max(1, min(state["base_queue"], 60))

        avg_wait = max(0, queue * random.uniform(1.5, 4.0))
        max_wait = avg_wait + random.uniform(5, 30)

        # Phase cycling
        state["phase_timer"] += 2.0  # each tick = 2 seconds
        if state["phase_timer"] >= state["phase_duration"]:
            state["phase_idx"] = (state["phase_idx"] + 1) % len(PHASE_NAMES)
            state["phase_timer"] = 0.0
            state["phase_duration"] = random.uniform(20, 60)

        # Backpressure drifts
        state["backpressure"] += random.gauss(0, 0.05)
        state["backpressure"] = max(0.0, min(1.0, state["backpressure"]))

        nodes.append({
            "id": jid,
            "queue": queue,
            "avg_wait": round(avg_wait, 1),
            "max_wait": round(max_wait, 1),
            "current_phase": state["phase_idx"],
            "phase_name": PHASE_NAMES[state["phase_idx"]],
            "time_in_phase": round(state["phase_timer"], 1),
            "control_mode": state["control_mode"],
            "backpressure": round(state["backpressure"], 2),
        })

        total_vehicles += queue
        total_wait += avg_wait
        throughput += random.randint(0, 5)

        # Failsafe events — roughly every ~30 ticks
        if random.random() < 1.0 / 30:
            events.append({
                "type": "FAILSAFE",
                "junction": jid,
                "message": random.choice([
                    "Lane starved 90s",
                    "Queue overflow detected",
                    "Phase stuck > 120s",
                    "Backpressure critical",
                    "Detector malfunction fallback",
                ]),
                "time": sim_time,
            })
            active_failsafes += 1

        # EV preemption — roughly every ~100 ticks
        if random.random() < 1.0 / 100:
            events.append({
                "type": "EV_PREEMPTION",
                "junction": jid,
                "message": random.choice([
                    "Ambulance approaching — green corridor",
                    "Fire engine priority activated",
                    "VIP escort preemption",
                ]),
                "time": sim_time,
            })
            active_ev += 1

    n_junctions = max(len(nodes), 1)
    avg_wait_global = round(total_wait / n_junctions, 1)

    kpis = {
        "avg_wait": avg_wait_global,
        "total_vehicles": total_vehicles,
        "throughput": throughput,
        "active_failsafes": active_failsafes,
        "active_ev_preemptions": active_ev,
    }

    return {
        "tick": tick,
        "sim_time": round(sim_time, 1),
        "nodes": nodes,
        "events": events,
        "kpis": kpis,
    }


# ---------------------------------------------------------------------------
# WebSocket broadcaster
# ---------------------------------------------------------------------------
async def broadcast_loop():
    """Background task: broadcast a live snapshot to every connected client
    every 2 seconds."""
    logger.info("Broadcast loop started")
    while True:
        await asyncio.sleep(2)

        if sim_state["paused"]:
            continue

        sim_state["tick"] += 1
        sim_state["sim_time"] += 2.0

        snapshot = generate_mock_snapshot(sim_state["tick"], sim_state["sim_time"])
        payload = json.dumps(snapshot)

        # Store recent events
        if snapshot["events"]:
            sim_state["events_log"].extend(snapshot["events"])
            # Keep only the last 200 events
            sim_state["events_log"] = sim_state["events_log"][-200:]

        stale: List[WebSocket] = []
        for ws in connected_clients:
            try:
                await ws.send_text(payload)
            except Exception:
                stale.append(ws)

        for ws in stale:
            try:
                connected_clients.remove(ws)
            except ValueError:
                pass


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hook."""
    # -- Startup --
    # 1. Parse network topology
    parsed = parse_sumo_network(NET_FILE)
    if parsed and parsed.get("junctions"):
        network_topology.update(parsed)
        logger.info(
            f"Loaded SUMO network: {len(network_topology['junctions'])} junctions, "
            f"{len(network_topology['edges'])} edges, "
            f"{len(network_topology['traffic_lights'])} traffic lights"
        )
    else:
        logger.info("Using mock network topology")
        network_topology.update(generate_mock_network())

    # 2. Initialise per-junction mock states
    _init_junction_mock_states()

    # 3. Start background broadcast loop
    task = asyncio.create_task(broadcast_loop())

    yield  # --- app is running ---

    # -- Shutdown --
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    logger.info("Broadcast loop stopped")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="IntelliLight Dashboard Backend",
    description="Real-time bridge between SUMO traffic simulation and the web dashboard.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 1. Network Topology Endpoint
# ---------------------------------------------------------------------------
@app.get("/api/network")
async def get_network():
    """Return the full network topology (junctions, edges, traffic lights).
    Called once when the dashboard loads."""
    return JSONResponse(content=network_topology)


# ---------------------------------------------------------------------------
# 2. WebSocket Endpoint — /ws/live
# ---------------------------------------------------------------------------
@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    """Accept a WebSocket connection and add it to the broadcast list.
    The broadcast_loop pushes snapshots every 2 seconds."""
    await ws.accept()
    connected_clients.append(ws)
    logger.info(f"WebSocket client connected ({len(connected_clients)} total)")

    try:
        while True:
            # Keep the connection open; listen for any client messages (pings, etc.)
            data = await ws.receive_text()
            # Clients can send a JSON ping — we just acknowledge
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        try:
            connected_clients.remove(ws)
        except ValueError:
            pass
        logger.info(f"WebSocket client disconnected ({len(connected_clients)} remaining)")


# ---------------------------------------------------------------------------
# 3. Command Endpoint
# ---------------------------------------------------------------------------
class CommandPayload(BaseModel):
    type: str                        # "OVERRIDE", "PAUSE", "RESUME"
    junction: Optional[str] = None
    phase: Optional[int] = None


@app.post("/api/command")
async def handle_command(cmd: CommandPayload):
    """Accept operator commands — override phase, pause/resume simulation."""
    cmd_type = cmd.type.upper()

    if cmd_type == "PAUSE":
        sim_state["paused"] = True
        logger.info("Simulation PAUSED by operator")
        return {"status": "ok", "message": "Simulation paused"}

    elif cmd_type == "RESUME":
        sim_state["paused"] = False
        logger.info("Simulation RESUMED by operator")
        return {"status": "ok", "message": "Simulation resumed"}

    elif cmd_type == "OVERRIDE":
        if not cmd.junction:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Missing 'junction' for OVERRIDE command"},
            )
        if cmd.phase is None:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Missing 'phase' for OVERRIDE command"},
            )
        sim_state["overrides"][cmd.junction] = cmd.phase
        # Also update the mock state so it takes effect immediately
        if cmd.junction in _junction_mock_state:
            _junction_mock_state[cmd.junction]["phase_idx"] = cmd.phase % len(PHASE_NAMES)
            _junction_mock_state[cmd.junction]["phase_timer"] = 0.0
            _junction_mock_state[cmd.junction]["control_mode"] = "MANUAL"
        logger.info(f"OVERRIDE: junction={cmd.junction} → phase {cmd.phase}")
        return {"status": "ok", "message": f"Junction {cmd.junction} overridden to phase {cmd.phase}"}

    else:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": f"Unknown command type: {cmd_type}"},
        )


# ---------------------------------------------------------------------------
# 4. Serve Static Files & Dashboard HTML at root
# ---------------------------------------------------------------------------
# Mount static directory AFTER API routes so /api/* takes priority
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    logger.warning(f"Static directory not found: {STATIC_DIR}")

DASHBOARD_HTML = os.path.join(STATIC_DIR, "dashboard.html")


@app.get("/")
async def root():
    """Serve the dashboard HTML at the root path."""
    if os.path.isfile(DASHBOARD_HTML):
        return FileResponse(DASHBOARD_HTML)
    return JSONResponse(
        status_code=404,
        content={"detail": "dashboard.html not found in webapp/static/"},
    )
