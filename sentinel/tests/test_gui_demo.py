"""
Unit Tests for Sentinel + Intelli-Light SUMO GUI Demo Module.
"""

from unittest.mock import MagicMock, patch
import pytest

from sentinel.gui_demo import find_sumo_binary, run_gui_scenario
from sentinel.intercept.tactical_bridge import TacticalStage


def test_find_sumo_binary_fallback():
    """Verify binary discovery falls back to 'sumo' gracefully if sumo-gui is unavailable."""
    with patch("shutil.which", return_value=None):
        with patch("os.path.exists", return_value=False):
            bin_path = find_sumo_binary(use_gui=False)
            assert "sumo" in bin_path


def test_gui_scenario_with_mock_traci():
    """Verify TraCI simulation step loop, target coloring, and tactical signal regulation."""
    mock_traci = MagicMock()
    mock_traci.vehicle.getIDList.return_value = ["veh_0", "veh_1"]
    mock_traci.vehicle.getSpeed.return_value = 12.0
    mock_traci.vehicle.getLaneID.return_value = "edge_0_0"
    mock_traci.vehicle.getRoadID.return_value = "edge_0"
    mock_traci.edge.getToJunction.return_value = "J_MOCK_1"
    mock_traci.vehicle.getPosition.return_value = (500.0, 500.0)
    mock_traci.lane.getLength.return_value = 300.0
    mock_traci.vehicle.getLanePosition.return_value = 150.0
    mock_traci.vehicle.getNextTLS.return_value = [("TLS_J1", 0, 80.0, "r")]
    mock_traci.trafficlight.getIDList.return_value = ["TLS_J1"]
    mock_traci.trafficlight.getRedYellowGreenState.return_value = "GGGG"

    with patch.dict("sys.modules", {"traci": mock_traci}):
        run_gui_scenario(
            cfg_file="dummy.sumocfg",
            target_plate="UP32XY9999",
            use_gui=False,
            delay_ms=0,
            max_steps=5,
            auto_intercept_step=2,
            manual_mode=False,
        )

        # Assert target vehicle was colored bright red
        mock_traci.vehicle.setColor.assert_any_call("veh_0", (255, 20, 20, 255))
        # Assert simulation steps were executed
        assert mock_traci.simulationStep.call_count == 5
        # Assert TraCI was properly closed
        mock_traci.close.assert_called_once()


def test_gui_scenario_option_a_apprehension_removal():
    """Verify that when suspect halts in containment, vehicle is removed and signal program is restored."""
    mock_traci = MagicMock()
    mock_traci.vehicle.getIDList.return_value = ["veh_0", "veh_1"]
    # Vehicle speed is 0.0 m/s (halted) at close range (10m)
    mock_traci.vehicle.getSpeed.return_value = 0.0
    mock_traci.vehicle.getLaneID.return_value = "edge_0_0"
    mock_traci.vehicle.getRoadID.return_value = "edge_0"
    mock_traci.edge.getToJunction.return_value = "J_MOCK_1"
    mock_traci.vehicle.getPosition.return_value = (500.0, 500.0)
    mock_traci.lane.getLength.return_value = 300.0
    mock_traci.vehicle.getLanePosition.return_value = 290.0
    mock_traci.vehicle.getNextTLS.return_value = [("TLS_J1", 0, 10.0, "r")]
    mock_traci.trafficlight.getIDList.return_value = ["TLS_J1"]
    mock_traci.trafficlight.getRedYellowGreenState.return_value = "rrrr"

    with patch.dict("sys.modules", {"traci": mock_traci}):
        with patch("builtins.input", return_value=""):
            run_gui_scenario(
                cfg_file="dummy.sumocfg",
                target_plate="UP32XY9999",
                use_gui=False,
                delay_ms=0,
                max_steps=10,
                auto_intercept_step=1,
                manual_mode=False,
            )

            # Option A assertions:
            # 1. Target vehicle was removed
            mock_traci.vehicle.remove.assert_called_with("veh_0")
            # 2. Traffic light program was restored to normal program "0"
            mock_traci.trafficlight.setProgram.assert_called_with("TLS_J1", "0")


def test_intellilight_controller_queue_clearing():
    """Verify IntelliLightAdaptiveController detects lane queue pressure and transitions phase."""
    from sentinel.intellilight_controller import IntelliLightAdaptiveController

    mock_traci = MagicMock()
    mock_traci.trafficlight.getIDList.return_value = ["TLS_J1"]

    mock_phase_0 = MagicMock()
    mock_phase_0.state = "GGgrrr"
    mock_phase_1 = MagicMock()
    mock_phase_1.state = "yyyrrr"
    mock_phase_2 = MagicMock()
    mock_phase_2.state = "rrrGGG"

    mock_logic = MagicMock()
    mock_logic.phases = [mock_phase_0, mock_phase_1, mock_phase_2]
    mock_traci.trafficlight.getAllProgramLogics.return_value = [mock_logic]
    mock_traci.trafficlight.getPhase.return_value = 0
    mock_traci.trafficlight.getControlledLinks.return_value = [
        [("lane_0_0", "", "")],
        [("lane_0_1", "", "")],
        [("lane_0_2", "", "")],
        [("lane_1_0", "", "")],
        [("lane_1_1", "", "")],
        [("lane_1_2", "", "")],
    ]

    # Congestion on link 3, 4, 5 (Phase 2 approach)
    def mock_halting(lane):
        return 4 if lane.startswith("lane_1") else 0

    def mock_waiting(lane):
        return 30.0 if lane.startswith("lane_1") else 0.0

    mock_traci.lane.getLastStepHaltingNumber.side_effect = mock_halting
    mock_traci.lane.getWaitingTime.side_effect = mock_waiting

    controller = IntelliLightAdaptiveController(min_green=3, yellow_duration=2)

    all_logs = []
    for _ in range(5):
        all_logs.extend(controller.step(mock_traci))

    assert controller.optimizations_count >= 1
    assert any("TLS_J1" in l for l in all_logs)
    # Verify both the intermediate yellow transition and the final green phase were called
    mock_traci.trafficlight.setPhase.assert_any_call("TLS_J1", 1)
    mock_traci.trafficlight.setPhase.assert_called_with("TLS_J1", 2)


def test_intellilight_controller_yields_to_sentinel():
    """Verify controller ignores traffic lights currently overridden by Sentinel."""
    from sentinel.intellilight_controller import IntelliLightAdaptiveController

    mock_traci = MagicMock()
    mock_traci.trafficlight.getIDList.return_value = ["TLS_SENTINEL_TARGET", "TLS_OTHER"]

    controller = IntelliLightAdaptiveController()
    logs = controller.step(mock_traci, overridden_tls={"TLS_SENTINEL_TARGET"})

    # Assert that TLS_SENTINEL_TARGET was never initialized in controller state
    assert "TLS_SENTINEL_TARGET" not in controller.tls_states
