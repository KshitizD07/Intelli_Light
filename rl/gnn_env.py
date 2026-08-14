import gymnasium as gym
from gymnasium import spaces
import numpy as np
from typing import Dict, Any, List

class GraphTrafficEnv(gym.Env):
    """
    Graph Neural Network (GNN) Traffic Environment with Deterministic Failsafe.
    
    This environment represents the city as a graph:
    - Nodes: Intersections
    - Edges: Roads connecting them
    
    Action Space: Continuous weights for traffic streams (dynamic phase generation).
    Observation Space: Dict containing node_features and adjacency_matrix.
    """
    
    metadata = {"render_modes": ["human"]}
    
    def __init__(self, n_junctions: int = 5, failsafe_threshold: float = 90.0):
        super(GraphTrafficEnv, self).__init__()
        self.n_junctions = n_junctions
        self.failsafe_threshold = failsafe_threshold  # in seconds
        
        # 26-dim features as previously defined, but represented as a node matrix
        self.feature_dim = 26 
        
        # Action space: Priority weights for 4 streams per junction
        # E.g., [N-S through, N-S left, E-W through, E-W left]
        self.n_streams = 4
        self.action_space = spaces.Box(
            low=0.0, high=1.0, 
            shape=(self.n_junctions * self.n_streams,), 
            dtype=np.float32
        )
        
        # Observation space: Graph structure
        self.observation_space = spaces.Dict({
            "node_features": spaces.Box(
                low=-1.0, high=1.0, 
                shape=(self.n_junctions, self.feature_dim), 
                dtype=np.float32
            ),
            "adjacency": spaces.Box(
                low=0.0, high=1.0, 
                shape=(self.n_junctions, self.n_junctions), 
                dtype=np.float32
            )
        })
        
        # Internal state mock
        self.current_waits = np.zeros((self.n_junctions, self.n_streams))
        self.adjacency_matrix = self._build_mock_topology()
        
    def _build_mock_topology(self) -> np.ndarray:
        """Create a mock adjacency matrix (e.g., a line or star topology)."""
        adj = np.zeros((self.n_junctions, self.n_junctions), dtype=np.float32)
        # Simple line topology: 0-1-2-3-4
        for i in range(self.n_junctions - 1):
            adj[i, i+1] = 1.0
            adj[i+1, i] = 1.0
        return adj

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.current_waits = np.zeros((self.n_junctions, self.n_streams))
        return self._get_obs(), {}

    def _get_obs(self) -> Dict[str, np.ndarray]:
        # Mock node features (waits, queues, etc.)
        # In a real setup, this pulls from traci
        node_features = np.random.uniform(-0.1, 0.1, size=(self.n_junctions, self.feature_dim)).astype(np.float32)
        
        # Inject wait times into features for realism
        for i in range(self.n_junctions):
            # assume index 8:12 are wait times
            node_features[i, 8:12] = self.current_waits[i] / 120.0 
            
        return {
            "node_features": node_features,
            "adjacency": self.adjacency_matrix
        }
        
    def step(self, action: np.ndarray):
        # 1. Check for Failsafe / Reflex override
        # The Manifesto states: if max_wait_time >= 90_SECONDS, trigger failsafe
        
        final_actions = action.reshape(self.n_junctions, self.n_streams)
        override_flags = [False] * self.n_junctions
        
        for j in range(self.n_junctions):
            max_wait_idx = np.argmax(self.current_waits[j])
            if self.current_waits[j, max_wait_idx] >= self.failsafe_threshold:
                # ── The Reflex (Deterministic Failsafe) ──
                # Override the GNN's predicted weights. Force max priority to starving stream.
                final_actions[j] = 0.0
                final_actions[j, max_wait_idx] = 1.0
                override_flags[j] = True
                
        # 2. Simulate traffic (Mock update)
        # Streams with highest weights reduce their wait times. Others increase.
        for j in range(self.n_junctions):
            chosen_stream = np.argmax(final_actions[j])
            self.current_waits[j] += np.random.uniform(1.0, 5.0, size=self.n_streams)
            self.current_waits[j, chosen_stream] = 0.0 # Clear the queue
            
        # 3. Calculate Reward
        # Penalty for high wait times
        reward = -np.sum(self.current_waits) / (self.n_junctions * self.n_streams)
        
        # 4. Info dict (useful for dashboard/telemetry)
        info = {
            "failsafe_active": any(override_flags),
            "failsafe_nodes": [j for j, overridden in enumerate(override_flags) if overridden],
            "max_waits": np.max(self.current_waits, axis=1).tolist()
        }
        
        return self._get_obs(), reward, False, False, info
