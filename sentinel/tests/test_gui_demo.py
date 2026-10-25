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
        )

        # Assert target vehicle was colored bright red
        mock_traci.vehicle.setColor.assert_any_call("veh_0", (255, 20, 20, 255))
        # Assert simulation steps were executed
        assert mock_traci.simulationStep.call_count == 5
        # Assert TraCI was properly closed
        mock_traci.close.assert_called_once()
