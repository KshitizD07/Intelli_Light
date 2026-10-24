"""
sentinel/registry.py
=====================
Flagged Vehicle Registry backed by SQLite.

Stores which plates are flagged, by whom, why, and whether
intercept has been authorized. All reads/writes are thread-safe
via a module-level lock.

No Intelli-Light source file is imported or modified here.
"""

import sqlite3
import threading
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone

from sentinel.config import REGISTRY_DB_PATH

logger = logging.getLogger(__name__)
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class FlaggedVehicle:
    plate: str
    flag_reason: str
    authority: str
    flagged_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    intercept_authorized: bool = False
    notes: str = ""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class FlaggedVehicleRegistry:
    """
    Thread-safe SQLite-backed registry of flagged vehicle plates.

    Usage:
        registry = FlaggedVehicleRegistry()
        registry.add(FlaggedVehicle(plate="UP32AB1234", flag_reason="surveillance",
                                    authority="Lucknow CP"))
        entry = registry.lookup("UP32AB1234")
        registry.authorize_intercept("UP32AB1234")
        registry.remove("UP32AB1234")
    """

    def __init__(self, db_path: str = REGISTRY_DB_PATH):
        self.db_path = db_path
        self._init_db()
        logger.info(f"FlaggedVehicleRegistry initialized at {db_path}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with _lock, self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS flagged_vehicles (
                    plate                TEXT PRIMARY KEY,
                    flag_reason          TEXT NOT NULL,
                    authority            TEXT NOT NULL,
                    flagged_at           TEXT NOT NULL,
                    intercept_authorized INTEGER NOT NULL DEFAULT 0,
                    notes                TEXT DEFAULT ''
                )
            """)
            conn.commit()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add(self, vehicle: FlaggedVehicle) -> None:
        """Add or replace a flagged vehicle entry."""
        with _lock, self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO flagged_vehicles
                    (plate, flag_reason, authority, flagged_at, intercept_authorized, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                vehicle.plate.upper().strip(),
                vehicle.flag_reason,
                vehicle.authority,
                vehicle.flagged_at,
                int(vehicle.intercept_authorized),
                vehicle.notes,
            ))
            conn.commit()
        logger.info(f"[REGISTRY] Added: {vehicle.plate} | reason={vehicle.flag_reason}")

    def remove(self, plate: str) -> bool:
        """Remove a plate from the registry. Returns True if found and removed."""
        plate = plate.upper().strip()
        with _lock, self._connect() as conn:
            cursor = conn.execute("DELETE FROM flagged_vehicles WHERE plate = ?", (plate,))
            conn.commit()
            removed = cursor.rowcount > 0
        if removed:
            logger.info(f"[REGISTRY] Removed: {plate}")
        return removed

    def authorize_intercept(self, plate: str) -> bool:
        """Set intercept_authorized=True for a plate. Returns True if plate exists."""
        plate = plate.upper().strip()
        with _lock, self._connect() as conn:
            cursor = conn.execute(
                "UPDATE flagged_vehicles SET intercept_authorized = 1 WHERE plate = ?",
                (plate,)
            )
            conn.commit()
            updated = cursor.rowcount > 0
        if updated:
            logger.warning(f"[REGISTRY] INTERCEPT AUTHORIZED for: {plate}")
        return updated

    def revoke_intercept(self, plate: str) -> bool:
        """Revoke intercept authorization."""
        plate = plate.upper().strip()
        with _lock, self._connect() as conn:
            cursor = conn.execute(
                "UPDATE flagged_vehicles SET intercept_authorized = 0 WHERE plate = ?",
                (plate,)
            )
            conn.commit()
            updated = cursor.rowcount > 0
        if updated:
            logger.info(f"[REGISTRY] Intercept revoked for: {plate}")
        return updated

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def lookup(self, plate: str) -> Optional[FlaggedVehicle]:
        """Return FlaggedVehicle if plate is in registry, else None."""
        plate = plate.upper().strip()
        with _lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM flagged_vehicles WHERE plate = ?", (plate,)
            ).fetchone()
        if row is None:
            return None
        return FlaggedVehicle(
            plate=row["plate"],
            flag_reason=row["flag_reason"],
            authority=row["authority"],
            flagged_at=row["flagged_at"],
            intercept_authorized=bool(row["intercept_authorized"]),
            notes=row["notes"],
        )

    def is_flagged(self, plate: str) -> bool:
        """Fast O(1) check: is this plate in the registry?"""
        return self.lookup(plate) is not None

    def is_intercept_authorized(self, plate: str) -> bool:
        """True only if plate is flagged AND intercept has been explicitly authorized."""
        entry = self.lookup(plate)
        return entry is not None and entry.intercept_authorized

    def all_flagged(self) -> list[FlaggedVehicle]:
        """Return all flagged vehicles."""
        with _lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM flagged_vehicles").fetchall()
        return [
            FlaggedVehicle(
                plate=r["plate"],
                flag_reason=r["flag_reason"],
                authority=r["authority"],
                flagged_at=r["flagged_at"],
                intercept_authorized=bool(r["intercept_authorized"]),
                notes=r["notes"],
            )
            for r in rows
        ]

    def seed_demo(self):
        """Seed registry with demo vehicles for SIH presentation."""
        demo_vehicles = [
            FlaggedVehicle(
                plate="UP32AB1234",
                flag_reason="suspect_surveillance",
                authority="Lucknow CP Office",
                intercept_authorized=False,
                notes="Person of interest in ongoing investigation",
            ),
            FlaggedVehicle(
                plate="UP32XY9999",
                flag_reason="stolen_vehicle",
                authority="UP Traffic Police",
                intercept_authorized=True,
                notes="Reported stolen 2026-10-20. Intercept on sight.",
            ),
            FlaggedVehicle(
                plate="UP41BC5678",
                flag_reason="wanted",
                authority="STF Lucknow",
                intercept_authorized=False,
                notes="Subject linked to highway robbery case",
            ),
        ]
        for v in demo_vehicles:
            self.add(v)
        logger.info("[REGISTRY] Demo seed complete: 3 vehicles loaded")
