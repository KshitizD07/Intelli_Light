import os
import sys
import numpy as np
import torch
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from rl.gnn_env import GraphTrafficEnv

def evaluate_model(model_path, num_steps=2000):
    print("=" * 60)
    print(" Intelli-Light 3.0: GNN Policy Evaluation Diagnostics")
    print("=" * 60)
    
    # Initialize environment
    def make_env():
        return GraphTrafficEnv(n_junctions=5, failsafe_threshold=90.0)
    env = DummyVecEnv([make_env])
    
    # Load model
    if not os.path.exists(model_path):
        print(f"[ERROR] Checkpoint not found at: {model_path}")
        return
        
    print(f"[INFO] Loading policy network from: {model_path}")
    model = PPO.load(model_path, env=env, custom_objects={"device": "cpu"})
    
    # Metrics containers
    rewards = []
    max_wait_times = []
    average_wait_times = []
    failsafe_activations = 0
    
    obs = env.reset()
    
    print(f"[INFO] Simulating {num_steps} control cycles...")
    for step in range(num_steps):
        action, _states = model.predict(obs, deterministic=True)
        obs, reward, done, info = env.step(action)
        
        rewards.append(reward[0])
        
        # Info contains: failsafe_active, failsafe_nodes, max_waits
        step_info = info[0]
        max_wait_times.append(np.mean(step_info["max_waits"]))
        
        # Approximate wait times across all junctions/streams
        # (Based on rewards which represent average penalty across nodes)
        average_wait_times.append(-reward[0])
        
        if step_info["failsafe_active"]:
            failsafe_activations += 1
            
    # Compile performance stats
    mean_reward = np.mean(rewards)
    std_reward = np.std(rewards)
    mean_avg_wait = np.mean(average_wait_times)
    mean_max_wait = np.mean(max_wait_times)
    failsafe_rate = (failsafe_activations / num_steps) * 100
    
    print("\n" + "=" * 25 + " PERFORMANCE METRICS " + "=" * 25)
    print(f"Total Steps Tested:       {num_steps} steps")
    print(f"Overall Mean Reward:      {mean_reward:.4f} (higher is better)")
    print(f"Reward Deviation:         {std_reward:.4f}")
    print(f"Mean Intersection Delay:  {mean_avg_wait:.2f} seconds")
    print(f"Mean Peak Waiting Time:   {mean_max_wait:.2f} seconds")
    print(f"Failsafe Override Rate:   {failsafe_rate:.2f}% (GNN safety violation frequency)")
    
    # Grade policy quality
    print("-" * 71)
    if failsafe_rate < 5.0 and mean_avg_wait < 30.0:
        grade = "A (OPTIMIZED TRAFFIC STREAM)"
        desc = "The policy has successfully learned green-wave optimization with minimal safety intervention."
    elif failsafe_rate < 20.0:
        grade = "B (STABLE STREAMING)"
        desc = "Stable control. GNN keeps queue heights controlled, but relies on occasional failsafes."
    else:
        grade = "C (UNSTABLE / TRAINING UNDERFIT)"
        desc = "High delay and frequent failsafe overrides. Model requires more training or structural observation parameters."
        
    print(f"Performance Category:    {grade}")
    print(f"Diagnostic Summary:      {desc}")
    print("=" * 71 + "\n")

if __name__ == "__main__":
    latest_checkpoint = os.path.join(project_root, "models", "checkpoints", "gnn_checkpoint_step_100000.zip")
    evaluate_model(latest_checkpoint)
