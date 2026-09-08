import pytest
from fastapi.testclient import TestClient
from src.schemas.request_schemas import DriverVerificationRequest, BatchDriverVerificationRequest

def test_health_liveness(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_health_readiness(client: TestClient):
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ready", "not_ready")
    assert "storage" in data

def test_single_driver_verification_stub(client: TestClient):
    payload = {
        "driver_id": "test-driver-1",
        "mobile_number": "9876543210",
        "vehicle_class": "2 wheeler"
    }
    response = client.post("/api/v1/verify-driver", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["driver_id"] == "test-driver-1"
    assert data["status"] == "REJECTED"
    assert "AADHAAR_NOT_FOUND" in data["rejection_reasons"]

def test_batch_driver_verification_stub(client: TestClient):
    payload = {
        "drivers": [
            {
                "driver_id": "driver-1",
                "mobile_number": "1111111111",
                "vehicle_class": "2 wheeler"
            },
            {
                "driver_id": "driver-2",
                "mobile_number": "2222222222",
                "vehicle_class": "car"
            }
        ]
    }
    response = client.post("/api/v1/batch-verify", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 2
    assert len(data["results"]) == 2

def test_invalid_mobile_number_rejected(client: TestClient):
    payload = {
        "driver_id": "bad-driver",
        "mobile_number": "not-a-number",
        "vehicle_class": "2 wheeler"
    }
    response = client.post("/api/v1/verify-driver", json=payload)
    assert response.status_code == 422

def test_empty_batch_rejected(client: TestClient):
    payload = {"drivers": []}
    response = client.post("/api/v1/batch-verify", json=payload)
    assert response.status_code == 422
