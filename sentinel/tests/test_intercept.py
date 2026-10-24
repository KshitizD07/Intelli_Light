"""
sentinel/tests/test_intercept.py
=================================
Unit tests for MarkovPathPredictor and InterceptOrchestrator.
"""

import os
import pytest
from sentinel.registry import FlaggedVehicleRegistry, FlaggedVehicle
from sentinel.intercept.predictor import MarkovPathPredictor
from sentinel.intercept.orchestrator import InterceptOrchestrator


@pytest.fixture
def test_setup(tmp_path):
    reg_db = str(tmp_path / "test_reg.db")
    audit_file = str(tmp_path / "test_audit.jsonl")

    reg = FlaggedVehicleRegistry(db_path=reg_db)
    pred = MarkovPathPredictor()
    pred.transitions["J1"]["J2"] = 0.8
    pred.transitions["J1"]["J3"] = 0.2
    pred.transitions["J2"]["J4"] = 1.0

    orch = InterceptOrchestrator(registry=reg, predictor=pred, audit_file=audit_file)
    return reg, pred, orch, audit_file


def test_markov_predictions(test_setup):
    _, pred, _, _ = test_setup
    top = pred.predict_next_junctions("J1", top_k=2)
    assert len(top) == 2
    assert top[0][0] == "J2"
    assert top[0][1] == 0.8


def test_intercept_authorization_required(test_setup):
    reg, _, orch, _ = test_setup
    # Plate not in registry
    res1 = orch.request_intercept("UNKNOWN", "J1", "HQ", "test")
    assert res1["success"] is False
    assert "not in the flagged registry" in res1["error"]

    # Plate in registry but NOT authorized
    reg.add(FlaggedVehicle(plate="UP32MONITOR", flag_reason="watch", authority="HQ", intercept_authorized=False))
    res2 = orch.request_intercept("UP32MONITOR", "J1", "HQ", "test")
    assert res2["success"] is False
    assert "not authorized" in res2["error"]


def test_intercept_execution_and_audit(test_setup):
    reg, _, orch, audit_file = test_setup
    plate = "UP32STOLEN"
    reg.add(FlaggedVehicle(plate=plate, flag_reason="stolen", authority="HQ", intercept_authorized=True))

    res = orch.request_intercept(plate, "J1", "OFFICER_1", "chase")
    assert res["success"] is True
    assert res["plate"] == plate
    assert len(res["overridden_junctions"]) > 0

    # Overrides returned
    overrides = orch.get_signal_overrides()
    assert len(overrides) > 0
    assert any(ov["target_plate"] == plate for ov in overrides.values())

    # Audit log verification
    assert os.path.exists(audit_file)
    with open(audit_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) >= 1
        assert "INTERCEPT_INITIATED" in lines[-1]
        assert "record_hash" in lines[-1]


def test_cancel_intercept(test_setup):
    reg, _, orch, _ = test_setup
    plate = "UP32CHASE"
    reg.add(FlaggedVehicle(plate=plate, flag_reason="evasion", authority="HQ", intercept_authorized=True))
    orch.request_intercept(plate, "J1", "OFFICER_1", "test")

    ok = orch.cancel_intercept(plate, "OFFICER_1")
    assert ok is True
    assert len(orch.get_signal_overrides()) == 0
