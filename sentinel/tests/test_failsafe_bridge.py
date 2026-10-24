"""
sentinel/tests/test_failsafe_bridge.py
=======================================
Unit tests for SentinelFailsafeBridge.
"""

from deployment.failsafe import FailsafeWatchdog, SystemState
from sentinel.registry import FlaggedVehicleRegistry, FlaggedVehicle
from sentinel.intercept.predictor import MarkovPathPredictor
from sentinel.intercept.orchestrator import InterceptOrchestrator
from sentinel.intercept.failsafe_bridge import SentinelFailsafeBridge


def test_failsafe_bridge_normal_action():
    wd = FailsafeWatchdog()
    wd.ping()
    bridge = SentinelFailsafeBridge(watchdog=wd)

    res = bridge.resolve_action(
        junction_id="J1",
        requested_duration=25,
        inference_latency=0.1,
    )
    assert res["mode"] == "NORMAL_AI"
    assert res["duration"] == 25


def test_failsafe_bridge_emergency_preemption_overrides_intercept(tmp_path):
    reg = FlaggedVehicleRegistry(db_path=str(tmp_path / "reg.db"))
    reg.add(FlaggedVehicle("UP32STOLEN", "theft", "HQ", intercept_authorized=True))

    orch = InterceptOrchestrator(
        registry=reg,
        predictor=MarkovPathPredictor(),
        audit_file=str(tmp_path / "audit.jsonl"),
    )
    orch.request_intercept("UP32STOLEN", "J1", "HQ", "pursuit")

    wd = FailsafeWatchdog()
    wd.ping()
    bridge = SentinelFailsafeBridge(watchdog=wd, orchestrator=orch)

    # Without emergency vehicle: Intercept override applied
    res_int = bridge.resolve_action(
        junction_id="J1",
        requested_duration=25,
        inference_latency=0.1,
        emergency_vehicle_present=False,
    )
    assert res_int["mode"] == "INTERCEPT_OVERRIDE"

    # With emergency vehicle: Emergency preemption takes absolute priority
    res_em = bridge.resolve_action(
        junction_id="J1",
        requested_duration=25,
        inference_latency=0.1,
        emergency_vehicle_present=True,
    )
    assert res_em["mode"] == "EMERGENCY_PREEMPT"
    assert res_em["duration"] == 45


def test_failsafe_bridge_watchdog_failure():
    wd = FailsafeWatchdog(max_inference_latency=0.2)
    wd.ping()
    bridge = SentinelFailsafeBridge(watchdog=wd)

    # Extreme latency triggers watchdog fallback
    res = bridge.resolve_action(
        junction_id="J1",
        requested_duration=25,
        inference_latency=0.8,
    )
    assert res["mode"] == "WATCHDOG_FALLBACK"
    assert res["duration"] == 30
