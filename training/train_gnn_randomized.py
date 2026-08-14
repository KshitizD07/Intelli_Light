import os
import sys
import time
import queue
import threading
from pathlib import Path
import torch
import numpy as np

# Add project root to python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set resource limits FIRST for laptop protection
try:
    torch.set_num_threads(4)
    torch.set_num_interop_threads(4)
except RuntimeError:
    pass

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.monitor import Monitor

from rl.sumo_gnn_randomized_env import SUMOGraphTrafficRandomizedEnv
from training.train_gnn_sumo import SUMOGNNCallback, input_listener

def main():
    print("=" * 60)
    print(" Intelli-Light 3.0: Robust GNN Domain Randomization Training")
    print("=" * 60)
    print("[INFO] Safety Limit: Restricted to exactly 4 CPU threads.")
    print("[INFO] Training on randomized 2x2 grid configurations...")
    
    # 1. Initialize Headless Randomized SUMO Environment wrapped in Monitor
    def make_env():
        return Monitor(SUMOGraphTrafficRandomizedEnv(
            use_gui=False,
            failsafe_threshold=90.0,
            ev_probability=0.05,
            breakdown_probability=0.005
        ))
        
    env = DummyVecEnv([make_env])
    
    # 2. Check for latest checkpoint to auto-resume
    save_dir = os.path.join(project_root, "models", "checkpoints")
    os.makedirs(save_dir, exist_ok=True)
    latest_checkpoint = os.path.join(save_dir, "randomized_gnn_model_latest.zip")
    
    # Extract dimensions from env space
    node_features_space = env.observation_space.spaces['node_features']
    print(f"[INFO] Graph Dimensions: {node_features_space.shape[0]} intersections, {node_features_space.shape[1]} features.")
    
    # We must explicitly load GNNExtractor
    from models.gnn_extractor import GNNExtractor
    policy_kwargs = dict(
        features_extractor_class=GNNExtractor,
        features_extractor_kwargs=dict(features_dim=128),
        net_arch=[128, 64]
    )

    total_steps = 10000

    if os.path.exists(latest_checkpoint):
        print(f"[INFO] Found previous training state. Auto-resuming from: {latest_checkpoint}")
        model = PPO.load(latest_checkpoint, env=env, custom_objects={"device": "cpu"})
        # Re-apply thread limits
        torch.set_num_threads(4)
        torch.set_num_interop_threads(4)
    else:
        print("[INFO] No existing checkpoints found. Initializing fresh model...")
        model = PPO(
            "MultiInputPolicy",
            env,
            policy_kwargs=policy_kwargs,
            learning_rate=3e-4,
            n_steps=1024,
            batch_size=64,
            verbose=0,
            device="cpu"
        )



    # 4. Start learning protocol
    callback = SUMOGNNCallback(
        total_timesteps=total_steps,
        checkpoint_interval=10000,
        report_interval=2000, # Show progress more frequently (every 2k steps) since total is 10k!
        save_path=os.path.join(save_dir, "randomized_gnn_model_v1.zip")
    )
    
    # Make sure we save to randomized latest checkpoint
    callback.save_path = os.path.join(save_dir, "randomized_gnn_model_v1.zip")

    print("\n[INFO] Starting training protocol. Type 'update' at any time to request status.\n")
    try:
        model.learn(total_timesteps=total_steps, callback=callback)
        # Save final checkpoints
        model.save(os.path.join(save_dir, "randomized_gnn_model_v1.zip"))
        model.save(latest_checkpoint)
        print("\n\n[SUCCESS] GNN Domain Randomization training completed successfully!")
    except KeyboardInterrupt:
        print("\n\n[INFO] Training paused by Operator.")
        model.save(latest_checkpoint)
        print(f"[INFO] Current state saved to: {latest_checkpoint}")

if __name__ == "__main__":
    main()
