import os
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import SQLModel, create_engine, Session

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


def test_submit_job_no_dependencies(client: TestClient):
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
    with Session(engine) as session:
        job_in_db = session.get(Job, job_id)
        assert job_in_db is not None
        assert job_in_db.status == "pending"
        assert len(job_in_db.dependencies) == 0


def test_submit_job_with_dependencies(client: TestClient):
    """
    Tests successful submission of a job that depends on two other jobs.
    """
    # 1. Create prerequisite jobs directly in the test DB
    parent_job_1_id = uuid.uuid4()
    parent_job_2_id = uuid.uuid4()

    with Session(engine) as session:
        parent_job_1 = Job(id=parent_job_1_id, status="completed", payload={}, resource_requirements={},
                           retry_config={})
        parent_job_2 = Job(id=parent_job_2_id, status="completed", payload={}, resource_requirements={},
                           retry_config={})
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
    with Session(engine) as session:
        job_in_db = session.get(Job, child_job_id)
        assert job_in_db is not None
        assert job_in_db.status == "blocked"

        # Verify that the dependency links were created
        deps = session.query(JobDep).filter(JobDep.job_id == child_job_id).all()
        assert len(deps) == 2
        dep_ids_in_db = {str(dep.depends_on_job_id) for dep in deps}
        assert str(parent_job_1_id) in dep_ids_in_db
        assert str(parent_job_2_id) in dep_ids_in_db


def test_submit_job_conflict(client: TestClient):
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
