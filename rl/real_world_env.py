import gymnasium as gym
from gymnasium import spaces
import numpy as np
from collections import deque

class RealWorldMARLEnv(gym.Env):
    """
    Real-World Friendly Multi-Agent Traffic Environment.
    
    Features:
    1. Independent Learning (MARL) - each agent observes its N-hop local graph.
    2. Spatio-Temporal: Observation includes the last T timesteps (LSTM ready).
    3. Backpressure Reward: Optimizes for throughput (Surtrac killer).
    4. Real-world constraints: 
       - Minimum 15s green time (prevents flickering).
       - Emergency Vehicle absolute priority.
       - Deterministic Starvation Failsafe (90s limit).
    """
    def __init__(self, n_neighbors=4, seq_len=5, min_green=15.0, failsafe_time=90.0):
        super(RealWorldMARLEnv, self).__init__()
        
        self.n_nodes = n_neighbors + 1 # Ego + Neighbors
        self.seq_len = seq_len
        self.min_green = min_green
        self.failsafe_time = failsafe_time
        
        # Feature vector: [Queue, Wait, EV_Present, Phase_Active, Time_Since_Switch]
        self.feature_dim = 5 
        
        # Action: Continuous stream pressure weights (e.g., 4 valid streams/phases)
        self.n_streams = 4
        self.action_space = spaces.Box(low=0.0, high=1.0, shape=(self.n_streams,), dtype=np.float32)
        
        # Observation: Temporal Graph
        self.observation_space = spaces.Dict({
            "temporal_graph": spaces.Box(
                low=-1.0, high=1.0, 
                shape=(self.seq_len, self.n_nodes, self.feature_dim), 
                dtype=np.float32
            ),
            "adjacency": spaces.Box(
                low=0.0, high=1.0, 
                shape=(self.n_nodes, self.n_nodes), 
                dtype=np.float32
            )
        })
        
        self.history = deque(maxlen=self.seq_len)
        self.current_phase = 0
        self.time_in_phase = 0.0
        
    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.current_phase = 0
        self.time_in_phase = 0.0
        
        # Fill history buffer with zeros
        for _ in range(self.seq_len):
            self.history.append(np.zeros((self.n_nodes, self.feature_dim), dtype=np.float32))
            
        return self._get_obs(), {}

    def _get_obs(self):
        # Mocking incoming Traci data for ego and neighbors
        current_state = np.random.uniform(0, 1, size=(self.n_nodes, self.feature_dim)).astype(np.float32)
        self.history.append(current_state)
        
        # Local star topology (Ego at index 0, connected to all neighbors)
        adj = np.zeros((self.n_nodes, self.n_nodes), dtype=np.float32)
        adj[0, 1:] = 1.0
        adj[1:, 0] = 1.0
        np.fill_diagonal(adj, 1.0)
        
        temporal_graph = np.stack(list(self.history), axis=0)
        
        return {
            "temporal_graph": temporal_graph,
            "adjacency": adj
        }

    def step(self, action: np.ndarray):
        # 1. Evaluate Constraints (Real-World Rules)
        
        # Fake local state for logic evaluation
        max_wait = np.random.uniform(0, 100) # Mock wait time
        ev_present = np.random.choice([True, False], p=[0.05, 0.95]) # 5% chance of EV
        
        info = {"override": False, "reason": ""}
        
        if self.time_in_phase < self.min_green:
            # Absolute Min Green Time Lock (Prevent crashes & sudden braking)
            chosen_phase = self.current_phase
            info["override"] = True
            info["reason"] = "MIN_GREEN_LOCK"
            
        elif ev_present:
            # Absolute Priority for Emergency Vehicles (Once safe to switch)
            chosen_phase = 0 # Assume phase 0 is the EV's path
            info["override"] = True
            info["reason"] = "EV_PREEMPTION"
            
        elif max_wait >= self.failsafe_time:
            # Deterministic Starvation Failsafe
            chosen_phase = 1 # Assume phase 1 is the starving lane
            info["override"] = True
            info["reason"] = "STARVATION_FAILSAFE"
            
        else:
            # GNN Optimization
            chosen_phase = int(np.argmax(action))
            
        # Update phase tracking
        if chosen_phase == self.current_phase:
            self.time_in_phase += 5.0 # Assuming 5s step
        else:
            self.current_phase = chosen_phase
            self.time_in_phase = 0.0
            
        # 2. Backpressure Reward Calculation (Surtrac Killer)
        # Reward = (Queue incoming) - (Queue outgoing) -> Maximize flow
        incoming_q = np.random.uniform(10, 50)
        outgoing_q = np.random.uniform(0, 30)
        pressure = incoming_q - outgoing_q
        
        # The agent is rewarded for releasing pressure (pushing traffic out)
        reward = float(pressure)
        
        obs = self._get_obs()
        done = False
        
        return obs, reward, done, False, info
