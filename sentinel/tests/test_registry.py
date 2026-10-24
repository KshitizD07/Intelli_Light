"""
sentinel/tests/test_registry.py
================================
Unit tests for FlaggedVehicleRegistry.
"""

import os
import tempfile
import pytest
from sentinel.registry import FlaggedVehicleRegistry, FlaggedVehicle


@pytest.fixture
def registry(tmp_path):
    db = str(tmp_path / "test_registry.db")
    return FlaggedVehicleRegistry(db_path=db)


def test_add_and_lookup(registry):
    v = FlaggedVehicle(plate="UP32AB1234", flag_reason="test", authority="Test HQ")
    registry.add(v)
    result = registry.lookup("UP32AB1234")
    assert result is not None
    assert result.plate == "UP32AB1234"
    assert result.flag_reason == "test"


def test_plate_normalized_uppercase(registry):
    v = FlaggedVehicle(plate="up32ab1234", flag_reason="test", authority="Test HQ")
    registry.add(v)
    assert registry.is_flagged("UP32AB1234")
    assert registry.is_flagged("up32ab1234")
    assert registry.is_flagged("  Up32Ab1234  ")


def test_lookup_missing_returns_none(registry):
    assert registry.lookup("NOTEXIST") is None


def test_is_flagged(registry):
    registry.add(FlaggedVehicle(plate="MH12XY0001", flag_reason="stolen", authority="Mumbai"))
    assert registry.is_flagged("MH12XY0001")
    assert not registry.is_flagged("DL01AB9999")


def test_remove(registry):
    registry.add(FlaggedVehicle(plate="KA01AB1111", flag_reason="wanted", authority="Blr"))
    assert registry.is_flagged("KA01AB1111")
    removed = registry.remove("KA01AB1111")
    assert removed is True
    assert not registry.is_flagged("KA01AB1111")


def test_remove_nonexistent_returns_false(registry):
    assert registry.remove("NOPE9999") is False


def test_authorize_intercept(registry):
    registry.add(FlaggedVehicle(plate="UP32XY9999", flag_reason="stolen", authority="UP"))
    assert not registry.is_intercept_authorized("UP32XY9999")
    ok = registry.authorize_intercept("UP32XY9999")
    assert ok is True
    assert registry.is_intercept_authorized("UP32XY9999")


def test_revoke_intercept(registry):
    registry.add(FlaggedVehicle(plate="TN09AA0001", flag_reason="evader", authority="TN"))
    registry.authorize_intercept("TN09AA0001")
    assert registry.is_intercept_authorized("TN09AA0001")
    registry.revoke_intercept("TN09AA0001")
    assert not registry.is_intercept_authorized("TN09AA0001")


def test_intercept_requires_flag_first(registry):
    # authorize_intercept on a non-existent plate returns False
    ok = registry.authorize_intercept("GHOST9999")
    assert ok is False
    assert not registry.is_intercept_authorized("GHOST9999")


def test_all_flagged(registry):
    registry.add(FlaggedVehicle(plate="AA01BB0001", flag_reason="r1", authority="a1"))
    registry.add(FlaggedVehicle(plate="AA01BB0002", flag_reason="r2", authority="a2"))
    all_v = registry.all_flagged()
    plates = [v.plate for v in all_v]
    assert "AA01BB0001" in plates
    assert "AA01BB0002" in plates


def test_replace_existing(registry):
    registry.add(FlaggedVehicle(plate="UP01AA1111", flag_reason="old", authority="old_auth"))
    registry.add(FlaggedVehicle(plate="UP01AA1111", flag_reason="new", authority="new_auth"))
    result = registry.lookup("UP01AA1111")
    assert result.flag_reason == "new"
    assert result.authority == "new_auth"


def test_seed_demo(registry):
    registry.seed_demo()
    all_v = registry.all_flagged()
    assert len(all_v) == 3
    plates = [v.plate for v in all_v]
    assert "UP32AB1234" in plates
    assert "UP32XY9999" in plates
    assert "UP41BC5678" in plates
    # UP32XY9999 has intercept pre-authorized in seed
    assert registry.is_intercept_authorized("UP32XY9999")
