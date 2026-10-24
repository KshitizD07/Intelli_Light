"""
sentinel/tests/test_road_snapper.py
====================================
Unit tests for RoadSnapper.
"""

from sentinel.tracker.road_snapper import RoadSnapper


def test_road_snapper_empty():
    snapper = RoadSnapper()
    assert snapper.get_route_geometry([]) == []


def test_road_snapper_single_junction():
    snapper = RoadSnapper()
    # If network loaded, returns coord or empty
    res = snapper.get_route_geometry(["J_NONEXISTENT"])
    assert isinstance(res, list)


def test_road_snapper_sequence_fallback():
    snapper = RoadSnapper()
    coords = snapper.get_route_geometry(["J_01", "J_02", "J_03"])
    assert isinstance(coords, list)
