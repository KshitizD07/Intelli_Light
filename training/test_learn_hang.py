import os
import sys
import time
from pathlib import Path
import torch
import numpy as np

# Add project root to python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.monitor import Monitor

from rl.sumo_gnn_randomized_env import SUMOGraphTrafficRandomizedEnv

def make_env():
    return Monitor(SUMOGraphTrafficRandomizedEnv(
        use_gui=False,
        failsafe_threshold=90.0,
        ev_probability=0.05,
        breakdown_probability=0.005
    ))

def main():
    print("[INFO] Starting test learn script...")
    env = DummyVecEnv([make_env])
    print("[INFO] Env created.")
    
    from models.gnn_extractor import GNNExtractor
    policy_kwargs = dict(
        features_extractor_class=GNNExtractor,
        features_extractor_kwargs=dict(features_dim=128),
        net_arch=[128, 64]
    )
    
    print("[INFO] Initializing PPO...")
    model = PPO(
        "MultiInputPolicy",
        env,
        policy_kwargs=policy_kwargs,
        learning_rate=3e-4,
        n_steps=10, # Very small n_steps for quick test
        batch_size=10,
        verbose=1,
        device="cpu"
    )
    print("[INFO] PPO initialized. Starting learn...")
    
    model.learn(total_timesteps=10)
    print("[INFO] Learn finished successfully!")
    env.close()

if __name__ == "__main__":
    main()
