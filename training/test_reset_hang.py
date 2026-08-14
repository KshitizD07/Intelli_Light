import os
import sys
import time
from pathlib import Path

# Add project root to python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rl.sumo_gnn_randomized_env import SUMOGraphTrafficRandomizedEnv

def main():
    print("[INFO] Starting test script...")
    env = SUMOGraphTrafficRandomizedEnv(use_gui=False)
    print("[INFO] Environment initialized successfully.")
    
    print("[INFO] Running reset 1...")
    obs, info = env.reset()
    print("[INFO] Reset 1 complete. Obs nodes:", obs["node_features"].shape)
    
    time.sleep(2)
    
    print("[INFO] Running reset 2...")
    obs, info = env.reset()
    print("[INFO] Reset 2 complete. Obs nodes:", obs["node_features"].shape)
    
    env.close()
    print("[INFO] Test finished successfully!")

if __name__ == "__main__":
    main()
