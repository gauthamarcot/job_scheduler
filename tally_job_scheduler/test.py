import os
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import SQLModel, create_engine, Session, select

from tally_job_scheduler.models.jobs import Job, JobDep
from .main import app



DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "toor#toor")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5433")
DB_NAME = os.getenv("POSTGRES_DB", "postgres")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL)


@pytest.fixture(name="client")
def client_fixture():
    """
    This fixture creates the database tables before a test runs,
    yields a TestClient instance for making API calls, and then
    drops the tables after the test is complete to ensure isolation.
    """
    # Yield the TestClient to be used by the test function
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(name="session")
def session_fixture():
    with Session(engine) as session:
        yield session


def test_health_endpoint(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["api_status"] == "ok"
    assert data["db_status"] == "ok"


def test_submit_job_no_dependencies(client: TestClient, session: Session):
    """
    Tests successful submission of a simple job with no dependencies.
    """
    job_id = uuid.uuid4()
    job_payload = {
        "job_id": str(job_id),
        "type": "data_processing",
        "payload": {"source": "/path/to/data", "destination": "/path/to/output"},
        "resource_requirements": {"cpu_units": 1, "memory_mb": 512},
    }

    response = client.post("/jobs/", json=job_payload)

    # Assertions
    assert response.status_code == 201
    data = response.json()
    assert data["job_id"] == str(job_id)
    assert data["status"] == "pending"
    assert "created_at" in data
    assert data["priority"] == "normal"

    # Verify in DB
    job_in_db = session.get(Job, job_id)
    assert job_in_db is not None
    assert job_in_db.status == "pending"
    assert len(job_in_db.dependencies) == 0


def test_submit_job_with_dependencies(client: TestClient, session: Session):
    """
    Tests successful submission of a job that depends on two other jobs.
    """
    # 1. Create prerequisite jobs directly in the test DB
    parent_job_1_id = uuid.uuid4()
    parent_job_2_id = uuid.uuid4()

    parent_job_1 = Job(job_id=parent_job_1_id, type="parent1", status="completed", payload={}, 
                      resource_requirements={}, retry_config={})
    parent_job_2 = Job(job_id=parent_job_2_id, type="parent2", status="completed", payload={}, 
                      resource_requirements={}, retry_config={})
    session.add(parent_job_1)
    session.add(parent_job_2)
    session.commit()

    # 2. Define the new job that depends on the previous ones
    child_job_id = uuid.uuid4()
    job_payload = {
        "job_id": str(child_job_id),
        "type": "report_generation",
        "payload": {"report_name": "quarterly_summary"},
        "resource_requirements": {"cpu_units": 1, "memory_mb": 256},
        "depends_on": [str(parent_job_1_id), str(parent_job_2_id)],
    }

    response = client.post("/jobs/", json=job_payload)

    # 3. Assertions
    assert response.status_code == 201
    data = response.json()
    assert data["job_id"] == str(child_job_id)
    assert data["status"] == "blocked"  # Status must be 'blocked' due to dependencies
    assert "created_at" in data

    # 4. Verify relationships in DB
    job_in_db = session.get(Job, child_job_id)
    assert job_in_db is not None
    assert job_in_db.status == "blocked"

    # Verify that the dependency links were created
    deps = session.exec(select(JobDep).where(JobDep.job_id == child_job_id)).all()
    assert len(deps) == 2
    dep_ids_in_db = {str(dep.depends_on_job_id) for dep in deps}
    assert str(parent_job_1_id) in dep_ids_in_db
    assert str(parent_job_2_id) in dep_ids_in_db


def test_submit_job_duplicate_id(client: TestClient):
    """
    Tests that the API returns a 409 Conflict error if a job with the same
    ID is submitted twice.
    """
    job_id = uuid.uuid4()
    job_payload = {
        "job_id": str(job_id),
        "type": "initial_job",
        "payload": {"key": "value"},
        "resource_requirements": {"cpu_units": 1, "memory_mb": 128},
    }

    # First submission should succeed
    response1 = client.post("/jobs/", json=job_payload)
    assert response1.status_code == 201

    # Second submission with the same job_id should fail
    response2 = client.post("/jobs/", json=job_payload)
    assert response2.status_code == 409
    data = response2.json()
    assert "detail" in data
    assert "already exists" in data["detail"]


def test_get_all_jobs(client: TestClient, session: Session):
    job_id = uuid.uuid4()
    job = Job(
        job_id=job_id, 
        type="test_job", 
        status="pending", 
        payload={}, 
        resource_requirements={}, 
        retry_config={}
    )
    session.add(job)
    session.commit()

    response = client.get("/jobs/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(j["job_id"] == str(job_id) for j in data)


def test_get_job_by_id(client: TestClient, session: Session):
    job_id = uuid.uuid4()
    job = Job(
        job_id=job_id, 
        type="test_job", 
        status="pending", 
        payload={}, 
        resource_requirements={}, 
        retry_config={}
    )
    session.add(job)
    session.commit()

    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == str(job_id)
    assert data["type"] == "test_job"


def test_get_job_by_invalid_id(client: TestClient):
    response = client.get("/jobs/invalid-uuid")
    assert response.status_code == 400


def test_get_nonexistent_job(client: TestClient):
    fake_job_id = uuid.uuid4()
    response = client.get(f"/jobs/{fake_job_id}")
    assert response.status_code == 404


def test_cancel_job(client: TestClient, session: Session):
    job_id = uuid.uuid4()
    job = Job(
        job_id=job_id, 
        type="test_job", 
        status="pending", 
        payload={}, 
        resource_requirements={}, 
        retry_config={}
    )
    session.add(job)
    session.commit()

    response = client.patch(f"/jobs/{job_id}/cancel")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Job cancelled successfully"
    assert data["job_id"] == str(job_id)

    job_in_db = session.get(Job, job_id)
    assert job_in_db.status == "cancelled"


def test_cancel_completed_job(client: TestClient, session: Session):
    job_id = uuid.uuid4()
    job = Job(
        job_id=job_id, 
        type="test_job", 
        status="completed", 
        payload={}, 
        resource_requirements={}, 
        retry_config={}
    )
    session.add(job)
    session.commit()

    response = client.patch(f"/jobs/{job_id}/cancel")
    assert response.status_code == 400


def test_cancel_nonexistent_job(client: TestClient):
    fake_job_id = uuid.uuid4()
    response = client.patch(f"/jobs/{fake_job_id}/cancel")
    assert response.status_code == 404


def test_get_job_logs(client: TestClient, session: Session):
    job_id = uuid.uuid4()
    job = Job(
        job_id=job_id, 
        type="test_job", 
        status="pending", 
        payload={}, 
        resource_requirements={}, 
        retry_config={}
    )
    session.add(job)
    session.commit()

    response = client.get(f"/jobs/{job_id}/logs")
    assert response.status_code == 200
    data = response.json()
    assert "logs" in data


def test_submit_job_with_timeout(client: TestClient):
    job_id = uuid.uuid4()
    job_payload = {
        "job_id": str(job_id),
        "type": "long_running_job",
        "payload": {"operation": "heavy_computation"},
        "resource_requirements": {"cpu_units": 4, "memory_mb": 2048},
        "timeout_seconds": 3600
    }

    response = client.post("/jobs/", json=job_payload)
    assert response.status_code == 201
    data = response.json()
    assert data["job_id"] == str(job_id)


def test_submit_job_with_custom_retry_config(client: TestClient):
    job_id = uuid.uuid4()
    job_payload = {
        "job_id": str(job_id),
        "type": "unreliable_job",
        "payload": {"operation": "external_api_call"},
        "resource_requirements": {"cpu_units": 1, "memory_mb": 512},
        "retry_config": {"max_attempts": 5, "backoff_multiplier": 2}
    }

    response = client.post("/jobs/", json=job_payload)
    assert response.status_code == 201
    data = response.json()
    assert data["job_id"] == str(job_id)


def test_submit_job_missing_required_fields(client: TestClient):
    job_payload = {
        "type": "incomplete_job",
        "payload": {"key": "value"}
    }

    response = client.post("/jobs/", json=job_payload)
    assert response.status_code == 422


def test_submit_job_invalid_resource_requirements(client: TestClient):
    job_id = uuid.uuid4()
    job_payload = {
        "job_id": str(job_id),
        "type": "test_job",
        "payload": {"key": "value"},
        "resource_requirements": {"cpu_units": -1, "memory_mb": 0}
    }

    response = client.post("/jobs/", json=job_payload)
    assert response.status_code == 422


def test_circular_dependency_detection(client: TestClient, session: Session):
    job_id = uuid.uuid4()
    job = Job(
        job_id=job_id, 
        type="test_job", 
        status="pending", 
        payload={}, 
        resource_requirements={}, 
        retry_config={}
    )
    session.add(job)
    session.commit()

    job_payload = {
        "job_id": str(uuid.uuid4()),
        "type": "dependent_job",
        "payload": {"key": "value"},
        "resource_requirements": {"cpu_units": 1, "memory_mb": 512},
        "depends_on": [str(job_id)]
    }

    response = client.post("/jobs/", json=job_payload)
    assert response.status_code == 201

    circular_job_payload = {
        "job_id": str(job_id),
        "type": "circular_job",
        "payload": {"key": "value"},
        "resource_requirements": {"cpu_units": 1, "memory_mb": 512},
        "depends_on": [str(job_id)]
    }

    response = client.post("/jobs/", json=circular_job_payload)
    assert response.status_code == 400


def test_websocket_connection(client: TestClient):
    with client.websocket_connect("/jobs/ws/stream") as websocket:
        response = websocket.receive_text()
        assert response is not None


def test_job_status_transitions(client: TestClient, session: Session):
    job_id = uuid.uuid4()
    job = Job(
        job_id=job_id, 
        type="test_job", 
        status="pending", 
        payload={}, 
        resource_requirements={}, 
        retry_config={}
    )
    session.add(job)
    session.commit()

    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"

    job.status = "running"
    session.add(job)
    session.commit()

    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"


def test_job_with_complex_payload(client: TestClient):
    job_id = uuid.uuid4()
    complex_payload = {
        "input_files": ["file1.txt", "file2.txt"],
        "output_format": "json",
        "processing_options": {
            "compression": True,
            "encryption": False,
            "batch_size": 1000
        },
        "metadata": {
            "user_id": "user123",
            "project": "data_analysis",
            "priority": "high"
        }
    }
    
    job_payload = {
        "job_id": str(job_id),
        "type": "complex_processing",
        "payload": complex_payload,
        "resource_requirements": {"cpu_units": 8, "memory_mb": 4096},
        "timeout_seconds": 7200
    }

    response = client.post("/jobs/", json=job_payload)
    assert response.status_code == 201
    data = response.json()
    assert data["job_id"] == str(job_id)
