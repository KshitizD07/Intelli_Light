import os
import sys
import numpy as np
import random
import traci
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rl.sumo_gnn_env import SUMOGraphTrafficEnv

class SUMOGraphTrafficRealisticEnv(SUMOGraphTrafficEnv):
    """
    SUMO-integrated GNN Traffic Environment with realistic traffic events:
    - Emergency Vehicle Spawning (with high priority weights)
    - Random Vehicle Breakdowns (accidents/stalls causing queue spikes)
    - Dynamic Traffic Injection (variable inflow to simulate congestion waves)
    """
    def __init__(self, sumocfg_file: str, use_gui: bool = False, failsafe_threshold: float = 90.0,
                 ev_probability: float = 0.05, breakdown_probability: float = 0.005):
        super().__init__(sumocfg_file=sumocfg_file, use_gui=use_gui, failsafe_threshold=failsafe_threshold)
        
        self.ev_probability = ev_probability
        self.breakdown_probability = breakdown_probability
        
        self.ev_count = 0
        self.breakdown_count = 0
        self.halted_vehicles = {} # veh_id -> duration remaining to stay stopped
        
    def step(self, action: np.ndarray):
        # 1. Manage current breakdowns (decrement timers, release if finished)
        released_vehs = []
        for veh_id, remaining_time in list(self.halted_vehicles.items()):
            if remaining_time <= 5.0: # 5 seconds step
                try:
                    # Resume standard behavior (speed limit)
                    traci.vehicle.setSpeed(veh_id, -1.0)
                    released_vehs.append(veh_id)
                except traci.TraCIException:
                    released_vehs.append(veh_id)
            else:
                self.halted_vehicles[veh_id] -= 5.0
        for v in released_vehs:
            del self.halted_vehicles[v]

        # 2. Inject Emergency Vehicles dynamically
        if random.random() < self.ev_probability:
            try:
                routes = traci.route.getIDList()
                if routes:
                    veh_id = f"ev_{self.ev_count}_{traci.simulation.getTime()}"
                    route_id = random.choice(routes)
                    traci.vehicle.add(vehID=veh_id, routeID=route_id, departLane="best", departSpeed="max")
                    traci.vehicle.setColor(veh_id, (255, 0, 0, 255)) # Red for EV
                    traci.vehicle.setVehicleClass(veh_id, "emergency")
                    # Speed up the EV
                    traci.vehicle.setSpeedFactor(veh_id, 1.5)
                    self.ev_count += 1
            except traci.TraCIException:
                pass

        # 3. Inject random breakdowns / accidents
        if random.random() < self.breakdown_probability:
            try:
                vehicles = traci.vehicle.getIDList()
                # Filter out EVs and already halted vehicles
                candidates = [v for v in vehicles if not v.startswith("ev_") and v not in self.halted_vehicles]
                if candidates:
                    target_veh = random.choice(candidates)
                    # Halt vehicle for 45-90 seconds
                    halt_duration = random.randint(45, 90)
                    traci.vehicle.setSpeed(target_veh, 0.0) # Stop vehicle
                    traci.vehicle.setColor(target_veh, (255, 165, 0, 255)) # Orange hazard indicator
                    self.halted_vehicles[target_veh] = halt_duration
                    self.breakdown_count += 1
            except traci.TraCIException:
                pass

        # 4. Standard step (applies phase actions, updates SUMO clock, calculates standard reward)
        obs, reward, done, truncated, info = super().step(action)
        
        # 5. Enrich info dict with realistic metrics
        info.update({
            "ev_spawned": self.ev_count,
            "breakdowns_triggered": self.breakdown_count,
            "currently_halted_accidents": len(self.halted_vehicles)
        })
        
        # 6. Apply penalty on reward for active accidents / breakdowns
        # High queue penalty is already captured by super().step via halted step queues,
        # but we can add a specific EV delay penalty to incentivize EV greenwaves
        ev_delay_penalty = 0.0
        try:
            active_vehs = traci.vehicle.getIDList()
            for v in active_vehs:
                if v.startswith("ev_"):
                    # High penalty for emergency vehicle delay
                    ev_delay_penalty += traci.vehicle.getWaitingTime(v)
        except traci.TraCIException:
            pass
            
        reward -= (ev_delay_penalty * 0.1)
        
        return obs, float(reward), done, truncated, info
