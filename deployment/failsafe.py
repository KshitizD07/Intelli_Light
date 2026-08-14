"""
Safety Failsafe Engine for Real-World Deployment
=================================================

This module implements a Watchdog state machine designed to intercept
RL actions before they reach the physical controller. It ensures that
strict safety invariants are never violated.

Modes:
- NORMAL: AI control is active and healthy.
- FALLBACK_SOFT: Reverting to fixed-timer due to inference lag or minor anomaly.
- FALLBACK_HARD: System in critical failure (e.g. comms loss); forcing flashing yellow/red.
"""

import time
import logging
from enum import Enum
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class SystemState(Enum):
    NORMAL = "NORMAL"
    FALLBACK_SOFT = "FALLBACK_SOFT"  # Revert to fixed-time schedule
    FALLBACK_HARD = "FALLBACK_HARD"  # Revert to flashing hardware mode

class FailsafeWatchdog:
    """
    Monitors system health and AI decisions to prevent unsafe traffic conditions.
    """
    
    def __init__(
        self, 
        max_inference_latency: float = 0.5,  # seconds
        max_queue_threshold: int = 150,      # vehicles
        max_wait_threshold: int = 120,       # seconds
        heartbeat_timeout: float = 2.0       # seconds
    ):
        self.max_inference_latency = max_inference_latency
        self.max_queue_threshold = max_queue_threshold
        self.max_wait_threshold = max_wait_threshold
        self.heartbeat_timeout = heartbeat_timeout
        
        self.current_state = SystemState.NORMAL
        self.last_heartbeat = time.time()
        self.violation_history = []
        
        logger.info(f"FailsafeWatchdog initialized. Mode: {self.current_state.name}")

    def ping(self):
        """Update the heartbeat timestamp. Must be called by main loop."""
        self.last_heartbeat = time.time()
        if self.current_state == SystemState.FALLBACK_HARD:
            logger.info("Heartbeat restored. Attempting to clear HARD fallback... Requires manual reset.")

    def check_health(self) -> SystemState:
        """
        Evaluate current health based on heartbeat.
        If heartbeat is lost, trigger FALLBACK_HARD immediately.
        """
        time_since_ping = time.time() - self.last_heartbeat
        if time_since_ping > self.heartbeat_timeout:
            self._trigger_fallback(
                SystemState.FALLBACK_HARD, 
                f"Heartbeat lost for {time_since_ping:.2f}s (Threshold: {self.heartbeat_timeout}s)"
            )
        return self.current_state

    def validate_action(
        self, 
        duration: int, 
        inference_latency: float, 
        obs_snapshot: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Validate an AI action before sending to the controller.
        
        Args:
            duration: The requested green duration in seconds.
            inference_latency: How long it took the model to predict.
            obs_snapshot: Context about the current intersection state.
            
        Returns:
            int: The safe duration to apply (may be overridden).
        """
        # 1. Check Heartbeat
        if self.check_health() == SystemState.FALLBACK_HARD:
            return -1  # Indicates hardware override required

        # 2. Check Latency
        if inference_latency > self.max_inference_latency:
            self._trigger_fallback(
                SystemState.FALLBACK_SOFT,
                f"Inference latency {inference_latency:.3f}s exceeded threshold {self.max_inference_latency}s"
            )

        # 3. Check State Anomalies (if observation provided)
        if obs_snapshot:
            max_q = max(obs_snapshot.get('queues', [0]))
            max_w = max(obs_snapshot.get('waits', [0]))
            
            if max_q > self.max_queue_threshold:
                self._trigger_fallback(
                    SystemState.FALLBACK_SOFT,
                    f"Queue anomaly detected: {max_q} > {self.max_queue_threshold}"
                )
                
            if max_w > self.max_wait_threshold:
                logger.warning(f"Wait time threshold exceeded ({max_w}s). Forcing minimum clearance.")
                return max(duration, 45) # Force at least 45s to clear the starvation

        # If we are in soft fallback, we override the AI with a safe default
        if self.current_state == SystemState.FALLBACK_SOFT:
            return 30  # Standard 30s fixed-timer fallback

        return duration

    def _trigger_fallback(self, new_state: SystemState, reason: str):
        """Transition system state and log the violation."""
        if self.current_state != new_state:
            logger.error(f"FAILSAFE TRIGGERED [{new_state.name}]: {reason}")
            self.current_state = new_state
            self.violation_history.append({
                "time": time.time(),
                "state": new_state.name,
                "reason": reason
            })

    def manual_reset(self):
        """Allows human operator to clear fallbacks via Dashboard."""
        logger.info("Failsafe manually reset to NORMAL.")
        self.current_state = SystemState.NORMAL
        self.last_heartbeat = time.time()

if __name__ == "__main__":
    # Simple test
    logging.basicConfig(level=logging.INFO)
    wd = FailsafeWatchdog(max_inference_latency=0.5)
    
    # Normal behavior
    wd.ping()
    safe_dur = wd.validate_action(20, inference_latency=0.1)
    assert safe_dur == 20
    
    # Latency anomaly -> Soft Fallback
    safe_dur = wd.validate_action(20, inference_latency=0.6)
    assert safe_dur == 30 # Overridden
    assert wd.current_state == SystemState.FALLBACK_SOFT
    
    # Heartbeat loss -> Hard Fallback
    time.sleep(2.1)
    safe_dur = wd.validate_action(20, inference_latency=0.1)
    assert safe_dur == -1
    assert wd.current_state == SystemState.FALLBACK_HARD
