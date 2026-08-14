"""
Intelli-Light 3.0: GNN Training Script
=======================================

This script trains the Graph Neural Network (GNN) policy on the city topology.
It uses Stable-Baselines3's PPO algorithm, integrating our custom GNNExtractor
to process the GraphTrafficEnv's node features and adjacency matrices.
"""

import os
import sys
from pathlib import Path
import torch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv

from rl.gnn_env import GraphTrafficEnv
from models.gnn_extractor import GNNExtractor

def main():
    print("=" * 60)
    print(" Intelli-Light 3.0: Initializing GNN Training Protocol")
    print("=" * 60)
    
    # 1. Initialize the Graph Environment with Failsafe Threshold
    def make_env():
        return GraphTrafficEnv(n_junctions=5, failsafe_threshold=90.0)
        
    env = DummyVecEnv([make_env])
    
    # 2. Configure PPO with custom GNN Feature Extractor
    policy_kwargs = dict(
        features_extractor_class=GNNExtractor,
        features_extractor_kwargs=dict(features_dim=256),
        net_arch=[256, 128] # MLP after the GNN processes the graph
    )
    
    model = PPO(
        "MultiInputPolicy", # Required for spaces.Dict observation space
        env,
        policy_kwargs=policy_kwargs,
        learning_rate=3e-4,
        n_steps=1024,
        batch_size=64,
        verbose=1,
        device="auto"
    )
    
    # 3. Train the Model
    print("\n[INFO] Starting training with GNNExtractor...")
    print(f"[INFO] Device: {model.device}")
    
    try:
        model.learn(total_timesteps=10000)
    except KeyboardInterrupt:
        print("\n[INFO] Training interrupted.")
        
    # 4. Save Checkpoint
    save_dir = os.path.join(project_root, "models", "checkpoints")
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, "gnn_model_v1.zip")
    
    model.save(save_path)
    print(f"\n[SUCCESS] GNN model saved to {save_path}")

if __name__ == "__main__":
    main()
