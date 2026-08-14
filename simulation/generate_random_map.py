import os
import subprocess
import random

def generate_random_sumo_network(nodes=69, output_dir="simulation/random_map"):
    """
    Generates a completely random SUMO network with N nodes.
    Uses SUMO's netgenerate tool to build a chaotic topology.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    net_file = os.path.join(output_dir, "random_69.net.xml")
    
    # Run SUMO's netgenerate tool for a random network
    print(f"[INFO] Generating random network with {nodes} intersections...")
    
    cmd = [
        "netgenerate",
        "--rand", "true",
        "--rand.iterations", str(nodes),
        "--default.lanenumber", "2",
        "--tls.guess", "true",
        "--output-file", net_file
    ]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"[SUCCESS] Random network saved to {net_file}")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to generate network: {e.stderr.decode()}")
        return None

    # Generate random routes (traffic) for this network
    rou_file = os.path.join(output_dir, "random_69.rou.xml")
    print("[INFO] Generating random traffic routes...")
    
    route_cmd = [
        "python", "-m", "sumolib.net.generateTrips",
        "-n", net_file,
        "-o", rou_file,
        "-e", "3600", # 1 hour of traffic
        "--fringe-factor", "10", 
        "--random"
    ]
    
    # We might need to use randomTrips.py depending on the SUMO version. 
    # Let's write a fallback using Python's sumolib if needed.
    
    randomTrips_script = os.path.join(os.environ.get("SUMO_HOME", ""), "tools", "randomTrips.py")
    if os.path.exists(randomTrips_script):
        route_cmd = [
            "python", randomTrips_script,
            "-n", net_file,
            "-r", rou_file,
            "-e", "3600",
            "--random"
        ]
        
    try:
        subprocess.run(route_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"[SUCCESS] Random routes saved to {rou_file}")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to generate routes: {e.stderr.decode()}")
        return None
        
    # Generate SUMO config file
    sumocfg_file = os.path.join(output_dir, "random_69.sumocfg")
    with open(sumocfg_file, "w") as f:
        f.write(f'''<configuration>
    <input>
        <net-file value="random_69.net.xml"/>
        <route-files value="random_69.rou.xml"/>
    </input>
    <time>
        <begin value="0"/>
        <end value="3600"/>
    </time>
</configuration>''')

    print(f"[SUCCESS] Config saved to {sumocfg_file}")
    return sumocfg_file

if __name__ == "__main__":
    generate_random_sumo_network()
