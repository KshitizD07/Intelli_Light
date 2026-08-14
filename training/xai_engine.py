"""
Explainable AI (XAI) Engine for Intelli-Light
==============================================

Provides human-readable reasoning for RL signal decisions.
Essential for liability audits and building trust with city engineers.

Maps the 20-dim ILPS observation space to "Feature Attribution" logs.
"""

import numpy as np
from typing import Dict, List, Any

class DecisionExplainer:
    """
    Analyzes RL observations and actions to generate natural language reasoning.
    """
    
    FEATURE_MAP = {
        0: "North Queue", 1: "South Queue", 2: "East Queue", 3: "West Queue",
        4: "North Delta", 5: "South Delta", 6: "East Delta", 7: "West Delta",
        8: "North Wait",  9: "South Wait",  10: "East Wait", 11: "West Wait",
        12: "Emergency Flag",
        13: "Current Phase",
        14: "Upstream Phase", 15: "Upstream Time",
        16: "Downstream Phase", 17: "Downstream Time",
        18: "Has Upstream", 19: "Has Downstream"
    }

    PHASE_NAMES = ["EW-Through", "EW-Left", "NS-Through", "NS-Left"]

    def __init__(self, queue_threshold: float = 0.5, wait_threshold: float = 0.5):
        self.queue_threshold = queue_threshold
        self.wait_threshold = wait_threshold

    def explain(self, observation: np.ndarray, action: int, duration: int) -> Dict[str, Any]:
        """
        Generate a reasoning report for a single decision.
        
        Args:
            observation: The 20-dim Box space
            action: The chosen duration index
            duration: The actual duration in seconds
            
        Returns:
            Reasoning dictionary
        """
        # Extract features
        queues = observation[0:4]
        deltas = observation[4:8]
        waits = observation[8:12]
        emergency = observation[12] > 0.5
        current_phase_idx = int(round(observation[13] * 3.0))
        
        reasons = []
        priority_level = "NORMAL"

        # 1. Check for Emergency (Highest Priority)
        if emergency:
            reasons.append("EMERGENCY VEHICLE DETECTED: Overriding for immediate clearance.")
            priority_level = "CRITICAL"

        # 2. Check for High Queues
        max_q_idx = np.argmax(queues)
        if queues[max_q_idx] > self.queue_threshold:
            dir_name = ["North", "South", "East", "West"][max_q_idx]
            reasons.append(f"High congestion on {dir_name} approach ({queues[max_q_idx]*100:.0f}% capacity).")
            priority_level = "HIGH"

        # 3. Check for Starvation (Long Waits)
        max_w_idx = np.argmax(waits)
        if waits[max_w_idx] > self.wait_threshold:
            dir_name = ["North", "South", "East", "West"][max_w_idx]
            reasons.append(f"Starvation risk: Vehicles on {dir_name} waiting > {waits[max_w_idx]*120:.0f}s.")
            priority_level = "HIGH"

        # 4. Phase-specific Logic
        phase_name = self.PHASE_NAMES[current_phase_idx]
        if duration > 30:
            reasons.append(f"Extended {phase_name} to clear accumulating cluster.")
        elif duration < 20:
            reasons.append(f"Shortened {phase_name} due to low demand/high pressure from cross-streets.")

        # 5. Coordination (ILPS specific)
        if observation[18] > 0.5 or observation[19] > 0.5:
            reasons.append("Coordinating with neighboring junctions to maintain green-wave.")

        return {
            "summary": " ".join(reasons) if reasons else "Standard flow optimization based on balanced pressure.",
            "priority": priority_level,
            "primary_driver": self.FEATURE_MAP[max_q_idx] if queues[max_q_idx] > waits[max_w_idx] else self.FEATURE_MAP[8+max_w_idx],
            "decision_metadata": {
                "phase": phase_name,
                "duration": duration,
                "max_queue": float(np.max(queues)),
                "max_wait": float(np.max(waits))
            }
        }

if __name__ == "__main__":
    # Test logic
    explainer = DecisionExplainer()
    mock_obs = np.zeros(20)
    mock_obs[3] = 0.8  # Heavy West queue
    mock_obs[13] = 0.0 # EW-Through phase
    
    report = explainer.explain(mock_obs, 5, 45)
    print(f"REASONING: {report['summary']}")
    print(f"PRIORITY: {report['priority']}")
    print(f"DRIVER: {report['driver']}")
