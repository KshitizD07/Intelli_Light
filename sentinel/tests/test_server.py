"""
sentinel/tests/test_server.py
==============================
Integration tests for Sentinel FastAPI Server and REST/WebSocket APIs.
"""

import pytest
from starlette.testclient import TestClient

from sentinel.server import app


@pytest.fixture(scope="module")
def client():
    # Use lifespan context
    with TestClient(app) as test_client:
        yield test_client


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "SENTINEL" in response.text


def test_flagged_vehicles_api(client):
    # GET list
    resp = client.get("/api/flagged")
    assert resp.status_code == 200
    initial_list = resp.json()
    assert isinstance(initial_list, list)

    # POST new vehicle
    payload = {
        "plate": "TEST_SERVER_PLATE",
        "flag_reason": "Unit Test Flag",
        "authority": "Test Division",
        "intercept_authorized": False,
        "notes": "Testing API",
    }
    post_resp = client.post("/api/flagged", json=payload)
    assert post_resp.status_code == 200
    assert post_resp.json()["status"] == "registered"

    # Verify present in list
    verify_resp = client.get("/api/flagged")
    plates = [v["plate"] for v in verify_resp.json()]
    assert "TEST_SERVER_PLATE" in plates

    # Authorize intercept
    auth_resp = client.post("/api/flagged/TEST_SERVER_PLATE/authorize")
    assert auth_resp.status_code == 200
    assert auth_resp.json()["status"] == "authorized"


def test_intercept_api(client):
    # Ensure test vehicle is registered with intercept auth
    reg_payload = {
        "plate": "UP32_API_TEST",
        "flag_reason": "Intercept Test",
        "authority": "Test Police",
        "intercept_authorized": True,
        "notes": "",
    }
    client.post("/api/flagged", json=reg_payload)

    # Trigger intercept
    trig_payload = {
        "plate": "UP32_API_TEST",
        "current_junction": "J_010",
        "authorized_by": "COMMANDER",
        "reason": "Test Pursuit",
    }
    trig_resp = client.post("/api/intercept/trigger", json=trig_payload)
    assert trig_resp.status_code == 200
    data = trig_resp.json()
    assert data["success"] is True
    assert "mission_id" in data
    assert len(data["overridden_junctions"]) > 0

    # Check active overrides
    ovr_resp = client.get("/api/intercept/overrides")
    assert ovr_resp.status_code == 200
    overrides = ovr_resp.json()
    assert len(overrides) > 0

    # Cancel intercept
    cancel_payload = {
        "plate": "UP32_API_TEST",
        "cancelled_by": "COMMANDER",
    }
    cancel_resp = client.post("/api/intercept/cancel", json=cancel_payload)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["success"] is True


def test_od_matrix_and_trajectories_api(client):
    resp_od = client.get("/api/od-matrix")
    assert resp_od.status_code == 200
    assert isinstance(resp_od.json(), list)

    resp_traj = client.get("/api/trajectories")
    assert resp_traj.status_code == 200
    assert isinstance(resp_traj.json(), list)


def test_websocket_live_stream(client):
    with client.websocket_connect("/ws/live") as websocket:
        # Upon connect, server immediately pushes camera topology
        data = websocket.receive_json()
        assert "cameras" in data
        assert "metrics" in data
        assert isinstance(data["cameras"], dict)
