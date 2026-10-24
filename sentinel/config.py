"""
sentinel/config.py
==================
All Sentinel constants and paths in one place.
No Intelli-Light source file is imported or modified here.
"""

import os

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Intelli-Light root

# Lucknow SUMO map (read-only, no modification)
SUMO_NET_FILE = os.path.join(_ROOT, "simulation", "lucknow_map", "lucknow.net.xml")
SUMO_ROU_FILE = os.path.join(_ROOT, "simulation", "lucknow_map", "lucknow.rou.xml")
SUMO_CFG_FILE = os.path.join(_ROOT, "simulation", "lucknow_map", "lucknow.sumocfg")

# Sentinel data directory (writable, isolated)
SENTINEL_DATA_DIR = os.path.join(_ROOT, "sentinel", "data")
os.makedirs(SENTINEL_DATA_DIR, exist_ok=True)

REGISTRY_DB_PATH = os.path.join(SENTINEL_DATA_DIR, "registry.db")
AUDIT_LOG_PATH   = os.path.join(SENTINEL_DATA_DIR, "audit.jsonl")
TRACE_DB_PATH    = os.path.join(SENTINEL_DATA_DIR, "traces.db")

# ---------------------------------------------------------------------------
# SUMO / Simulation
# ---------------------------------------------------------------------------
SUMO_BINARY      = "sumo"          # "sumo-gui" for visual demo
SUMO_PORT        = 8813            # TraCI port for Sentinel's own SUMO instance
SUMO_STEP_LENGTH = 1.0             # seconds per simulation tick
SUMO_MAX_STEPS   = 3600            # 1 hour of sim time per episode
CAMERA_RADIUS_M  = 30.0            # metres: vehicle must be within this of a junction to be "seen"

# ---------------------------------------------------------------------------
# ALPR Pipeline
# ---------------------------------------------------------------------------
ALPR_MODE = "sumo"    # "sumo" = synthetic sightings from TraCI | "video" = real camera feed
VOTE_WINDOW = 3        # frames to accumulate before committing a plate read
FUZZY_THRESHOLD = 85   # RapidFuzz score (0-100) minimum for plate match
OCR_CONFIDENCE_MIN = 0.60  # minimum PaddleOCR confidence to accept a read

# Common Indian OCR substitution pairs (character confusion)
OCR_SUBSTITUTIONS = [
    ("0", "D"), ("D", "0"),
    ("1", "I"), ("I", "1"),
    ("8", "B"), ("B", "8"),
    ("5", "S"), ("S", "5"),
]

# ---------------------------------------------------------------------------
# Anomaly Engine
# ---------------------------------------------------------------------------
ANOMALY_DEVIATION_THRESHOLD = 0.65   # score >= this triggers alert
ANOMALY_LOOP_MIN_VISITS     = 3      # junction visited this many times = loop detected
ANOMALY_STOP_THRESHOLD_S    = 120    # gap between consecutive sightings (seconds) = extended stop
ANOMALY_SPEED_LIMIT_FACTOR  = 1.4    # allow 40% over road speed limit before flagging

# ---------------------------------------------------------------------------
# Intercept Orchestrator
# ---------------------------------------------------------------------------
INTERCEPT_TTL_S = 600              # auto-expire override after 10 minutes
INTERCEPT_RED_HOLD_S = 90          # how long to hold red on blocked approaches
INTERCEPT_MAX_JUNCTIONS = 4        # max junctions to override simultaneously

# ---------------------------------------------------------------------------
# WebSocket / Event Bus
# ---------------------------------------------------------------------------
EVENT_BUS_MAX_QUEUE = 2000         # max pending events before dropping oldest

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = "INFO"
