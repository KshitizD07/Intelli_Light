"""
Intelli-Light Adaptive Max-Pressure Traffic Signal Controller
============================================================

Dynamically regulates traffic signal phases across all junctions in the
Lucknow network based on real-time lane queue backlogs and vehicle waiting times.
Prevents congestion, clears gridlock, and seamlessly yields individual junctions
to Sentinel when tactical red-wall intercepts are authorized.
"""

from typing import Dict, Set, Optional, Tuple, List
import logging

logger = logging.getLogger("IntelliLightController")


class IntelliLightAdaptiveController:
    """
    Real-time adaptive Max-Pressure signal controller for TraCI networks.
    """

    def __init__(
        self,
        min_green: int = 8,
        max_green: int = 40,
        yellow_duration: int = 3,
        queue_weight: float = 2.5,
        wait_weight: float = 0.1,
    ):
        self.min_green = min_green
        self.max_green = max_green
        self.yellow_duration = yellow_duration
        self.queue_weight = queue_weight
        self.wait_weight = wait_weight

        # State tracking per TLS ID:
        # {
        #   "current_phase": int,
        #   "duration": int,
        #   "is_yellow": bool,
        #   "target_phase": int,
        #   "phases": list,
        #   "links": list
        # }
        self.tls_states: Dict[str, dict] = {}
        self.total_queue_cleared: int = 0
        self.optimizations_count: int = 0

    def step(self, traci_module, overridden_tls: Optional[Set[str]] = None) -> List[str]:
        """
        Executes one step of adaptive traffic signal regulation.
        Returns a list of human-readable log messages describing active optimizations.
        """
        overridden = overridden_tls or set()
        logs: List[str] = []

        try:
            all_tls = traci_module.trafficlight.getIDList()
        except Exception:
            return logs

        for tid in all_tls:
            # Yield this junction if Sentinel has tactical command of it
            if tid in overridden:
                # Reset local state so it safely re-syncs when Sentinel releases
                if tid in self.tls_states:
                    self.tls_states.pop(tid, None)
                continue

            # Initialize junction tracking if not cached
            if tid not in self.tls_states:
                try:
                    logics = traci_module.trafficlight.getAllProgramLogics(tid)
                    if not logics or not logics[0].phases:
                        continue
                    current_p = traci_module.trafficlight.getPhase(tid)
                    links = traci_module.trafficlight.getControlledLinks(tid)
                    self.tls_states[tid] = {
                        "current_phase": current_p,
                        "duration": 0,
                        "is_yellow": False,
                        "target_phase": current_p,
                        "phases": logics[0].phases,
                        "links": links,
                    }
                except Exception:
                    continue

            st = self.tls_states[tid]
            st["duration"] += 1

            # Handle yellow transition completion
            if st["is_yellow"]:
                if st["duration"] >= self.yellow_duration:
                    st["current_phase"] = st["target_phase"]
                    st["is_yellow"] = False
                    st["duration"] = 0
                    try:
                        traci_module.trafficlight.setPhase(tid, st["current_phase"])
                    except Exception:
                        pass
                continue

            # Respect minimum green duration
            if st["duration"] < self.min_green:
                continue

            # Calculate pressure for every controlled link
            phases = st["phases"]
            links = st["links"]
            link_pressure = {}

            max_halting_seen = 0
            for l_idx, link_list in enumerate(links):
                pressure = 0.0
                for incoming_lane, _, _ in link_list:
                    try:
                        q = traci_module.lane.getLastStepHaltingNumber(incoming_lane)
                        w = traci_module.lane.getWaitingTime(incoming_lane)
                        if q > max_halting_seen:
                            max_halting_seen = q
                        pressure += q * self.queue_weight + w * self.wait_weight
                    except Exception:
                        pass
                link_pressure[l_idx] = pressure

            # Score each available green phase
            best_phase = st["current_phase"]
            max_score = -1.0

            for p_idx, phase_obj in enumerate(phases):
                state_str = phase_obj.state
                # Only consider green phases
                if "G" not in state_str and "g" not in state_str:
                    continue

                score = 0.0
                for l_idx, char in enumerate(state_str):
                    if char in ("G", "g"):
                        score += link_pressure.get(l_idx, 0.0)

                if score > max_score:
                    max_score = score
                    best_phase = p_idx

            force_switch = st["duration"] >= self.max_green and best_phase != st["current_phase"]

            # Trigger phase switch if higher backlog detected or max green reached
            if (best_phase != st["current_phase"] and max_score > 2.0) or force_switch:
                # Find intermediate yellow phase if available
                yellow_idx = (st["current_phase"] + 1) % len(phases)
                has_yellow = "y" in phases[yellow_idx].state

                if has_yellow:
                    st["current_phase"] = yellow_idx
                    st["target_phase"] = best_phase
                    st["is_yellow"] = True
                    st["duration"] = 0
                    try:
                        traci_module.trafficlight.setPhase(tid, yellow_idx)
                    except Exception:
                        pass
                else:
                    st["current_phase"] = best_phase
                    st["duration"] = 0
                    try:
                        traci_module.trafficlight.setPhase(tid, best_phase)
                    except Exception:
                        pass

                self.optimizations_count += 1
                if max_halting_seen > 0:
                    self.total_queue_cleared += max_halting_seen
                    logs.append(
                        f"[INTELLI-LIGHT ADAPTIVE] TLS {tid[:18]} -> Phase {best_phase} "
                        f"(Cleared {max_halting_seen} queued vehicles | Pressure {max_score:.1f})"
                    )

        return logs
