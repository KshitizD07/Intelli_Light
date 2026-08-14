"""
Visualizer Script for the GNN Architecture.
Launches the SUMO GUI on the chaotic 69-node network to demonstrate
how the untrained GNN interacts with a city-scale layout.
"""
import os
import sys
from pathlib import Path
import time

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rl.sumo_gnn_env import SUMOGraphTrafficEnv

def main():
    print("="*60)
    print(" Intelli-Light 3.0: Launching Visual Demonstration (GUI)")
    print("="*60)
    
    cfg_file = os.path.join(project_root, "simulation", "lucknow_map", "lucknow.sumocfg")
    
    if not os.path.exists(cfg_file):
        print(f"[ERROR] Config not found: {cfg_file}")
        return
        
    # Initialize with use_gui=True to open the visual SUMO window
    env = SUMOGraphTrafficEnv(sumocfg_file=cfg_file, use_gui=True)
    obs, info = env.reset()
    
    print("\n[INFO] SUMO GUI has been launched on your desktop!")
    print("[INFO] The simulation is running with the untrained GNN model.")
    print("[INFO] You can adjust the simulation delay in the SUMO UI to watch the lights change.")
    print("Press Ctrl+C in the terminal to stop the simulation.\n")
    
    try:
        while True:
            # The model is currently untrained, so we sample random stream weights
            action = env.action_space.sample()
            
            obs, reward, done, truncated, info = env.step(action)
            
            # If the scenario finishes (1 hour simulated time), restart it
            if done:
                print("[INFO] Scenario completed. Restarting...")
                obs, info = env.reset()
                
            # A tiny sleep to prevent the python loop from maxing out CPU if SUMO runs too fast
            time.sleep(0.01)
            
    except KeyboardInterrupt:
        print("\n[INFO] Demonstration stopped by user.")
    finally:
        env.close()
        print("[INFO] SUMO closed successfully.")

if __name__ == "__main__":
    main()
