import os
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Import app after setting a harmless default; test requests override the DB session.
os.environ.setdefault("DATABASE_URL", "sqlite://")
from flowforge.db import Base, get_session
from flowforge import models  # noqa: F401
from flowforge.main import app

TEST_ENGINE = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(bind=TEST_ENGINE, autoflush=False, expire_on_commit=False)
Base.metadata.create_all(bind=TEST_ENGINE)


def override_get_session():
    with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_session] = override_get_session
client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_execute_workflow_and_fetch_execution():
    payload = {
        "name": "Demo workflow",
        "definition": {
            "nodes": [
                {"id": "start", "type": "trigger"},
                {"id": "enrich", "type": "set", "config": {"values": {"ok": True}}},
                {"id": "finish", "type": "output"},
            ],
            "edges": [
                {"source": "start", "target": "enrich"},
                {"source": "enrich", "target": "finish"},
            ],
        },
    }
    created = client.post("/api/workflows", json=payload)
    assert created.status_code == 201, created.text
    workflow_id = created.json()["id"]

    listed = client.get("/api/workflows")
    assert listed.status_code == 200
    assert any(item["id"] == workflow_id for item in listed.json())

    run = client.post(f"/api/workflows/{workflow_id}/execute", json={"input": {"user": "test"}})
    assert run.status_code == 201, run.text
    execution = run.json()
    assert execution["status"] == "succeeded"
    assert execution["result_data"] == {"user": "test", "ok": True}

    fetched = client.get(f"/api/executions/{execution['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == execution["id"]


def test_missing_workflow_returns_404():
    response = client.post("/api/workflows/not-a-real-id/execute", json={"input": {}})
    assert response.status_code == 404


def test_update_workflow_preserves_canvas_positions_and_new_name():
    payload = {
        "name": "Before edit",
        "definition": {
            "nodes": [
                {"id": "start", "type": "trigger", "position": {"x": 64, "y": 96}},
                {"id": "finish", "type": "output", "position": {"x": 380, "y": 96}},
            ],
            "edges": [{"source": "start", "target": "finish"}],
        },
    }
    created = client.post("/api/workflows", json=payload)
    assert created.status_code == 201, created.text
    workflow_id = created.json()["id"]

    payload["name"] = "After edit"
    payload["definition"]["nodes"][1]["position"] = {"x": 460, "y": 128}
    updated = client.put(f"/api/workflows/{workflow_id}", json=payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "After edit"
    assert updated.json()["definition"]["nodes"][1]["position"] == {"x": 460.0, "y": 128.0}


def test_list_executions_can_filter_by_workflow():
    payload = {
        "name": "Execution history test",
        "definition": {
            "nodes": [{"id": "start", "type": "trigger"}, {"id": "finish", "type": "output"}],
            "edges": [{"source": "start", "target": "finish"}],
        },
    }
    created = client.post("/api/workflows", json=payload)
    workflow_id = created.json()["id"]
    run = client.post(f"/api/workflows/{workflow_id}/execute", json={"input": {"value": 7}})
    assert run.status_code == 201, run.text

    listed = client.get("/api/executions", params={"workflow_id": workflow_id, "limit": 5})
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["workflow_id"] == workflow_id
