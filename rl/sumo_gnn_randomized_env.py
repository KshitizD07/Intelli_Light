import os
import sys
import numpy as np
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rl.sumo_gnn_realistic_env import SUMOGraphTrafficRealisticEnv
from simulation.random_grid_generator import generate_random_grid

class SUMOGraphTrafficRandomizedEnv(SUMOGraphTrafficRealisticEnv):
    """
    SUMO-integrated GNN Traffic Environment with Domain Randomization.
    Generates a brand new 2x2 grid layout (4 junctions) with randomized lanes,
    speed limits, road lengths, and traffic density at every episode reset.
    """
    def __init__(self, use_gui: bool = False, failsafe_threshold: float = 90.0,
                 ev_probability: float = 0.05, breakdown_probability: float = 0.005):
        # 1. Generate an initial random grid network to size the spaces
        initial_cfg = generate_random_grid()
        if not initial_cfg:
            raise RuntimeError("[ERROR] Failed to generate initial random grid network.")
            
        super().__init__(sumocfg_file=initial_cfg, use_gui=use_gui, failsafe_threshold=failsafe_threshold,
                         ev_probability=ev_probability, breakdown_probability=breakdown_probability)
                         
    def reset(self, seed=None, options=None):
        # 1. Close TraCI connection to terminate SUMO and release Windows file locks
        try:
            import traci
            traci.close()
        except:
            pass
            
        # 2. On every episode reset, generate a brand new randomized grid configuration!
        new_cfg = generate_random_grid()
        if new_cfg:
            self.sumocfg_file = new_cfg
        
        # 3. Call reset of realistic environment to restart SUMO TraCI with the new config
        return super().reset(seed=seed, options=options)
