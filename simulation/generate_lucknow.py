import os
import subprocess
import urllib.request
import urllib.parse

def main():
    print("=" * 60)
    print(" Intelli-Light 3.0: Downloading Real Lucknow Map (Overpass API)")
    print("=" * 60)
    
    output_dir = os.path.join("simulation", "lucknow_map")
    os.makedirs(output_dir, exist_ok=True)
    
    prefix = "lucknow"
    osm_file = os.path.join(output_dir, f"{prefix}.osm.xml")
    net_file = os.path.join(output_dir, f"{prefix}.net.xml")
    rou_file = os.path.join(output_dir, f"{prefix}.rou.xml")
    sumocfg_file = os.path.join(output_dir, f"{prefix}.sumocfg")
    
    bbox = "26.80,80.90,26.88,81.00"
    print(f"[INFO] Fetching Lucknow OSM data from Overpass API (bbox: {bbox})...")
    
    overpass_url = "http://overpass-api.de/api/interpreter"
    overpass_query = f"""
    [out:xml][timeout:120];
    (
      way["highway"]({bbox});
      node(w);
    );
    out body;
    """
    
    try:
        data = urllib.parse.urlencode({'data': overpass_query}).encode('utf-8')
        headers = {
            'User-Agent': 'IntelliLight Bot / 1.0 (Contact: admin@intellilight.com)',
            'Accept': '*/*'
        }
        req = urllib.request.Request(overpass_url, data=data, headers=headers)
        with urllib.request.urlopen(req) as response:
            osm_data = response.read().decode('utf-8')
            
        with open(osm_file, "w", encoding="utf-8") as f:
            f.write(osm_data)
        print(f"[SUCCESS] Downloaded OSM data to {osm_file}")
    except Exception as e:
        print(f"[ERROR] Failed to fetch data: {e}")
        return

    # 2. Convert OSM to SUMO Network
    print("[INFO] Converting OSM data to SUMO network... (This may take a minute)")
    cmd_netconvert = [
        "netconvert",
        "--osm-files", osm_file,
        "-o", net_file,
        "--geometry.remove", "true",
        "--roundabouts.guess", "true",
        "--ramps.guess", "true",
        "--junctions.join", "true",
        "--tls.guess-signals", "true",
        "--tls.discard-simple", "true",
        "--tls.join", "true",
        "--output.street-names", "true"
    ]
    
    try:
        subprocess.run(cmd_netconvert, check=True, stdout=subprocess.DEVNULL)
        print(f"[SUCCESS] Converted map to {net_file}")
    except subprocess.CalledProcessError as e:
        print("[ERROR] Failed to convert map via netconvert.")
        return
        
    # 3. Generate Random Traffic (Trips)
    print("[INFO] Generating traffic routes for Lucknow...")
    sumo_home = os.environ.get("SUMO_HOME", "")
    randomTrips_script = os.path.join(sumo_home, "tools", "randomTrips.py")
    
    cmd_trips = [
        "python", randomTrips_script,
        "-n", net_file,
        "-r", rou_file,
        "-e", "3600",
        "--fringe-factor", "10",
        "--random"
    ]
    
    try:
        subprocess.run(cmd_trips, check=True, stdout=subprocess.DEVNULL)
        print(f"[SUCCESS] Traffic routes generated to {rou_file}")
    except subprocess.CalledProcessError as e:
        print("[ERROR] Failed to generate routes.")
        return
        
    # 4. Create SUMOCFG
    with open(sumocfg_file, "w") as f:
        f.write(f'''<configuration>
    <input>
        <net-file value="{prefix}.net.xml"/>
        <route-files value="{prefix}.rou.xml"/>
    </input>
    <time>
        <begin value="0"/>
        <end value="3600"/>
    </time>
</configuration>''')

    print(f"[SUCCESS] SUMO config generated: {sumocfg_file}")

if __name__ == "__main__":
    main()
