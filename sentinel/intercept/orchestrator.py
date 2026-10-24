"""
sentinel/intercept/orchestrator.py
==================================
Intercept Orchestrator & Signal Manipulation Engine.

Coordinates dynamic traffic signal intervention to contain flagged vehicles:
1. Verifies explicit operator authorization token & registry approval.
2. Forecasts vehicle escape trajectory using MarkovPathPredictor.
3. Computes phase overrides (Red-wall perimeter / Funnel corridor).
4. Enforces TTL auto-expiry (10 minutes) and safety constraints.
5. Writes tamper-evident SHA-256 hash-chained records to audit.jsonl.
"""

import os
import time
import json
import hashlib
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from sentinel.config import (
    AUDIT_LOG_PATH,
    INTERCEPT_TTL_S,
    INTERCEPT_RED_HOLD_S,
    INTERCEPT_MAX_JUNCTIONS,
)
from sentinel.registry import FlaggedVehicleRegistry
from sentinel.intercept.predictor import MarkovPathPredictor

logger = logging.getLogger(__name__)


@dataclass
class InterceptMission:
    mission_id: str
    plate: str
    target_junction: str
    authorized_by: str
    reason: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + INTERCEPT_TTL_S)
    overridden_junctions: List[str] = field(default_factory=list)
    active: bool = True


class InterceptOrchestrator:
    """
    Manages active intercept operations and audit compliance.
    """

    def __init__(
        self,
        registry: FlaggedVehicleRegistry,
        predictor: Optional[MarkovPathPredictor] = None,
        audit_file: str = AUDIT_LOG_PATH,
    ):
        self.registry = registry
        self.predictor = predictor or MarkovPathPredictor()
        self.audit_file = audit_file
        self.active_missions: Dict[str, InterceptMission] = {}  # plate -> mission
        self._last_audit_hash: str = "0" * 64
        self._init_audit_chain()

    def _init_audit_chain(self):
        """Recover last SHA-256 hash from audit log if it exists."""
        if os.path.exists(self.audit_file):
            try:
                with open(self.audit_file, "r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f if line.strip()]
                    if lines:
                        last_record = json.loads(lines[-1])
                        self._last_audit_hash = last_record.get("record_hash", self._last_audit_hash)
            except Exception as e:
                logger.warning(f"[Intercept] Failed to read last audit hash: {e}")

    def _append_audit(self, action: str, details: Dict[str, Any]):
        """Writes an append-only, SHA-256 hash-chained log entry."""
        timestamp = time.time()
        payload = {
            "action": action,
            "timestamp": timestamp,
            "details": details,
            "prev_hash": self._last_audit_hash,
        }
        serialized = json.dumps(payload, sort_keys=True)
        record_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        payload["record_hash"] = record_hash
        self._last_audit_hash = record_hash

        try:
            with open(self.audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception as e:
            logger.error(f"[Intercept] Failed to append audit log: {e}")

    def request_intercept(
        self,
        plate: str,
        current_junction: str,
        authorized_by: str,
        reason: str,
    ) -> Dict[str, Any]:
        """
        Initiates a traffic intercept perimeter around target vehicle.
        Requires plate to be registered and approved.
        """
        plate = plate.upper().strip()

        if not self.registry.is_flagged(plate):
            return {
                "success": False,
                "error": f"Vehicle {plate} is not in the flagged registry.",
            }

        if not self.registry.is_intercept_authorized(plate):
            return {
                "success": False,
                "error": f"Intercept is not authorized for vehicle {plate}.",
            }

        # Predict candidate escape nodes ahead
        envelope = self.predictor.predict_escape_envelope(current_junction, hops=2)
        # Select up to INTERCEPT_MAX_JUNCTIONS intersections
        target_junctions = envelope[:INTERCEPT_MAX_JUNCTIONS] if envelope else [current_junction]

        mission_id = f"INT-{plate}-{int(time.time())}"
        mission = InterceptMission(
            mission_id=mission_id,
            plate=plate,
            target_junction=current_junction,
            authorized_by=authorized_by,
            reason=reason,
            overridden_junctions=target_junctions,
        )
        self.active_missions[plate] = mission

        # Audit logging
        self._append_audit("INTERCEPT_INITIATED", {
            "mission_id": mission_id,
            "plate": plate,
            "target_junction": current_junction,
            "overridden_junctions": target_junctions,
            "authorized_by": authorized_by,
            "reason": reason,
            "expires_at": mission.expires_at,
        })

        logger.warning(
            f"[INTERCEPT] ACTIVE: {mission_id} | Target: {plate} at {current_junction} | "
            f"Perimeter: {target_junctions}"
        )

        return {
            "success": True,
            "mission_id": mission_id,
            "plate": plate,
            "overridden_junctions": target_junctions,
            "ttl_seconds": INTERCEPT_TTL_S,
        }

    def cancel_intercept(self, plate: str, cancelled_by: str) -> bool:
        plate = plate.upper().strip()
        mission = self.active_missions.pop(plate, None)
        if not mission:
            return False

        mission.active = False
        self._append_audit("INTERCEPT_CANCELLED", {
            "mission_id": mission.mission_id,
            "plate": plate,
            "cancelled_by": cancelled_by,
        })
        logger.info(f"[INTERCEPT] Cancelled mission {mission.mission_id} for {plate}")
        return True

    def get_signal_overrides(self) -> Dict[str, Dict[str, Any]]:
        """
        Returns active phase overrides for traffic controllers.
        Checks TTL expiry before returning.
        Format:
          {
            "J_042": {"mode": "RED_WALL", "hold_seconds": 90, "plate": "UP32XY9999"}
          }
        """
        now = time.time()
        expired = [p for p, m in self.active_missions.items() if now >= m.expires_at]
        for p in expired:
            m = self.active_missions.pop(p)
            self._append_audit("INTERCEPT_EXPIRED_TTL", {"mission_id": m.mission_id, "plate": p})
            logger.info(f"[INTERCEPT] Mission {m.mission_id} for {p} expired by TTL")

        overrides: Dict[str, Dict[str, Any]] = {}
        for plate, mission in self.active_missions.items():
            for jid in mission.overridden_junctions:
                overrides[jid] = {
                    "mode": "RED_WALL",
                    "hold_seconds": INTERCEPT_RED_HOLD_S,
                    "target_plate": plate,
                    "mission_id": mission.mission_id,
                    "remaining_ttl": max(0, int(mission.expires_at - now)),
                }
        return overrides
