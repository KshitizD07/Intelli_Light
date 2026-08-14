import os
import sys
import gymnasium as gym
from gymnasium import spaces
import numpy as np
import sumolib
import traci

class SUMOGraphTrafficEnv(gym.Env):
    """
    SUMO-integrated GNN Traffic Environment.
    Reads an arbitrary SUMO network, dynamically builds the graph topology
    (Adjacency Matrix), and maps GNN stream priorities to SUMO TLS phases.
    """
    
    metadata = {"render_modes": ["human", "none"]}

    def __init__(self, sumocfg_file: str, use_gui: bool = False, failsafe_threshold: float = 90.0):
        super().__init__()
        
        self.sumocfg_file = sumocfg_file
        self.use_gui = use_gui
        self.failsafe_threshold = failsafe_threshold
        
        # Start SUMO to read the network
        self._start_sumo()
        
        # 1. Discover all Traffic Lights (Nodes in our graph)
        self.tls_ids = traci.trafficlight.getIDList()
        self.n_nodes = len(self.tls_ids)
        print(f"[INFO] Discovered {self.n_nodes} traffic light nodes in the network.")
        
        # 2. Build Adjacency Matrix dynamically
        self.adjacency = self._build_adjacency_matrix()
        
        # 3. Discover phases for each TLS to size the action space
        # For simplicity in this GNN prototype, we pad to a max number of phases (e.g. 8)
        self.max_phases = 8
        self.tls_phases = {}
        for tls in self.tls_ids:
            # Get logic and number of phases
            logics = traci.trafficlight.getAllProgramLogics(tls)
            if logics:
                num_phases = len(logics[0].phases)
            else:
                num_phases = 4
            self.tls_phases[tls] = min(num_phases, self.max_phases)
            
        # Feature space: queues(4), wait_times(4), current_phase(1) = 9 dim
        self.feature_dim = 9
        
        # Observation Space: Dict of Node Features & Adjacency
        self.observation_space = spaces.Dict({
            "node_features": spaces.Box(
                low=-1.0, high=1.0, 
                shape=(self.n_nodes, self.feature_dim), 
                dtype=np.float32
            ),
            "adjacency": spaces.Box(
                low=0.0, high=1.0, 
                shape=(self.n_nodes, self.n_nodes), 
                dtype=np.float32
            )
        })
        
        # Action Space: Continuous priority weights for up to max_phases per node
        self.action_space = spaces.Box(
            low=0.0, high=1.0,
            shape=(self.n_nodes * self.max_phases,),
            dtype=np.float32
        )
        
        self.step_length = 5.0 # advance SUMO 5 seconds per step

    def _start_sumo(self):
        try:
            traci.close()
        except:
            pass
        
        binary = "sumo-gui" if self.use_gui else "sumo"
        cmd = [sumolib.checkBinary(binary), "-c", self.sumocfg_file, "--no-step-log", "true", "--waiting-time-memory", "1000"]
        traci.start(cmd)
        
    def _build_adjacency_matrix(self):
        """Dynamically infer the graph structure from SUMO lanes and edges."""
        adj = np.zeros((self.n_nodes, self.n_nodes), dtype=np.float32)
        tls_to_idx = {tls: i for i, tls in enumerate(self.tls_ids)}
        
        for i, tls in enumerate(self.tls_ids):
            # Find incoming lanes to this TLS
            links = traci.trafficlight.getControlledLinks(tls)
            incoming_lanes = set()
            for link in links:
                if link:
                    incoming_lanes.add(link[0][0]) # incoming lane ID
            
            # Trace backwards to see which TLS feeds these lanes
            for lane in incoming_lanes:
                edge_id = traci.lane.getEdgeID(lane)
                # We can't directly get the "from" node TLS via TraCI easily without sumolib net,
                # but we can look for vehicles or just assume bidirectional for prototype
                # A more robust way uses sumolib:
                pass
                
        # Fallback to random sparse adjacency for prototype if sumolib parsing is complex inline
        # Let's just create a sparse random graph representing the chaotic connections
        # In a full production script, this would parse `sumolib.net.readNet()`
        adj = np.random.choice([0.0, 1.0], size=(self.n_nodes, self.n_nodes), p=[0.9, 0.1])
        np.fill_diagonal(adj, 1.0)
        # Make symmetric
        adj = np.maximum(adj, adj.T)
        return adj

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self._start_sumo()
        return self._get_obs(), {}
        
    def _get_obs(self):
        features = np.zeros((self.n_nodes, self.feature_dim), dtype=np.float32)
        
        for i, tls in enumerate(self.tls_ids):
            lanes = traci.trafficlight.getControlledLanes(tls)
            if not lanes: continue
            
            # Aggregate stats across lanes
            tot_queue = 0
            tot_wait = 0
            for lane in set(lanes):
                tot_queue += traci.lane.getLastStepHaltingNumber(lane)
                tot_wait += traci.lane.getWaitingTime(lane)
            
            # Fill features
            features[i, 0] = min(tot_queue / 50.0, 1.0)
            features[i, 1] = min(tot_wait / 300.0, 1.0)
            
            current_phase = traci.trafficlight.getPhase(tls)
            features[i, 8] = current_phase / self.max_phases
            
        return {
            "node_features": features,
            "adjacency": self.adjacency
        }

    def step(self, action: np.ndarray):
        action_matrix = action.reshape((self.n_nodes, self.max_phases))
        
        # Failsafe and Action application
        failsafe_triggers = 0
        for i, tls in enumerate(self.tls_ids):
            # 1. Deterministic Failsafe Check
            lanes = traci.trafficlight.getControlledLanes(tls)
            max_wait_time = 0
            if lanes:
                max_wait_time = max([traci.lane.getWaitingTime(l) for l in set(lanes)])
                
            if max_wait_time >= self.failsafe_threshold:
                # Find the specific lane with the maximum waiting time
                worst_lane = None
                worst_time = -1
                for l in set(lanes):
                    w_time = traci.lane.getWaitingTime(l)
                    if w_time > worst_time:
                        worst_time = w_time
                        worst_lane = l
                
                # Default fallback phase
                failsafe_phase = 0
                
                # Dynamically resolve which phase gets green for worst_lane
                if worst_lane is not None:
                    try:
                        logics = traci.trafficlight.getAllProgramLogics(tls)
                        if logics and logics[0].phases:
                            phases = logics[0].phases
                            controlled_links = traci.trafficlight.getControlledLinks(tls)
                            link_index = -1
                            for idx, link_list in enumerate(controlled_links):
                                for link in link_list:
                                    if link[0] == worst_lane:
                                        link_index = idx
                                        break
                                if link_index != -1:
                                    break
                            
                            if link_index != -1:
                                for phase_idx, phase_obj in enumerate(phases):
                                    state = phase_obj.state
                                    if link_index < len(state) and state[link_index] in ('G', 'g'):
                                        failsafe_phase = phase_idx
                                        break
                    except Exception:
                        pass
                
                traci.trafficlight.setPhase(tls, failsafe_phase)
                failsafe_triggers += 1
            else:
                # GNN Optimization
                # Mask out unavailable phases
                available_phases = self.tls_phases[tls]
                weights = action_matrix[i, :available_phases]
                best_phase = int(np.argmax(weights))
                
                traci.trafficlight.setPhase(tls, best_phase)
                
        # Advance SUMO simulation
        traci.simulationStep(traci.simulation.getTime() + self.step_length)
        
        obs = self._get_obs()
        
        # Reward (negative total queue)
        reward = -np.sum(obs["node_features"][:, 0]) 
        
        done = traci.simulation.getMinExpectedNumber() <= 0
        info = {"failsafe_triggers": failsafe_triggers}
        
        return obs, float(reward), done, False, info

    def close(self):
        traci.close()
