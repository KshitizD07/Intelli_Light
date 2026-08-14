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
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.monitor import Monitor

from rl.sumo_gnn_realistic_env import SUMOGraphTrafficRealisticEnv
from models.gnn_extractor import GNNExtractor

# Thread-safe queue for operator commands
cmd_queue = queue.Queue()

def input_listener():
    while True:
        try:
            line = sys.stdin.readline().strip().lower()
            if line == 'update':
                cmd_queue.put('report')
        except Exception:
            break

class SUMOGNNCallback(BaseCallback):
    """
    Callback specifically tuned for SUMO GNN training.
    Logs standard RL metrics alongside SUMO-specific variables:
    - Emergency Vehicles Spawned
    - Breakdowns / Accidents triggered
    - Failsafe triggers
    """
    def __init__(self, total_timesteps, checkpoint_interval=25000, report_interval=10000, save_path=None, verbose=0):
        super().__init__(verbose)
        self.total_timesteps = total_timesteps
        self.checkpoint_interval = checkpoint_interval
        self.report_interval = report_interval
        self.save_path = save_path
        self.last_report_step = 0
        self.last_save_step = 0
        
        # Diagnostics accumulators
        self.total_evs = 0
        self.total_breakdowns = 0
        self.total_failsafes = 0

    def _on_step(self) -> bool:
        current_step = self.num_timesteps
        percent = (current_step / self.total_timesteps) * 100
        
        # Accumulate metrics from step info
        for info in self.locals.get("infos", []):
            if "ev_spawned" in info:
                self.total_evs = info["ev_spawned"]
            if "breakdowns_triggered" in info:
                self.total_breakdowns = info["breakdowns_triggered"]
            if "failsafe_triggers" in info:
                self.total_failsafes += info["failsafe_triggers"]

        # 1. Print progress indicator every 100 steps with newline to flush to log file
        if current_step % 100 == 0 or current_step == 1:
            print(f"[Progress] {percent:.2f}% | Step: {current_step}/{self.total_timesteps} | Active halted: {self.locals.get('infos')[0].get('currently_halted_accidents', 0)}")
            sys.stdout.flush()

        # 2. Check for manual update triggers
        try:
            cmd = cmd_queue.get_nowait()
            if cmd == 'report':
                self.print_health_report("ON-DEMAND OPERATOR REPORT")
        except queue.Empty:
            pass

        # 3. Interval Report (Every 10k steps)
        if current_step - self.last_report_step >= self.report_interval:
            self.last_report_step = current_step
            self.print_health_report(f"INTERVAL HEALTH CHECK ({current_step} steps)")

        # 4. Checkpoint Save (Every 25k steps)
        if current_step - self.last_save_step >= self.checkpoint_interval:
            self.last_save_step = current_step
            self.save_checkpoint(current_step)

        return True

    def print_health_report(self, title):
        current_step = self.num_timesteps
        percent = (current_step / self.total_timesteps) * 100
        mean_reward = "N/A"
        mean_len = "N/A"
        
        if len(self.model.ep_info_buffer) > 0:
            rewards = [info['r'] for info in self.model.ep_info_buffer]
            lengths = [info['l'] for info in self.model.ep_info_buffer]
            mean_reward = f"{sum(rewards)/len(rewards):.4f}"
            mean_len = f"{sum(lengths)/len(lengths):.1f}"
            
        # Get live queue features from env
        avg_wait = "N/A"
        if self.training_env is not None:
            waits = []
            for env_idx in range(self.training_env.num_envs):
                raw_env = self.training_env.envs[env_idx]
                if hasattr(raw_env, 'env'):
                    raw_env = raw_env.env
                # First element of node features is normalized queues
                waits.append(np.mean(raw_env._get_obs()["node_features"][:, 1]) * 300.0)
            avg_wait = f"{np.mean(waits):.2f}s"

        print(f"\n\n==================== {title} ====================")
        print(f"  Status:             [ACTIVE] SUMO Optimisation")
        print(f"  Step Completed:     {current_step} / {self.total_timesteps}")
        print(f"  Completion Ratio:   {percent:.2f}%")
        print(f"  ------------------------------------------------")
        print(f"  Mean Reward:        {mean_reward}")
        print(f"  Mean Episode Len:   {mean_len} steps")
        print(f"  Mean Delay (Peak):  {avg_wait}")
        print(f"  Emergency Spawns:   {self.total_evs} vehicles")
        print(f"  Accidents/Stalls:   {self.total_breakdowns} events")
        print(f"  Failsafe Triggers:  {self.total_failsafes} overrides")
        print(f"  Learning Rate:      {self.model.policy.optimizer.param_groups[0]['lr']}")
        print(f"  Hardware Limit:     4 CPU Threads (Safe Mode)")
        print(f"========================================================\n")

    def save_checkpoint(self, step):
        if self.save_path:
            p = Path(self.save_path)
            checkpoint_file = p.parent / f"sumo_gnn_checkpoint_step_{step}.zip"
            latest_file = p.parent / "sumo_gnn_model_latest.zip"
            
            self.model.save(str(checkpoint_file))
            self.model.save(str(latest_file))
            print(f"\n\n[SUCCESS] Checkpoint saved: {checkpoint_file.name}")


def main():
    print("=" * 60)
    print(" Intelli-Light 3.0: Real SUMO GNN training protocol")
    print("=" * 60)
    print("[INFO] Safety Limit: Restricted to exactly 4 CPU threads.")
    print("[INFO] Loading Lucknow Map Scenario (osm/net/rou config)...")
    
    sumocfg_file = os.path.join(project_root, "simulation", "lucknow_map", "lucknow.sumocfg")
    
    # 1. Initialize Headless SUMO Environment wrapped in Monitor
    def make_env():
        return Monitor(SUMOGraphTrafficRealisticEnv(
            sumocfg_file=sumocfg_file,
            use_gui=False,
            failsafe_threshold=90.0,
            ev_probability=0.05,
            breakdown_probability=0.005
        ))
        
    env = DummyVecEnv([make_env])
    
    # 2. Check for latest checkpoint to auto-resume
    save_dir = os.path.join(project_root, "models", "checkpoints")
    os.makedirs(save_dir, exist_ok=True)
    latest_checkpoint = os.path.join(save_dir, "sumo_gnn_model_latest.zip")
    
    policy_kwargs = dict(
        features_extractor_class=GNNExtractor,
        features_extractor_kwargs=dict(features_dim=256),
        net_arch=[256, 128]
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

    # 3. Spin up command listener thread for manual 'update' command
    t = threading.Thread(target=input_listener, daemon=True)
    t.start()

    # 4. Start learning protocol
    callback = SUMOGNNCallback(
        total_timesteps=total_steps,
        checkpoint_interval=10000,
        report_interval=10000,
        save_path=os.path.join(save_dir, "sumo_gnn_model_v1.zip")
    )

    print("\n[INFO] Starting training protocol on Lucknow map. Type 'update' at any time to request status.\n")
    try:
        model.learn(total_timesteps=total_steps, callback=callback)
        print("\n\n[SUCCESS] SUMO GNN training completed successfully!")
    except KeyboardInterrupt:
        print("\n\n[INFO] Training paused by Operator.")
        model.save(latest_checkpoint)
        print(f"[INFO] Current state saved to: {latest_checkpoint}")

if __name__ == "__main__":
    main()
