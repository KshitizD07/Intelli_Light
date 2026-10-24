"""
sentinel/intercept/predictor.py
================================
Markov Transition Path Predictor.

Predicts the top-K most probable next intersections for a tracked vehicle
based on road topology transitions and recent vehicle heading.
"""

import os
import logging
from collections import defaultdict
from typing import List, Dict, Tuple, Optional

import sumolib
from sentinel.config import SUMO_NET_FILE
from sentinel.tracker.road_snapper import get_shared_sumo_net

logger = logging.getLogger(__name__)


class MarkovPathPredictor:
    """
    Builds a first-order Markov transition graph across network intersections.
    """

    def __init__(self, net_file: str = SUMO_NET_FILE):
        self.net_file = net_file
        self.transitions: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._init_topology()

    def _init_topology(self):
        """Seed transitions with uniform priors from physical road connectivity."""
        net = get_shared_sumo_net(self.net_file)
        if net is None:
            return
        try:
            for node in net.getNodes():
                src_id = node.getID()
                out_nodes = set()
                for edge in node.getOutgoing():
                    to_node = edge.getToNode()
                    if to_node:
                        out_nodes.add(to_node.getID())

                if out_nodes:
                    prob = 1.0 / len(out_nodes)
                    for dst_id in out_nodes:
                        self.transitions[src_id][dst_id] = prob
            logger.info(f"[MarkovPredictor] Initialized transition matrix for {len(self.transitions)} junctions")
        except Exception as e:
            logger.error(f"[MarkovPredictor] Topology init error: {e}")

    def update_transition(self, from_jid: str, to_jid: str, weight: float = 1.0):
        """Update transition count with observed vehicle movements."""
        self.transitions[from_jid][to_jid] += weight
        # Re-normalize
        total = sum(self.transitions[from_jid].values())
        if total > 0:
            for k in self.transitions[from_jid]:
                self.transitions[from_jid][k] /= total

    def predict_next_junctions(self, current_jid: str, top_k: int = 3) -> List[Tuple[str, float]]:
        """
        Returns the top-K predicted next intersections and their probabilities.
        """
        options = self.transitions.get(current_jid, {})
        if not options:
            return []
        sorted_options = sorted(options.items(), key=lambda item: item[1], reverse=True)
        return sorted_options[:top_k]

    def predict_escape_envelope(self, current_jid: str, hops: int = 2) -> List[str]:
        """
        Returns all candidate intersections within N hops where an intercept
        perimeter or red-wall should be established.
        """
        visited = set([current_jid])
        frontier = [current_jid]

        for _ in range(hops):
            next_frontier = []
            for jid in frontier:
                for nxt in self.transitions.get(jid, {}):
                    if nxt not in visited:
                        visited.add(nxt)
                        next_frontier.append(nxt)
            frontier = next_frontier

        visited.discard(current_jid)
        return list(visited)
