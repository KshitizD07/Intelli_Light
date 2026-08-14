"""
Test script for the new SUMOGraphTrafficEnv on the 69-node chaotic network.
"""
import os
import sys
from pathlib import Path
import numpy as np

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rl.sumo_gnn_env import SUMOGraphTrafficEnv

def main():
    print("="*60)
    print(" Intelli-Light 3.0: 69-Node Chaotic Network Test")
    print("="*60)
    
    cfg_file = os.path.join(project_root, "simulation", "random_map", "random_69.sumocfg")
    
    if not os.path.exists(cfg_file):
        print(f"[ERROR] Config not found: {cfg_file}")
        print("Please run `python simulation/generate_random_map.py` first.")
        return
        
    env = SUMOGraphTrafficEnv(sumocfg_file=cfg_file, use_gui=False)
    obs, info = env.reset()
    
    print(f"\n[INFO] Successfully initialized environment with {env.n_nodes} nodes.")
    print(f"[INFO] Node Features shape: {obs['node_features'].shape}")
    print(f"[INFO] Adjacency Matrix shape: {obs['adjacency'].shape}")
    print(f"[INFO] Action space shape: {env.action_space.shape}")
    
    print("\n[INFO] Running 100 simulation steps with random GNN actions...")
    
    total_failsafes = 0
    for i in range(100):
        # Mock GNN forward pass (random weights)
        action = env.action_space.sample()
        
        obs, reward, done, truncated, info = env.step(action)
        
        total_failsafes += info["failsafe_triggers"]
        
        if done:
            print(f"[INFO] Simulation ended early at step {i}.")
            break
            
    print("\n" + "="*60)
    print(" TEST COMPLETED")
    print(f" Total Failsafe Triggers (Starvation Prevented): {total_failsafes}")
    print("="*60)
    
    env.close()

if __name__ == "__main__":
    main()
