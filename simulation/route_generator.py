"""
Traffic Scenario Generation Module
===================================

This module handles the generation of realistic traffic scenarios for SUMO simulation.

Features:
- Multiple traffic scenarios (morning rush, evening rush, weekend)
- Curriculum learning support (progressive difficulty)
- Emergency vehicle injection
- Automatic cleanup of old route files
- Realistic vehicle type distribution

Design:
- Creates SUMO-compatible .rou.xml files
- Supports dynamic traffic volume adjustment
- Includes vehicle type definitions with realistic parameters
"""

import os
import random
import glob
import uuid
import logging
from typing import Dict, Optional, Tuple

# Import configuration
from configs.parameters import (
    traffic,
    simulation,
    paths
)

# Setup logging
logger = logging.getLogger(__name__)


# =============================================================================
# ROUTE FILE GENERATION
# =============================================================================

def generate_route_file(
    filename: str,
    scenario: str = "RANDOM",
    curriculum_stage: int = 0,
    complexity_multiplier: float = 1.0
) -> Dict:
    """
    Generate a SUMO route file with realistic traffic scenarios.
    
    This function creates a complete .rou.xml file including:
    - Vehicle type definitions (car, 2-wheeler, bus, ambulance)
    - Route definitions for all four directions
    - Traffic flows based on scenario
    - Optional emergency vehicle
    
    Args:
        filename: Output path for the route file (should end in .rou.xml)
        scenario: Traffic scenario type ("RANDOM", "MORNING_RUSH", "EVENING_RUSH", "WEEKEND")
        curriculum_stage: Current curriculum learning stage (0=easy, 1=medium, 2=hard)
        complexity_multiplier: Additional multiplier for traffic density
    
    Returns:
        Dictionary containing scenario information:
        {
            "scenario": str,
            "flows": dict,
            "emergency": dict or None,
            "curriculum_stage": int,
            "total_flow": int
        }
    
    Raises:
        IOError: If file cannot be written
    
    Example:
        >>> info = generate_route_file(
        ...     "routes/scenario_001.rou.xml",
        ...     scenario="MORNING_RUSH",
        ...     curriculum_stage=2
        ... )
        >>> print(info["total_flow"])
        2400
    """
    logger.debug(f"Generating route file: {filename}, scenario: {scenario}, stage: {curriculum_stage}")
    
    # Select scenario if random
    if scenario == "RANDOM":
        scenario = random.choice(list(traffic.SCENARIOS.keys()))
    
    # Calculate traffic volume based on curriculum stage
    # if True:
    #     base_multiplier = CurriculumConfig.STAGES[curriculum_stage]["max_flow"] / 400.0
    # else:
    #     base_multiplier = 1.0
    curriculum_max_flows = [600, 1100, 1200]
    clamped_stage = max(0, min(len(curriculum_max_flows) - 1, curriculum_stage))
    base_multiplier = curriculum_max_flows[clamped_stage] / 400.0
    
    final_multiplier = base_multiplier * complexity_multiplier
    
    # Get traffic volumes for selected scenario
    flow_defs = _get_flow_definitions(scenario, final_multiplier)
    
    # Randomize flows within scenario ranges
    flows = _randomize_flows(flow_defs)
    
    # Write the route file
    try:
        with open(filename, "w") as f:
            _write_route_file_header(f)
            _write_vehicle_types(f)
            _write_route_definitions(f)
            _write_traffic_flows(f, flows)
            emergency_info = _write_emergency_vehicle(f)
            _write_route_file_footer(f)
        
        # Prepare scenario information
        scenario_info = {
            "scenario": scenario,
            "flows": flows,
            "emergency": emergency_info,
            "curriculum_stage": curriculum_stage,
            "total_flow": sum(flows.values())
        }
        
        logger.debug(f"Generated scenario: {scenario_info}")
        return scenario_info
        
    except IOError as e:
        logger.error(f"Failed to generate route file {filename}: {e}")
        raise


# def _get_flow_definitions(scenario: str, multiplier: float) -> Dict[str, Tuple[int, int]]:
#     """
#     Get flow definitions for a traffic scenario.
    
#     Args:
#         scenario: Scenario name
#         multiplier: Multiplier for traffic volume
    
#     Returns:
#         Dictionary with flow ranges: {"major_in": (min, max), ...}
#     """
#     base_volumes = ScenarioConfig.TRAFFIC_VOLUMES[scenario]
    
#     # Apply multiplier to all volume ranges
#     flow_defs = {}
#     for key, (min_val, max_val) in base_volumes.items():
#         flow_defs[key] = (
#             int(min_val * multiplier),
#             int(max_val * multiplier)
#         )
    
#     return flow_defs

def _get_flow_definitions(scenario: str, multiplier: float) -> Dict[str, Tuple[int, int]]:
    
    # Traffic volumes defined inline (replacing old ScenarioConfig.TRAFFIC_VOLUMES)
    TRAFFIC_VOLUMES = {
        "WEEKEND": {
            "major_in":  (200, 400),
            "major_out": (200, 400),
            "minor":     (100, 200)
        },
        "MORNING_RUSH": {
            "major_in":  (600, 900),
            "major_out": (200, 400),
            "minor":     (200, 400)
        },
        "EVENING_RUSH": {
            "major_in":  (200, 400),
            "major_out": (600, 900),
            "minor":     (200, 400)
        },
        "NIGHT": {
            "major_in":  (50, 150),
            "major_out": (50, 150),
            "minor":     (30, 100)
        }
    }
    
    # Fallback to WEEKEND if scenario not found
    base_volumes = TRAFFIC_VOLUMES.get(scenario, TRAFFIC_VOLUMES["WEEKEND"])
    
    flow_defs = {}
    for key, (min_val, max_val) in base_volumes.items():
        flow_defs[key] = (
            int(min_val * multiplier),
            int(max_val * multiplier)
        )
    
    return flow_defs


def _randomize_flows(flow_defs: Dict[str, Tuple[int, int]]) -> Dict[str, int]:
    flows = {}
    # West to East
    flows["W_E_1"] = random.randint(*flow_defs["major_in"])
    flows["W_E_4"] = random.randint(*flow_defs["major_in"])
    flows["W_E_7"] = random.randint(*flow_defs["major_in"])
    # East to West
    flows["E_W_3"] = random.randint(*flow_defs["major_out"])
    flows["E_W_6"] = random.randint(*flow_defs["major_out"])
    flows["E_W_9"] = random.randint(*flow_defs["major_out"])
    # North to South
    flows["N_S_1"] = random.randint(*flow_defs["minor"])
    flows["N_S_2"] = random.randint(*flow_defs["minor"])
    flows["N_S_3"] = random.randint(*flow_defs["minor"])
    # South to North
    flows["S_N_7"] = random.randint(*flow_defs["minor"])
    flows["S_N_8"] = random.randint(*flow_defs["minor"])
    flows["S_N_9"] = random.randint(*flow_defs["minor"])
    return flows


def _write_route_file_header(f):
    """Write XML header for route file."""
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    f.write('<!-- Generated by IntelliLight Route Generator -->\n')
    f.write('<routes>\n')


def _write_vehicle_types(f):
    """
    Write vehicle type definitions with realistic Indian traffic parameters.
    
    Tuning for Heterogeneous traffic:
    - car: Standard passenger vehicle (reduced minGap for aggressive following)
    - 2-wheeler: Motorcycle/scooter (lateral alignment arbitrary for lane-splitting)
    - bus: Public transport (large, slow)
    - ambulance: Emergency vehicle
    """
    f.write('\n  <!-- Vehicle Type Definitions (Indian Traffic Replica) -->\n')
    
    # Standard car: Aggressive following (minGap=1.0)
    f.write('  <vType id="car" accel="2.9" decel="7.5" sigma="0.7" '
            'length="5" minGap="1.0" maxSpeed="50" guiShape="passenger"/>\n')
    
    # Two-wheeler: Lane-splitting and erratic (sigma=0.9, latAlignment=arbitrary)
    f.write('  <vType id="2-wheeler" accel="3.5" decel="6.0" sigma="0.9" '
            'length="2.2" width="0.8" minGap="0.5" maxSpeed="45" '
            'latAlignment="arbitrary" guiShape="motorcycle"/>\n')
    
    # Bus: Large and disruptive
    f.write('  <vType id="bus" accel="1.2" decel="4.0" sigma="0.6" '
            'length="12" width="2.5" minGap="1.5" maxSpeed="35" guiShape="bus"/>\n')
    
    # Emergency vehicle: High priority
    f.write('  <vType id="ambulance" accel="4.5" decel="8.0" sigma="0.1" '
            'length="7" width="2.2" minGap="1.0" maxSpeed="65" '
            'guiShape="emergency" vClass="emergency"/>\n')


def _write_route_definitions(f):
    f.write('\n  <!-- 3x3 Grid Route Definitions -->\n')

    # West to East
    f.write('  <route id="W_E_1" edges="W1_to_J1 J1_to_J2 J2_to_J3 J3_to_E3"/>\n')
    f.write('  <route id="W_E_4" edges="W4_to_J4 J4_to_J5 J5_to_J6 J6_to_E6"/>\n')
    f.write('  <route id="W_E_7" edges="W7_to_J7 J7_to_J8 J8_to_J9 J9_to_E9"/>\n')

    # East to West
    f.write('  <route id="E_W_3" edges="E3_to_J3 J3_to_J2 J2_to_J1 J1_to_W1"/>\n')
    f.write('  <route id="E_W_6" edges="E6_to_J6 J6_to_J5 J5_to_J4 J4_to_W4"/>\n')
    f.write('  <route id="E_W_9" edges="E9_to_J9 J9_to_J8 J8_to_J7 J7_to_W7"/>\n')

    # North to South
    f.write('  <route id="N_S_1" edges="N1_to_J1 J1_to_J4 J4_to_J7 J7_to_S7"/>\n')
    f.write('  <route id="N_S_2" edges="N2_to_J2 J2_to_J5 J5_to_J8 J8_to_S8"/>\n')
    f.write('  <route id="N_S_3" edges="N3_to_J3 J3_to_J6 J6_to_J9 J9_to_S9"/>\n')

    # South to North
    f.write('  <route id="S_N_7" edges="S7_to_J7 J7_to_J4 J4_to_J1 J1_to_N1"/>\n')
    f.write('  <route id="S_N_8" edges="S8_to_J8 J8_to_J5 J5_to_J2 J2_to_N2"/>\n')
    f.write('  <route id="S_N_9" edges="S9_to_J9 J9_to_J6 J6_to_J3 J3_to_N3"/>\n')



def _write_traffic_flows(f, flows):
    f.write('\n  <!-- Traffic Flows -->\n')
    ep = simulation.EPISODE_LENGTH
    for route_id, flow_val in flows.items():
        f.write(f'  <flow id="flow_{route_id}" type="car" route="{route_id}" begin="0" end="{ep}" vehsPerHour="{flow_val}"/>\n')


def _write_emergency_vehicle(f) -> Optional[Dict]:
    """
    Optionally write an emergency vehicle.
    
    Args:
        f: File handle
    
    Returns:
        Emergency vehicle info dict if generated, None otherwise
    """
    # Randomly decide whether to include emergency vehicle
    if random.random() < traffic.EVENT_PROBABILITY:
        f.write('\n  <!-- Emergency Vehicle -->\n')
        
        # Random departure time and route
        depart_time = random.randint(*(60, 1500))
        route = random.choice(["W_E", "E_W", "N_S", "S_N"])
        vehicle_id = f"ambulance_{uuid.uuid4().hex[:8]}"
        
        f.write(f'  <vehicle id="{vehicle_id}" type="ambulance" '
                f'route="{route}" depart="{depart_time}" departLane="best"/>\n')
        
        return {
            "id": vehicle_id,
            "route": route,
            "depart": depart_time
        }
    
    return None


def _write_route_file_footer(f):
    """Write XML footer for route file."""
    f.write('\n</routes>\n')


# =============================================================================
# ROUTE FILE CLEANUP
# =============================================================================

def cleanup_old_routes(
    route_dir: Optional[str] = None,
    max_files: Optional[int] = None
) -> int:
    """
    Clean up old route files to prevent disk space issues.
    
    This function removes the oldest route files when the total count
    exceeds the maximum. Only files matching the pattern "route_*.rou.xml"
    are considered.
    
    Args:
        route_dir: Directory containing route files (default: from config)
        max_files: Maximum number of files to keep (default: from config)
    
    Returns:
        Number of files deleted
    
    Example:
        >>> cleaned = cleanup_old_routes()
        >>> print(f"Removed {cleaned} old route files")
    """
    # Use defaults from config if not specified
    if route_dir is None:
        route_dir = paths.ROUTES_DIR
    if max_files is None:
        max_files = 50
    
    try:
        # Find all route files
        pattern = os.path.join(route_dir, "route_*.rou.xml")
        route_files = glob.glob(pattern)
        
        # No cleanup needed if under limit
        if len(route_files) <= max_files:
            return 0
        
        # Sort by creation time (oldest first)
        route_files.sort(key=os.path.getctime)
        
        # Remove oldest files to get back to limit
        files_to_remove = route_files[:len(route_files) - max_files]
        cleaned_count = 0
        
        for file_path in files_to_remove:
            try:
                os.remove(file_path)
                cleaned_count += 1
                logger.debug(f"Removed old route file: {file_path}")
            except OSError as e:
                logger.warning(f"Failed to remove {file_path}: {e}")
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} old route files")
        
        return cleaned_count
        
    except Exception as e:
        logger.error(f"Route cleanup failed: {e}")
        return 0


def get_route_file_stats(route_dir: Optional[str] = None) -> Dict:
    """
    Get statistics about route files in directory.
    
    Args:
        route_dir: Directory to analyze (default: from config)
    
    Returns:
        Dictionary with statistics:
        {
            "total_files": int,
            "total_size_mb": float,
            "oldest_file": str,
            "newest_file": str
        }
    """
    if route_dir is None:
        route_dir = paths.ROUTES_DIR
    
    try:
        pattern = os.path.join(route_dir, "route_*.rou.xml")
        route_files = glob.glob(pattern)
        
        if not route_files:
            return {
                "total_files": 0,
                "total_size_mb": 0.0,
                "oldest_file": None,
                "newest_file": None
            }
        
        # Calculate total size
        total_size = sum(os.path.getsize(f) for f in route_files)
        
        # Find oldest and newest
        route_files.sort(key=os.path.getctime)
        
        return {
            "total_files": len(route_files),
            "total_size_mb": total_size / (1024 * 1024),
            "oldest_file": os.path.basename(route_files[0]),
            "newest_file": os.path.basename(route_files[-1])
        }
        
    except Exception as e:
        logger.error(f"Failed to get route file stats: {e}")
        return {"error": str(e)}


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def generate_unique_filename(route_dir: Optional[str] = None, prefix: str = "route") -> str:
    """
    Generate a unique filename for a route file.
    
    Args:
        route_dir: Directory where file will be created (default: from config)
        prefix: Filename prefix (default: "route")
    
    Returns:
        Full path to unique route file
    
    Example:
        >>> filename = generate_unique_filename()
        >>> print(filename)
        data/generated_routes/route_a3f2b1c4.rou.xml
    """
    if route_dir is None:
        route_dir = paths.ROUTES_DIR
    
    # Ensure directory exists
    os.makedirs(route_dir, exist_ok=True)
    
    # Generate unique ID
    unique_id = uuid.uuid4().hex[:8]
    filename = f"{prefix}_{unique_id}.rou.xml"
    
    return os.path.join(route_dir, filename)


def validate_route_file(filename: str) -> bool:
    """
    Validate that a route file exists and is readable.
    
    Args:
        filename: Path to route file
    
    Returns:
        True if file is valid, False otherwise
    """
    if not os.path.exists(filename):
        logger.error(f"Route file does not exist: {filename}")
        return False
    
    if not os.path.isfile(filename):
        logger.error(f"Route file is not a file: {filename}")
        return False
    
    if not filename.endswith('.rou.xml'):
        logger.warning(f"Route file has unexpected extension: {filename}")
    
    # Try to read first few bytes to ensure it's accessible
    try:
        with open(filename, 'r') as f:
            f.read(100)
        return True
    except Exception as e:
        logger.error(f"Cannot read route file {filename}: {e}")
        return False


# =============================================================================
# MODULE INITIALIZATION
# =============================================================================

# =============================================================================
# COMPATIBILITY WRAPPER CLASS
# =============================================================================

class RouteGenerator:
    """
    Wrapper class for route generation functions.
    This exists for compatibility with modules that expect a class interface.
    """

    def generate_unique_filename(self, prefix: str = "route"):
        return generate_unique_filename(prefix=prefix)

    def generate_route_file(self, filename: str, scenario="RANDOM", curriculum_stage=0):
        return generate_route_file(filename, scenario, curriculum_stage)
    def cleanup_old_routes(self, max_files: int =None)-> int:
        from pathlib import Path
        # ResourceConfig doesn't exist; use a sensible default
        max_files = max_files or 50
        route_dir = Path(paths.ROUTES_DIR)
        route_files=list(route_dir.glob("route_*.rou.xml"))
        route_files.sort(key=lambda f: f.stat().st_mtime)
        num_to_delete=max(0, len(route_files)-max_files)
        deleted=0

        for old_file in route_files[:num_to_delete]:
            try:
                old_file.unlink()
                deleted+=1
            except Exception as e:
                logger.warning(f"Failed to delete {old_file}: {e}")

        if deleted>0:
            logger.debug(f"Cleaned up {deleted} old route files")
        return deleted

# Ensure route directory exists when module is imported
os.makedirs(paths.ROUTES_DIR, exist_ok=True)

if __name__ == "__main__":
    # Simple test if run directly
    print("=== Route Generator Test ===")
    
    # Generate a test route file
    test_file = generate_unique_filename()
    print(f"\nGenerating test route file: {test_file}")
    
    info = generate_route_file(test_file, scenario="MORNING_RUSH", curriculum_stage=1)
    
    print(f"\nScenario Info:")
    print(f"  Scenario: {info['scenario']}")
    print(f"  Total Flow: {info['total_flow']} vehicles/hour")
    print(f"  Emergency: {'Yes' if info['emergency'] else 'No'}")
    print(f"  Flows: {info['flows']}")
    
    # Check if file was created
    if validate_route_file(test_file):
        print(f"\n Route file created successfully")
        
        # Show file stats
        stats = get_route_file_stats()
        print(f"\nRoute Directory Stats:")
        print(f"  Total files: {stats['total_files']}")
        print(f"  Total size: {stats['total_size_mb']:.2f} MB")
    else:
        print(f"\n Route file creation failed")