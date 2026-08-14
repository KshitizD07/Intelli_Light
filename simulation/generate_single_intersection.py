import os
import subprocess
import sys
from pathlib import Path

def generate_single_intersection(output_dir="simulation/single_intersection"):
    """
    Generates a single, standard 4-way traffic light intersection network
    and generates dynamic routes for training.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    net_file = os.path.join(output_dir, "single.net.xml")
    rou_file = os.path.join(output_dir, "single.rou.xml")
    sumocfg_file = os.path.join(output_dir, "single.sumocfg")
    
    print("[INFO] Building standard 4-way single intersection netxml...")
    # netgenerate --grid generates grid network. grid.number=1 means a single junction.
    cmd_net = [
        "netconvert",
        "--node-files", "",  # Empty node/edge means build procedurally or netgenerate
    ]
    # Standard SUMO netgenerate grid command for single junction (2x2 grid is easiest for 1 intersection at the center)
    cmd_netgenerate = [
        "netgenerate",
        "--grid", "true",
        "--grid.number", "2", # 2x2 grid of roads gives exactly 1 central intersection and 4 outer boundary nodes
        "--grid.length", "300",
        "--default.lanenumber", "2",
        "--tls.guess", "true",
        "--tls.default-type", "static",
        "-o", net_file
    ]
    
    try:
        subprocess.run(cmd_netgenerate, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[SUCCESS] Network generated: {net_file}")
    except Exception as e:
        print(f"[ERROR] Failed to run netgenerate: {e}")
        return False
        
    # Generate random routes for single intersection
    print("[INFO] Generating traffic routes for single intersection...")
    sumo_home = os.environ.get("SUMO_HOME", "")
    randomTrips_script = os.path.join(sumo_home, "tools", "randomTrips.py")
    
    cmd_trips = [
        "python", randomTrips_script,
        "-n", net_file,
        "-r", rou_file,
        "-e", "3600",
        "--fringe-factor", "10",
        "--period", "0.5", # High density traffic (1 car every 0.5s) to simulate heavy congestion
        "--random"
    ]
    
    try:
        subprocess.run(cmd_trips, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[SUCCESS] Routes generated: {rou_file}")
    except Exception as e:
        print(f"[ERROR] Failed to generate trips: {e}")
        return False
        
    # Write SUMOCFG
    with open(sumocfg_file, "w") as f:
        f.write('''<configuration>
    <input>
        <net-file value="single.net.xml"/>
        <route-files value="single.rou.xml"/>
    </input>
    <time>
        <begin value="0"/>
        <end value="3600"/>
    </time>
</configuration>''')
    print(f"[SUCCESS] SUMO config created: {sumocfg_file}")
    return True

if __name__ == "__main__":
    generate_single_intersection()
