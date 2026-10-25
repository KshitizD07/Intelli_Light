"""
Sentinel & Intelli-Light Unified Real-Time SUMO GUI Demonstration
==================================================================

Visualizes physical vehicle dynamics, ANPR camera triggers, and
tactical green-metering/red-wall signal regulation in real-time inside SUMO-GUI.

Features:
  1. Dual Viewports:
     - View #0: Global traffic flow overview (Intelli-Light adaptive civilian network).
     - View #1: Sentinel Surveillance Camera (auto-tracking flagged suspect).
  2. Manual Trigger:
     - Press [SPACE] or [R] in this terminal anytime to deploy the Red-Wall.
  3. Option A (Apprehend & Disappear):
     - Suspect is boxed in behind the civilian queue at the red signal.
     - Once halted, suspect is apprehended and removed from the network.
     - Red-wall holds release back to Intelli-Light green cycles, and civilian traffic resumes!
"""

import os
import sys
import time
import math
import argparse
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Auto-configure SUMO_HOME if unset or invalid
if "SUMO_HOME" not in os.environ or not os.path.exists(os.environ.get("SUMO_HOME", "")):
    site_packages_sumo = os.path.join(sys.prefix, "Lib", "site-packages", "sumo")
    if os.path.exists(site_packages_sumo):
        os.environ["SUMO_HOME"] = site_packages_sumo

from sentinel.intercept.tactical_bridge import TacticalGuidanceBridge, TacticalStage
from sentinel.intercept.orchestrator import InterceptOrchestrator
from sentinel.registry import FlaggedVehicleRegistry, FlaggedVehicle
from sentinel.ingestion.event_bus import EventBus
from sentinel.tracker.tracker import TrackerManager
from sentinel.tracker.road_snapper import RoadSnapper
from sentinel.ingestion.sumo_injector import CameraGrid

SUMO_NET_FILE = os.path.join(project_root, "simulation", "lucknow_map", "lucknow.net.xml")


def find_sumo_binary(use_gui: bool = True) -> str:
    """Finds sumo or sumo-gui binary across SUMO_HOME, eclipse-sumo, or PATH."""
    target_name = "sumo-gui" if use_gui else "sumo"

    try:
        import sumolib
        binary = sumolib.checkBinary(target_name)
        if os.path.isabs(binary) and os.path.exists(binary):
            return binary
        import shutil
        found = shutil.which(target_name)
        if found:
            return found
    except Exception:
        pass

    venv_bin = os.path.join(sys.prefix, "Scripts", f"{target_name}.exe")
    if os.path.exists(venv_bin):
        return venv_bin

    sumo_home = os.environ.get("SUMO_HOME", "")
    if sumo_home:
        cand = os.path.join(sumo_home, "bin", f"{target_name}.exe")
        if os.path.exists(cand):
            return cand

    if use_gui:
        print("[SENTINEL-GUI] 'sumo-gui' binary not found directly, falling back to 'sumo' binary...")
        return find_sumo_binary(use_gui=False)

    return "sumo"


def check_manual_trigger() -> bool:
    """Non-blocking keyboard check for Space, R, or Enter on Windows/POSIX."""
    try:
        import msvcrt
        while msvcrt.kbhit():
            ch = msvcrt.getch()
            if ch in (b' ', b'r', b'R', b'\r'):
                return True
    except Exception:
        pass
    return False


def run_gui_scenario(
    cfg_file: str,
    target_plate: str = "UP32XY9999",
    use_gui: bool = True,
    delay_ms: int = 180,
    max_steps: int = 800,
    auto_intercept_step: int = 35,
    manual_mode: bool = True,
):
    """
    Executes the interactive SUMO GUI scenario with Dual Viewports, Manual Red-Wall, and Option A.
    """
    import traci

    binary = find_sumo_binary(use_gui=use_gui)
    print("=" * 72)
    print(" SENTINEL + INTELLI-LIGHT UNIFIED PHYSICAL DEMONSTRATION")
    print("=" * 72)
    print(f"SUMO Binary:    {binary}")
    print(f"Config File:    {cfg_file}")
    print(f"Target Plate:   {target_plate} (Flagged Threat)")
    print(f"Step Delay:     {delay_ms} ms")
    print(f"Controls:       Press [SPACE] or [R] in this terminal to DEPLOY RED-WALL")
    print(f"Post-Action:    Option A (Apprehend, Remove Suspect & Resume Flow)")
    print("=" * 72)

    # Initialize Sentinel Infrastructure
    registry = FlaggedVehicleRegistry()
    registry.add(
        FlaggedVehicle(
            plate=target_plate,
            flag_reason="Stolen Vehicle / Armed Suspect",
            authority="Lucknow Police ICCC",
            intercept_authorized=True,
        )
    )
    road_snapper = RoadSnapper()
    orchestrator = InterceptOrchestrator(registry, road_snapper=road_snapper)
    tactical_bridge = TacticalGuidanceBridge(orchestrator=orchestrator)
    bus = EventBus()
    camera_grid = CameraGrid(SUMO_NET_FILE)
    tracker = TrackerManager(bus=bus, registry=registry, camera_grid=camera_grid)

    cmd = [
        binary,
        "-c", cfg_file,
        "--start",
        "--waiting-time-memory", "1000",
        "--step-length", "1.0",
        "--no-step-log", "true",
    ]

    gui_settings_path = os.path.join(project_root, "simulation", "lucknow_map", "gui-settings.xml")
    if use_gui and os.path.exists(gui_settings_path):
        cmd.extend(["--gui-settings-file", gui_settings_path])

    try:
        traci.start(cmd)
    except Exception as e:
        print(f"[ERROR] Failed to start TraCI with {binary}: {e}")
        return

    print("\n[INFO] TraCI connection established. Simulation running!")
    print("[INFO] Initializing Dual Viewports: Global Traffic Flow & Surveillance HUD...\n")

    target_veh_id = "0"
    target_tls_id = None
    intercept_active = False
    surveillance_locked = False
    apprehended = False
    stopped_count = 0
    post_apprehension_steps = 0
    tls_to_regulate = []

    try:
        step = 0
        while step < max_steps:
            traci.simulationStep()
            step += 1

            active_vehs = traci.vehicle.getIDList()
            if not active_vehs and not apprehended:
                continue

            # Check if target suspect is on the network
            target_present = target_veh_id in active_vehs

            # If target vehicle was removed after apprehension, continue normal flow demonstration
            if apprehended:
                post_apprehension_steps += 1
                if post_apprehension_steps % 5 == 0:
                    print(f"Step {step:03d} | Normal Flow Resumed | Active Civilian Vehicles: {len(active_vehs)}")
                if post_apprehension_steps >= 30:
                    print("\n" + "=" * 72)
                    print(" [DEMONSTRATION COMPLETE] Suspect removed, traffic fully normalized.")
                    print(" Press ENTER in this console to close the SUMO window...")
                    print("=" * 72 + "\n")
                    try:
                        input()
                    except Exception:
                        time.sleep(10.0)
                    break
                if delay_ms > 0:
                    time.sleep(delay_ms / 1000.0)
                continue

            # Ensure valid suspect vehicle
            if not target_present:
                target_veh_id = active_vehs[0]
                target_present = True

            # Style vehicles: Suspect = Bright Red, Civilians = Cyan/White/Yellow
            for vid in active_vehs:
                if vid == target_veh_id:
                    traci.vehicle.setColor(vid, (255, 20, 20, 255))
                else:
                    try:
                        v_num = int(vid)
                        if v_num % 3 == 0:
                            traci.vehicle.setColor(vid, (56, 189, 248, 255))   # Cyan
                        elif v_num % 3 == 1:
                            traci.vehicle.setColor(vid, (241, 245, 249, 255))  # White
                        else:
                            traci.vehicle.setColor(vid, (250, 204, 21, 255))   # Yellow
                    except ValueError:
                        traci.vehicle.setColor(vid, (148, 163, 184, 255))

            # Suspect telemetry
            pos = traci.vehicle.getPosition(target_veh_id)
            speed = traci.vehicle.getSpeed(target_veh_id)
            lane_id = traci.vehicle.getLaneID(target_veh_id)
            edge_id = traci.vehicle.getRoadID(target_veh_id)
            lane_len = traci.lane.getLength(lane_id) if lane_id else 200.0
            lane_pos = traci.vehicle.getLanePosition(target_veh_id) if lane_id else 50.0
            dist_to_end = max(0.0, lane_len - lane_pos)

            # Setup Dual Viewports in GUI
            if use_gui and not surveillance_locked:
                try:
                    # View #0: Overview of city traffic corridor
                    traci.gui.setSchema("View #0", "real world")
                    traci.gui.setZoom("View #0", 1200.0)

                    # View #1: Dedicated Sentinel Surveillance View
                    existing_views = traci.gui.getIDList()
                    surveillance_view = "View #1"
                    if surveillance_view not in existing_views:
                        traci.gui.addView(surveillance_view, "real world")

                    traci.gui.setSchema(surveillance_view, "real world")
                    traci.gui.trackVehicle(surveillance_view, target_veh_id)
                    traci.gui.setZoom(surveillance_view, 3800.0)

                    # Add tactical red marker POI
                    try:
                        traci.poi.add("TARGET_LOCK", pos[0], pos[1], (255, 20, 20, 255), "SUSPECT_PIN", layer=200, width=6, height=6)
                    except Exception:
                        pass

                    surveillance_locked = True
                except Exception:
                    pass

            # Update tactical marker position
            if surveillance_locked:
                try:
                    traci.poi.setPosition("TARGET_LOCK", pos[0], pos[1])
                except Exception:
                    pass

            # Check manual trigger from terminal keypress
            trigger_now = check_manual_trigger()
            if not intercept_active:
                if trigger_now or (not manual_mode and step >= auto_intercept_step):
                    intercept_active = True
                    raw_junc = traci.edge.getToJunction(edge_id) if edge_id and not str(edge_id).startswith(":") else "J_AHEAD"
                    current_junc = str(raw_junc) if raw_junc is not None else "J_AHEAD"
                    orchestrator.request_intercept(
                        plate=target_plate,
                        current_junction=current_junc,
                        authorized_by="OPERATOR_KSHITIZ",
                        reason="Manual Red-Wall Authorization",
                    )
                    print("\n" + "#" * 72)
                    print(f" [SENTINEL RED-WALL ACTIVATED] Target: {target_plate}")
                    print(f" Target Junction: {current_junc} | Authorized by: OPERATOR_KSHITIZ")
                    print(" Downstream signals switched to ALL-RED. Controlled queue forming ahead...")
                    print("#" * 72 + "\n")

            # Check next Traffic Light ahead
            next_tls_list = traci.vehicle.getNextTLS(target_veh_id)
            dist_to_tls = dist_to_end
            if next_tls_list and len(next_tls_list) > 0:
                tls_info = next_tls_list[0]
                target_tls_id = tls_info[0]
                dist_to_tls = tls_info[2]

            # Signal regulation and kinematic guidance
            if intercept_active:
                overrides = orchestrator.get_signal_overrides()
                active_junc = next(iter(overrides.keys())) if overrides else "J_AHEAD"
                directive = tactical_bridge.get_directive(
                    junction_id=active_junc,
                    plate=target_plate,
                    distance_to_junction_m=dist_to_tls,
                )

                if directive:
                    stage = directive.stage
                    target_v = directive.target_speed_mps

                    tls_to_regulate = [target_tls_id] if target_tls_id and target_tls_id in traci.trafficlight.getIDList() else list(traci.trafficlight.getIDList()[:3])

                    if stage in (TacticalStage.CHOKE, TacticalStage.CONTAINMENT):
                        for tid in tls_to_regulate:
                            state = traci.trafficlight.getRedYellowGreenState(tid)
                            all_red = "r" * len(state)
                            traci.trafficlight.setRedYellowGreenState(tid, all_red)
                        traci.vehicle.slowDown(target_veh_id, target_v, 1.5)
                    elif stage == TacticalStage.METERING:
                        traci.vehicle.slowDown(target_veh_id, target_v, 2.0)

                    kmh = speed * 3.6
                    print(
                        f"Step {step:03d} | TLS Dist: {dist_to_tls:5.1f}m | "
                        f"Speed: {speed:4.1f} m/s ({kmh:4.1f} km/h) | "
                        f"Stage: {stage.name:11s} | Regulated Target: {target_v:4.1f} m/s"
                    )

                    # Option A: Detect vehicle stop behind queue -> Apprehend and remove!
                    if stage == TacticalStage.CONTAINMENT and speed < 0.2:
                        stopped_count += 1
                        if stopped_count >= 3:
                            apprehended = True
                            print("\n" + "=" * 72)
                            print(f" [APPREHENSION SUCCESSFUL] Target '{target_plate}' Contained by Tactical Units!")
                            print(" Suspect halted behind civilian queue. Removing vehicle from network.")
                            print(" Releasing Red-Wall hold: Signals restored to Intelli-Light green cycle...")
                            print("=" * 72 + "\n")

                            # Remove vehicle and marker (Option A)
                            try:
                                traci.vehicle.remove(target_veh_id)
                            except Exception:
                                pass
                            try:
                                traci.poi.remove("TARGET_LOCK")
                            except Exception:
                                pass

                            # Cancel intercept and release traffic lights back to normal program
                            orchestrator.cancel_intercept(target_plate, cancelled_by="OPERATOR_KSHITIZ")
                            for tid in tls_to_regulate:
                                try:
                                    traci.trafficlight.setProgram(tid, "0")
                                except Exception:
                                    pass

                            print("[TRAFFIC RESUMED] Downstream signals green. Civilian queue moving smoothly.\n")
                    else:
                        stopped_count = 0
            else:
                kmh = speed * 3.6
                print(
                    f"Step {step:03d} | Normal Flow | Suspect: {speed:4.1f} m/s ({kmh:4.1f} km/h) | "
                    f">>> Press [SPACE] or [R] to DEPLOY RED-WALL <<<"
                )

            if delay_ms > 0:
                time.sleep(delay_ms / 1000.0)

    except KeyboardInterrupt:
        print("\n[INFO] Simulation interrupted by user.")
    finally:
        try:
            traci.close()
        except Exception:
            pass
        print("[SENTINEL-GUI] TraCI session closed.")


def main():
    parser = argparse.ArgumentParser(
        description="Sentinel + Intelli-Light Dual-View TraCI Scenario Visualizer"
    )
    parser.add_argument(
        "--cfg",
        default=str(project_root / "simulation" / "lucknow_map" / "lucknow.sumocfg"),
        help="Path to SUMO .sumocfg file",
    )
    parser.add_argument(
        "--plate",
        default="UP32XY9999",
        help="Target vehicle plate to track and intercept",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Run headless SUMO simulation instead of GUI",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=180,
        help="Delay per step in milliseconds for visual clarity",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=800,
        help="Maximum simulation steps to run",
    )
    parser.add_argument(
        "--intercept-step",
        type=int,
        default=35,
        help="Fallback step at which Red-Wall intercept is authorized if not triggered manually",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-trigger intercept at --intercept-step without waiting for manual keypress",
    )

    args = parser.parse_args()
    run_gui_scenario(
        cfg_file=args.cfg,
        target_plate=args.plate,
        use_gui=not args.no_gui,
        delay_ms=args.delay,
        max_steps=args.max_steps,
        auto_intercept_step=args.intercept_step,
        manual_mode=not args.auto,
    )


if __name__ == "__main__":
    main()
