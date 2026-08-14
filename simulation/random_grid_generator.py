import os
import random
import subprocess
import sumolib

def generate_random_grid(output_dir="simulation/domain_randomization"):
    """
    Generates a 2x2 grid (exactly 4 traffic light intersections) with randomized:
    - Road lengths (150m to 500m)
    - Lane numbers (2 to 4 lanes)
    - Speed limits (10m/s to 20m/s)
    - Traffic density and routes
    """
    os.makedirs(output_dir, exist_ok=True)
    
    net_file = os.path.join(output_dir, "random_grid.net.xml")
    rou_file = os.path.join(output_dir, "random_grid.rou.xml")
    sumocfg_file = os.path.join(output_dir, "random_grid.sumocfg")
    
    # 1. Randomize grid parameters
    road_length = random.choice([150, 200, 300, 400, 500])
    lanes = random.choice([2, 3, 4])
    speed = random.choice([11.11, 13.89, 16.67, 20.0]) # ~40km/h to 72km/h
    
    cmd_netgen = [
        "netgenerate",
        "--grid", "true",
        "--grid.number", "2", # Exactly 2x2 intersections = 4 nodes
        "--grid.length", str(road_length),
        "--default.lanenumber", str(lanes),
        "--default.speed", f"{speed:.2f}",
        "--default-junction-type", "traffic_light",
        "--tls.guess", "true",
        "--tls.default-type", "static",
        "-o", net_file
    ]
    
    try:
        subprocess.run(cmd_netgen, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[ERROR] netgenerate failed: {e}")
        return None

    # 2. Randomize traffic trips period (density)
    # period between 0.3 (high density) and 1.5 (low density)
    period = random.uniform(0.3, 1.5)
    
    sumo_home = os.environ.get("SUMO_HOME", "")
    randomTrips_script = os.path.join(sumo_home, "tools", "randomTrips.py")
    
    cmd_trips = [
        "python", randomTrips_script,
        "-n", net_file,
        "-r", rou_file,
        "-e", "3600",
        "--fringe-factor", "10",
        "--period", f"{period:.2f}",
        "--random"
    ]
    
    try:
        subprocess.run(cmd_trips, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[ERROR] randomTrips failed: {e}")
        return None
        
    # 3. Create SUMOCFG
    with open(sumocfg_file, "w") as f:
        f.write(f'''<configuration>
    <input>
        <net-file value="random_grid.net.xml"/>
        <route-files value="random_grid.rou.xml"/>
    </input>
    <time>
        <begin value="0"/>
        <end value="3600"/>
    </time>
</configuration>''')
        
    return sumocfg_file
