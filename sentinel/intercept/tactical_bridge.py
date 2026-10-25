"""
sentinel/intercept/tactical_bridge.py
======================================
Tactical Guidance & Signal Shaping Bridge.

Bridges Sentinel's InterceptOrchestrator to Intelli-Light's deployment controller
and traffic simulation. Instead of abruptly freezing vehicles by software fiat,
this module translates tactical containment directives into physical traffic
regulation strategies:

1. PROGRESSIVE METERING:
   Downstream green phase is throttled down to 10s (minimum safe green),
   creating a controlled civilian queue 200m ahead of the suspect.
   The suspect is kinematically forced to slow down via car-following physics.

2. TACTICAL CHOKE & FUNNEL:
   Suspect approach signal transitions to Red (honoring yellow intervals and
   pedestrian clearance), while cross-traffic or secondary diversions remain green.

3. STRICT SAFETY INVARIANTS:
   Every regulation plan respects pedestrian clearance (>= 15s), maximum red-hold
   (<= 120s), and emergency vehicle preemption (instant override).
"""

import time
import math
import logging
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

from sentinel.intercept.orchestrator import InterceptOrchestrator
from sentinel.intercept.failsafe_bridge import SentinelFailsafeBridge
from deployment.failsafe import SystemState

logger = logging.getLogger(__name__)


class TacticalStage(str, Enum):
    STANDBY = "STANDBY"
    METERING = "METERING"         # Throttle downstream green, induce 200m queue
    CHOKE = "CHOKE"               # Red light on suspect approach, flush cross-traffic
    FUNNEL = "FUNNEL"             # Keep diversion lane green, omit escape highway
    CONTAINMENT = "CONTAINMENT"   # Suspect fully boxed in by stopped civilian platoon


@dataclass
class TacticalDirective:
    mission_id: str
    target_plate: str
    target_junction: str
    stage: TacticalStage
    target_speed_mps: float
    metered_green_s: int = 10
    max_red_hold_s: int = 90
    pedestrian_clearance_s: int = 15
    active: bool = True
    evp_suspended: bool = False
    created_at: float = field(default_factory=time.time)


class TacticalGuidanceBridge:
    """
    Translates Sentinel intercept directives into Intelli-Light regulation plans
    and kinematic vehicle deceleration targets.
    """

    def __init__(
        self,
        orchestrator: InterceptOrchestrator,
        failsafe_bridge: Optional[SentinelFailsafeBridge] = None,
    ):
        self.orchestrator = orchestrator
        self.failsafe_bridge = failsafe_bridge or SentinelFailsafeBridge(orchestrator=orchestrator)
        logger.info("[TacticalGuidanceBridge] Initialized with failsafe invariants.")

    def get_directive(
        self,
        junction_id: str,
        plate: Optional[str] = None,
        distance_to_junction_m: float = 100.0,
        emergency_vehicle_present: bool = False,
    ) -> Optional[TacticalDirective]:
        """
        Determines the current tactical directive for a given junction.
        Evaluates emergency vehicle preemption and vehicle approach distance.
        """
        # Safety Priority 1: Emergency Vehicle Preemption
        if emergency_vehicle_present:
            logger.warning(
                f"[TacticalGuidance] EVP active at {junction_id}: intercept suspended for emergency priority."
            )
            return None

        overrides = self.orchestrator.get_signal_overrides()
        if junction_id not in overrides:
            return None

        ov = overrides[junction_id]
        target_plate = ov.get("target_plate", "")
        if plate and plate.upper().strip() != target_plate:
            return None  # Directive only targets the specific suspect vehicle

        mission_id = ov.get("mission_id", f"INT-{target_plate}")

        # Compute dynamic tactical stage based on approach distance
        if distance_to_junction_m > 250.0:
            stage = TacticalStage.METERING
            speed_target = 6.0  # ~21 km/h metered approach
        elif 60.0 < distance_to_junction_m <= 250.0:
            stage = TacticalStage.CHOKE
            speed_target = 2.5  # ~9 km/h crawl behind queue
        else:
            stage = TacticalStage.CONTAINMENT
            speed_target = 0.0  # Trapped behind queue

        # Bounded by failsafe invariants
        safe_hold = min(120, max(15, ov.get("hold_seconds", 90)))

        return TacticalDirective(
            mission_id=mission_id,
            target_plate=target_plate,
            target_junction=junction_id,
            stage=stage,
            target_speed_mps=speed_target,
            metered_green_s=10,
            max_red_hold_s=safe_hold,
            pedestrian_clearance_s=15,
        )

    def get_kinematic_target_speed(
        self,
        plate: str,
        next_junction: str,
        progress: float,
        base_speed_mps: float,
    ) -> Tuple[float, str]:
        """
        Calculates progressive physical deceleration for vehicles approaching
        a metered / queued intercept intersection.

        Returns:
            (target_speed_mps, guidance_status_string)
        """
        overrides = self.orchestrator.get_signal_overrides()
        if next_junction not in overrides:
            return base_speed_mps, "NORMAL_FLOW"

        ov = overrides[next_junction]
        if ov.get("target_plate") != plate.upper().strip():
            # Innocent civilian vehicle also slows down naturally at red light
            if progress >= 0.70:
                slowdown = max(0.0, 1.0 - (progress - 0.70) / 0.25)
                return base_speed_mps * slowdown, "CIVILIAN_QUEUE_WAIT"
            return base_speed_mps, "CIVILIAN_FLOW"

        # Suspect Vehicle Guidance Profile:
        # 1. progress < 0.35: Cruising normally toward corridor
        if progress < 0.35:
            return base_speed_mps, "APPROACHING_INTERCEPT_CORRIDOR"

        # 2. 0.35 <= progress < 0.70: Senses downstream metering & brake lights ahead
        if 0.35 <= progress < 0.70:
            ratio = (progress - 0.35) / (0.70 - 0.35)
            # Decelerate from base speed down to 5.0 m/s (~18 km/h)
            target_v = base_speed_mps - ratio * (base_speed_mps - 5.0)
            return round(max(5.0, target_v), 2), "TACTICAL_METERING_DECELERATION"

        # 3. 0.70 <= progress < 0.88: Bumper-to-bumper queue ahead, slowing to stop
        if 0.70 <= progress < 0.88:
            ratio = (progress - 0.70) / (0.88 - 0.70)
            target_v = 5.0 * (1.0 - ratio)
            return round(max(0.8, target_v), 2), "QUEUE_APPROACH_BRAKING"

        # 4. progress >= 0.88: Fully halted and contained behind civilian vehicle queue
        return 0.0, "CONTAINED_BEHIND_CIVILIAN_QUEUE"

    def compute_ntcip_plan(self, directive: TacticalDirective) -> Dict[str, Any]:
        """
        Generates standard NTCIP 1202 controller primitives for physical cabinets.
        """
        if directive.stage == TacticalStage.METERING:
            return {
                "phase_hold_mask": 0b00000000,
                "phase_force_off_mask": 0b00000001,  # Shorten phase 1
                "phase_omit_mask": 0b00000000,
                "split_seconds": directive.metered_green_s,
                "pedestrian_clearance_s": directive.pedestrian_clearance_s,
                "strategy": "METERED_APPROACH",
            }
        elif directive.stage in (TacticalStage.CHOKE, TacticalStage.CONTAINMENT):
            return {
                "phase_hold_mask": 0b00000010,       # Hold cross-traffic / pedestrian
                "phase_force_off_mask": 0b00000001,  # Terminate suspect phase
                "phase_omit_mask": 0b00000100,       # Omit escape corridor
                "split_seconds": directive.max_red_hold_s,
                "pedestrian_clearance_s": directive.pedestrian_clearance_s,
                "strategy": "TACTICAL_RED_WALL",
            }
        return {
            "phase_hold_mask": 0,
            "phase_force_off_mask": 0,
            "phase_omit_mask": 0,
            "split_seconds": 45,
            "pedestrian_clearance_s": directive.pedestrian_clearance_s,
            "strategy": "NORMAL_AI",
        }
