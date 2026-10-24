"""
sentinel/intercept/failsafe_bridge.py
======================================
Failsafe Watchdog & Emergency Preemption Bridge.

Bridges Sentinel's InterceptOrchestrator to Intelli-Light's deployment/failsafe.py
FailsafeWatchdog. Enforces strict safety envelopes during active vehicle intercept:
1. Emergency Vehicle Preemption (Ambulance / Fire) ALWAYS overrides suspect interception.
2. Pedestrian minimum clearance intervals are strictly preserved.
3. Maximum red-hold duration invariants are enforced to prevent gridlock.
4. Auto-reverts to Intelli-Light normal AI / watchdog schedule if intercept TTL expires.
"""

import time
import logging
from typing import Dict, Any, Optional

from deployment.failsafe import FailsafeWatchdog, SystemState
from sentinel.intercept.orchestrator import InterceptOrchestrator

logger = logging.getLogger(__name__)


class SentinelFailsafeBridge:
    """
    Combines Intelli-Light's physical watchdog with Sentinel's tactical intercept directives.
    """

    def __init__(
        self,
        watchdog: Optional[FailsafeWatchdog] = None,
        orchestrator: Optional[InterceptOrchestrator] = None,
        max_red_hold_s: int = 120,
        min_pedestrian_clearance_s: int = 15,
    ):
        self.watchdog = watchdog or FailsafeWatchdog()
        self.orchestrator = orchestrator
        self.max_red_hold_s = max_red_hold_s
        self.min_pedestrian_clearance_s = min_pedestrian_clearance_s

    def resolve_action(
        self,
        junction_id: str,
        requested_duration: int,
        inference_latency: float,
        obs_snapshot: Optional[Dict[str, Any]] = None,
        emergency_vehicle_present: bool = False,
    ) -> Dict[str, Any]:
        """
        Determines the safe signal phase duration considering AI action,
        failsafe health, active suspect intercept overrides, and emergency vehicles.

        Returns:
            dict containing:
              - duration: int (seconds)
              - mode: 'NORMAL_AI' | 'INTERCEPT_OVERRIDE' | 'EMERGENCY_PREEMPT' | 'WATCHDOG_FALLBACK'
              - reason: str
        """
        # Priority 1: Emergency Vehicle Preemption
        if emergency_vehicle_present:
            logger.warning(
                f"[FailsafeBridge] EMERGENCY VEHICLE DETECTED at {junction_id}. "
                "Suspending intercept overrides and granting immediate green wave."
            )
            return {
                "duration": 45,
                "mode": "EMERGENCY_PREEMPT",
                "reason": "Emergency vehicle priority clearance",
            }

        # Priority 2: Physical Hardware / Latency Watchdog
        watchdog_duration = self.watchdog.validate_action(
            duration=requested_duration,
            inference_latency=inference_latency,
            obs_snapshot=obs_snapshot,
        )

        if self.watchdog.current_state != SystemState.NORMAL:
            return {
                "duration": watchdog_duration,
                "mode": "WATCHDOG_FALLBACK",
                "reason": f"Watchdog state {self.watchdog.current_state.name}",
            }

        # Priority 3: Sentinel Intercept Override
        if self.orchestrator:
            active_overrides = self.orchestrator.get_signal_overrides()
            if junction_id in active_overrides:
                override = active_overrides[junction_id]
                # Enforce safety cap on hold duration
                applied_hold = min(self.max_red_hold_s, override.get("hold_seconds", 90))
                # Ensure minimum pedestrian time is respected
                applied_hold = max(self.min_pedestrian_clearance_s, applied_hold)

                return {
                    "duration": applied_hold,
                    "mode": "INTERCEPT_OVERRIDE",
                    "reason": f"Suspect {override.get('target_plate')} perimeter lock (Mission: {override.get('mission_id')})",
                }

        # Priority 4: Normal AI action
        return {
            "duration": watchdog_duration,
            "mode": "NORMAL_AI",
            "reason": "Optimal AI adaptive signal schedule",
        }
