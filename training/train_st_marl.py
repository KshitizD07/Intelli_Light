"""
Training Script for Spatio-Temporal MARL (STAN) Architecture
============================================================
Integrates the SpatioTemporalMARLExtractor (GAT + LSTM) with the
RealWorldMARLEnv (Backpressure, EV Priority, Min Green constraints).
"""

import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv

from rl.real_world_env import RealWorldMARLEnv
from models.st_marl_model import SpatioTemporalMARLExtractor

def main():
    print("=" * 60)
    print(" Intelli-Light 3.0: ST-MARL Training Initialization")
    print(" Architecture: Graph Attention (GAT) + LSTM History")
    print(" Optimization: Backpressure Routing (Surtrac Competitor)")
    print("=" * 60)
    
    def make_env():
        return RealWorldMARLEnv(n_neighbors=4, seq_len=5, min_green=15.0, failsafe_time=90.0)
        
    env = DummyVecEnv([make_env])
    
    policy_kwargs = dict(
        features_extractor_class=SpatioTemporalMARLExtractor,
        features_extractor_kwargs=dict(features_dim=128),
        net_arch=[128, 64] # Final MLP head predicting stream weights
    )
    
    model = PPO(
        "MultiInputPolicy",
        env,
        policy_kwargs=policy_kwargs,
        learning_rate=3e-4,
        n_steps=1024,
        batch_size=64,
        verbose=1,
        device="auto"
    )
    
    print("\n[INFO] Starting MARL Agent Training...")
    print(f"[INFO] Device: {model.device}")
    
    try:
        # Quick compilation/sanity test
        model.learn(total_timesteps=2048)
    except KeyboardInterrupt:
        print("\n[INFO] Training interrupted.")
        
    save_dir = os.path.join(project_root, "models", "checkpoints")
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, "st_marl_v1.zip")
    
    model.save(save_path)
    print(f"\n[SUCCESS] ST-MARL model saved to {save_path}")

if __name__ == "__main__":
    main()
