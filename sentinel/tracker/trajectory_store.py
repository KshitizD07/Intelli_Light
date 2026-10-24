"""
sentinel/tracker/trajectory_store.py
=====================================
SQLite-backed spatial-temporal trajectory store.

Features:
- Thread-safe storage for vehicle sightings and reconstructed trajectories.
- Spatial-temporal plausibility verification (flags speed violations / impossible hops).
- Real-time Origin-Destination (O-D) matrix generation for municipal traffic analytics.
- Forensic historical replay query engine.
"""

import sqlite3
import threading
import json
import logging
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timezone

from sentinel.config import TRACE_DB_PATH
from sentinel.tracker.vehicle_trace import VehicleTrace, Sighting

logger = logging.getLogger(__name__)
_store_lock = threading.Lock()


class TrajectoryStore:
    """
    Manages persistent storage for vehicle paths, events, and traffic matrix aggregation.
    """

    def __init__(self, db_path: str = TRACE_DB_PATH):
        self.db_path = db_path
        self._init_db()
        logger.info(f"[TrajectoryStore] Initialized at {db_path}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with _store_lock, self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sightings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plate TEXT NOT NULL,
                    junction_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    speed_mps REAL DEFAULT 0.0,
                    confidence REAL DEFAULT 1.0,
                    lat REAL DEFAULT 0.0,
                    lng REAL DEFAULT 0.0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sightings_plate ON sightings(plate);
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sightings_time ON sightings(timestamp);
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS trajectories (
                    plate TEXT PRIMARY KEY,
                    start_junction TEXT,
                    end_junction TEXT,
                    start_time REAL,
                    end_time REAL,
                    sightings_count INTEGER,
                    anomaly_score REAL DEFAULT 0.0,
                    is_flagged INTEGER DEFAULT 0,
                    geometry_geojson TEXT,
                    updated_at TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS od_matrix (
                    origin_junction TEXT NOT NULL,
                    destination_junction TEXT NOT NULL,
                    trip_count INTEGER DEFAULT 0,
                    avg_duration_s REAL DEFAULT 0.0,
                    PRIMARY KEY(origin_junction, destination_junction)
                )
            """)
            conn.commit()

    def record_sighting(self, plate: str, sighting: Sighting):
        """Append an individual sighting record."""
        plate = plate.upper().strip()
        with _store_lock, self._connect() as conn:
            conn.execute("""
                INSERT INTO sightings (plate, junction_id, timestamp, speed_mps, confidence, lat, lng)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                plate,
                sighting.junction_id,
                sighting.timestamp,
                sighting.speed_mps,
                sighting.confidence,
                sighting.lat,
                sighting.lng,
            ))
            conn.commit()

    def update_trajectory(
        self,
        trace: VehicleTrace,
        geometry_coords: Optional[List[Tuple[float, float]]] = None,
    ):
        """Persist or update summary trajectory state."""
        plate = trace.plate
        if not trace.sightings:
            return

        first = trace.first_seen
        last = trace.last_seen
        geom_json = json.dumps(geometry_coords or [])

        with _store_lock, self._connect() as conn:
            conn.execute("""
                INSERT INTO trajectories (
                    plate, start_junction, end_junction, start_time, end_time,
                    sightings_count, anomaly_score, is_flagged, geometry_geojson, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plate) DO UPDATE SET
                    end_junction = excluded.end_junction,
                    end_time = excluded.end_time,
                    sightings_count = excluded.sightings_count,
                    anomaly_score = excluded.anomaly_score,
                    is_flagged = excluded.is_flagged,
                    geometry_geojson = excluded.geometry_geojson,
                    updated_at = excluded.updated_at
            """, (
                plate,
                first.junction_id,
                last.junction_id,
                first.timestamp,
                last.timestamp,
                len(trace.sightings),
                trace.anomaly_score,
                int(trace.is_flagged),
                geom_json,
                datetime.now(timezone.utc).isoformat(),
            ))

            # If trip completed (at least 2 different junctions), update O-D matrix
            if first.junction_id != last.junction_id:
                duration = max(1.0, last.timestamp - first.timestamp)
                conn.execute("""
                    INSERT INTO od_matrix (origin_junction, destination_junction, trip_count, avg_duration_s)
                    VALUES (?, ?, 1, ?)
                    ON CONFLICT(origin_junction, destination_junction) DO UPDATE SET
                        trip_count = trip_count + 1,
                        avg_duration_s = (avg_duration_s * trip_count + excluded.avg_duration_s) / (trip_count + 1)
                """, (first.junction_id, last.junction_id, duration))

            conn.commit()

    def get_trajectory(self, plate: str) -> Optional[Dict[str, Any]]:
        plate = plate.upper().strip()
        with _store_lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM trajectories WHERE plate = ?", (plate,)).fetchone()
            if not row:
                return None
            res = dict(row)
            res["geometry"] = json.loads(res.get("geometry_geojson") or "[]")
            return res

    def get_all_active_trajectories(self, limit: int = 50) -> List[Dict[str, Any]]:
        with _store_lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trajectories ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
            out = []
            for r in rows:
                item = dict(r)
                item["geometry"] = json.loads(item.get("geometry_geojson") or "[]")
                out.append(item)
            return out

    def get_od_matrix(self, min_trips: int = 1) -> List[Dict[str, Any]]:
        with _store_lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM od_matrix WHERE trip_count >= ? ORDER BY trip_count DESC",
                (min_trips,),
            ).fetchall()
            return [dict(r) for r in rows]

    def verify_plausibility(
        self,
        plate: str,
        current_sighting: Sighting,
        max_speed_mps: float = 30.0,
    ) -> Tuple[bool, str]:
        """
        Evaluates spatial-temporal feasibility between the last sighting and current sighting.
        If speed required to reach current point exceeds physical constraints, flags impossible hop.
        """
        plate = plate.upper().strip()
        with _store_lock, self._connect() as conn:
            last = conn.execute(
                "SELECT * FROM sightings WHERE plate = ? ORDER BY timestamp DESC LIMIT 1",
                (plate,),
            ).fetchone()

        if not last:
            return True, "First sighting"

        dt = current_sighting.timestamp - last["timestamp"]
        if dt <= 0:
            return False, "Duplicate or backwards timestamp detected"

        # Check Euclidean or geographic distance
        lat1, lng1 = last["lat"], last["lng"]
        lat2, lng2 = current_sighting.lat, current_sighting.lng

        if lat1 != 0.0 and lat2 != 0.0:
            import math
            R = 6371000.0
            phi1, phi2 = math.radians(lat1), math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlam = math.radians(lng2 - lng1)
            ha = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
            dist_m = 2 * R * math.asin(math.sqrt(ha))
            calc_speed = dist_m / dt
            if calc_speed > max_speed_mps:
                return (
                    False,
                    f"Impossible hop: {dist_m:.0f}m covered in {dt:.1f}s ({calc_speed * 3.6:.1f} km/h > {max_speed_mps * 3.6:.1f} km/h)",
                )

        return True, "Plausible transition"
