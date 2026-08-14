import os
import sys
import time
import queue
import threading
from pathlib import Path
import torch

# Add project root to python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set resource limits FIRST before importing torch layers to guarantee safety
torch.set_num_threads(4)
torch.set_num_interop_threads(4)

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.callbacks import BaseCallback

from rl.gnn_env import GraphTrafficEnv
from models.gnn_extractor import GNNExtractor

# Thread-safe queue for operator CLI updates
cmd_queue = queue.Queue()

def input_listener():
    """Listens for user commands in a background thread."""
    while True:
        try:
            line = sys.stdin.readline().strip().lower()
            if line == 'update':
                cmd_queue.put('report')
        except Exception:
            break

class SafeTrainingCallback(BaseCallback):
    """
    Custom Stable-Baselines3 Callback for safe execution.
    - Limits logging overhead.
    - Tracks & displays real-time completion percentage.
    - Triggers reports every 10k steps.
    - Auto-saves checkpoints every 25k steps.
    - Listens for on-demand 'update' triggers.
    """
    def __init__(self, total_timesteps, checkpoint_interval=25000, report_interval=10000, save_path=None, verbose=0):
        super().__init__(verbose)
        self.total_timesteps = total_timesteps
        self.checkpoint_interval = checkpoint_interval
        self.report_interval = report_interval
        self.save_path = save_path
        self.last_report_step = 0
        self.last_save_step = 0

    def _on_step(self) -> bool:
        current_step = self.num_timesteps
        percent = (current_step / self.total_timesteps) * 100
        
        # 1. Print continuous progress indicator (one-liner)
        sys.stdout.write(f"\r[Progress] {percent:.2f}% | Step: {current_step}/{self.total_timesteps}")
        sys.stdout.flush()

        # 2. Check for manual on-demand 'update' trigger
        try:
            cmd = cmd_queue.get_nowait()
            if cmd == 'report':
                self.print_health_report("ON-DEMAND OPERATOR REPORT")
        except queue.Empty:
            pass

        # 3. Step Report (Every 10k steps)
        if current_step - self.last_report_step >= self.report_interval:
            self.last_report_step = current_step
            self.print_health_report(f"INTERVAL HEALTH CHECK ({current_step} steps)")

        # 4. Checkpoint Save (Every 25k steps)
        if current_step - self.last_save_step >= self.checkpoint_interval:
            self.last_save_step = current_step
            self.save_checkpoint(current_step)

        return True

    def print_health_report(self, title):
        """Prints a structured, professional dashboard diagnostics report."""
        current_step = self.num_timesteps
        percent = (current_step / self.total_timesteps) * 100
        mean_reward = "N/A"
        mean_len = "N/A"
        
        # Extract episodic info from monitor buffer
        if len(self.model.ep_info_buffer) > 0:
            rewards = [info['r'] for info in self.model.ep_info_buffer]
            lengths = [info['l'] for info in self.model.ep_info_buffer]
            mean_reward = f"{sum(rewards)/len(rewards):.4f}"
            mean_len = f"{sum(lengths)/len(lengths):.1f}"
            
        # Extract live average wait times directly from env instances
        avg_wait = "N/A"
        if self.training_env is not None:
            waits = []
            for env_idx in range(self.training_env.num_envs):
                # Traverse DummyVecEnv -> Monitor -> GraphTrafficEnv
                raw_env = self.training_env.envs[env_idx]
                if hasattr(raw_env, 'env'):
                    raw_env = raw_env.env
                waits.append(np.mean(raw_env.current_waits))
            avg_wait = f"{np.mean(waits):.2f}s"
            
        print(f"\n\n==================== {title} ====================")
        print(f"  Status:            [ACTIVE] Optimization Protocol")
        print(f"  Step Completed:    {current_step} / {self.total_timesteps}")
        print(f"  Completion Ratio:  {percent:.2f}%")
        print(f"  ------------------------------------------------")
        print(f"  Episodic Reward:   {mean_reward}")
        print(f"  Episodic Length:   {mean_len} steps")
        print(f"  Network Delay:     {avg_wait}")
        print(f"  Learning Rate:     {self.model.policy.optimizer.param_groups[0]['lr']}")
        print(f"  CPU Threads Limit: 4 Cores (Failsafe Mode)")
        print(f"========================================================\n")

    def save_checkpoint(self, step):
        if self.save_path:
            p = Path(self.save_path)
            checkpoint_file = p.parent / f"gnn_checkpoint_step_{step}.zip"
            # Keep a general "latest" file as well for auto-resume
            latest_file = p.parent / "gnn_model_latest.zip"
            
            self.model.save(str(checkpoint_file))
            self.model.save(str(latest_file))
            print(f"\n\n[SUCCESS] Checkpoint saved: {checkpoint_file.name}")


from stable_baselines3.common.monitor import Monitor

def main():
    print("=" * 60)
    print(" Intelli-Light 3.0: Safe GNN Training Launcher")
    print("=" * 60)
    print("[INFO] Safety Limit: Restricted to exactly 4 CPU threads.")
    
    # 1. Initialize Headless Environment with Monitor wrapping
    def make_env():
        return Monitor(GraphTrafficEnv(n_junctions=5, failsafe_threshold=90.0))
        
    env = DummyVecEnv([make_env])
    
    # 2. Check for latest checkpoint to auto-resume
    save_dir = os.path.join(project_root, "models", "checkpoints")
    os.makedirs(save_dir, exist_ok=True)
    latest_checkpoint = os.path.join(save_dir, "gnn_model_latest.zip")
    
    policy_kwargs = dict(
        features_extractor_class=GNNExtractor,
        features_extractor_kwargs=dict(features_dim=256),
        net_arch=[256, 128]
    )

    total_steps = 100000

    if os.path.exists(latest_checkpoint):
        print(f"[INFO] Found previous training state. Auto-resuming from: {latest_checkpoint}")
        model = PPO.load(latest_checkpoint, env=env, custom_objects={"device": "cpu"})
        # Update thread limits inside restored PyTorch runtime
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
            verbose=0, # Disable default SB3 verbose logs to keep terminal clean
            device="cpu" # Limit to CPU to prevent overheating laptop GPU
        )

    # 3. Spin up command listener thread for manual 'update' command
    t = threading.Thread(target=input_listener, daemon=True)
    t.start()

    # 4. Start learning protocol with custom safety callback
    callback = SafeTrainingCallback(
        total_timesteps=total_steps,
        checkpoint_interval=25000,
        report_interval=10000,
        save_path=os.path.join(save_dir, "gnn_model_v1.zip")
    )

    print("\n[INFO] Starting training protocol. Type 'update' at any time to request status.\n")
    try:
        model.learn(total_timesteps=total_steps, callback=callback)
        print("\n\n[SUCCESS] Training protocol completed successfully!")
    except KeyboardInterrupt:
        print("\n\n[INFO] Training paused by Operator.")
        model.save(latest_checkpoint)
        print(f"[INFO] Current state saved to: {latest_checkpoint}")

if __name__ == "__main__":
    main()
