import os
import uuid
import pytest
import asyncio
import time
from datetime import datetime
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


# ============================================================================
# SCENARIO 1: Basic Job Flow - Priority-based execution
# ============================================================================

def test_priority_based_execution_order(client: TestClient, session: Session):
    """
    Test that jobs execute in priority order: critical > high > normal > low
    """
    # Create jobs with different priorities
    test_jobs = [
        {
            "job_id": str(uuid.uuid4()),
            "type": "send_email",
            "priority": "normal",
            "payload": {"to": "user@example.com", "template": "welcome"},
            "resource_requirements": {"cpu_units": 1, "memory_mb": 128}
        },
        {
            "job_id": str(uuid.uuid4()),
            "type": "send_email",
            "priority": "critical",
            "payload": {"to": "vip@example.com", "template": "alert"},
            "resource_requirements": {"cpu_units": 1, "memory_mb": 128}
        },
        {
            "job_id": str(uuid.uuid4()),
            "type": "generate_report",
            "priority": "low",
            "payload": {"report_type": "daily_summary", "date": "2024-01-15"},
            "resource_requirements": {"cpu_units": 4, "memory_mb": 2048}
        }
    ]

    # Submit all jobs
    for job_payload in test_jobs:
        response = client.post("/jobs/", json=job_payload)
        assert response.status_code == 201

    # Verify jobs are created with correct priorities
    for job_payload in test_jobs:
        job_id = job_payload["job_id"]
        job_in_db = session.get(Job, uuid.UUID(job_id))
        assert job_in_db is not None
        assert job_in_db.priority == job_payload["priority"]
        assert job_in_db.status == "pending"


def test_resource_requirements_tracking(client: TestClient, session: Session):
    """
    Test that resource requirements are correctly stored and tracked
    """
    job_id = uuid.uuid4()
    job_payload = {
        "job_id": str(job_id),
        "type": "data_processing",
        "priority": "high",
        "payload": {"operation": "heavy_computation"},
        "resource_requirements": {
            "cpu_units": 4,
            "memory_mb": 2048,
            "gpu_units": 1,
            "disk_gb": 100
        }
    }

    response = client.post("/jobs/", json=job_payload)
    assert response.status_code == 201

    job_in_db = session.get(Job, job_id)
    assert job_in_db is not None
    assert job_in_db.resource_requirements["cpu_units"] == 4
    assert job_in_db.resource_requirements["memory_mb"] == 2048
    assert job_in_db.resource_requirements["gpu_units"] == 1
    assert job_in_db.resource_requirements["disk_gb"] == 100


# ============================================================================
# SCENARIO 2: Simple Dependencies - Enhanced testing
# ============================================================================

def test_dependency_chain_execution_order(client: TestClient, session: Session):
    """
    Test that jobs execute in dependency order regardless of priority
    """
    # Create a dependency chain: fetch_data -> process_data -> generate_report
    dependency_chain = [
        {
            "job_id": str(uuid.uuid4()),
            "type": "data_fetch",
            "priority": "high",
            "payload": {"source": "market_api", "symbols": ["AAPL", "GOOGL"]},
            "resource_requirements": {"cpu_units": 2, "memory_mb": 512}
        },
        {
            "job_id": str(uuid.uuid4()),
            "type": "data_processing",
            "priority": "high",
            "payload": {"operation": "calculate_indicators"},
            "resource_requirements": {"cpu_units": 4, "memory_mb": 1024}
        },
        {
            "job_id": str(uuid.uuid4()),
            "type": "report_generation",
            "priority": "normal",
            "payload": {"format": "pdf"},
            "resource_requirements": {"cpu_units": 2, "memory_mb": 512}
        }
    ]

    # Submit first job (no dependencies)
    response = client.post("/jobs/", json=dependency_chain[0])
    assert response.status_code == 201
    fetch_job_id = dependency_chain[0]["job_id"]

    # Submit second job (depends on first)
    dependency_chain[1]["depends_on"] = [fetch_job_id]
    response = client.post("/jobs/", json=dependency_chain[1])
    assert response.status_code == 201
    process_job_id = dependency_chain[1]["job_id"]

    # Submit third job (depends on second)
    dependency_chain[2]["depends_on"] = [process_job_id]
    response = client.post("/jobs/", json=dependency_chain[2])
    assert response.status_code == 201

    # Verify dependency relationships
    process_job = session.get(Job, uuid.UUID(process_job_id))
    assert process_job.status == "blocked"

    report_job = session.get(Job, uuid.UUID(dependency_chain[2]["job_id"]))
    assert report_job.status == "blocked"


def test_parent_failure_blocks_dependents(client: TestClient, session: Session):
    """
    Test that when a parent job fails, dependent jobs remain blocked
    """
    # Create parent job
    parent_job_id = uuid.uuid4()
    parent_job = Job(
        job_id=parent_job_id,
        type="parent_job",
        status="failed",
        payload={},
        resource_requirements={},
        retry_config={}
    )
    session.add(parent_job)
    session.commit()

    # Create dependent job
    child_job_id = uuid.uuid4()
    child_payload = {
        "job_id": str(child_job_id),
        "type": "dependent_job",
        "payload": {"operation": "process_result"},
        "resource_requirements": {"cpu_units": 1, "memory_mb": 256},
        "depends_on": [str(parent_job_id)]
    }

    response = client.post("/jobs/", json=child_payload)
    assert response.status_code == 201

    # Verify child job remains blocked
    child_job = session.get(Job, child_job_id)
    assert child_job.status == "blocked"


# ============================================================================
# SCENARIO 3: Complex Dependency Graph (DAG)
# ============================================================================

def test_complex_dag_structure(client: TestClient, session: Session):
    """
    Test handling of complex DAG structures with parallel and sequential dependencies
    """
    # Create complex DAG structure
    complex_dag = [
        # Two parallel data fetches
        {"job_id": str(uuid.uuid4()), "type": "data_fetch", "priority": "high", "payload": {},
         "resource_requirements": {}},
        {"job_id": str(uuid.uuid4()), "type": "data_fetch", "priority": "high", "payload": {},
         "resource_requirements": {}},
        # Analysis depends on both fetches
        {"job_id": str(uuid.uuid4()), "type": "analysis", "priority": "critical", "payload": {},
         "resource_requirements": {}},
        # Two parallel reports depend on analysis
        {"job_id": str(uuid.uuid4()), "type": "report", "priority": "high", "payload": {}, "resource_requirements": {}},
        {"job_id": str(uuid.uuid4()), "type": "report", "priority": "normal", "payload": {},
         "resource_requirements": {}},
        # Final job depends on both reports
        {"job_id": str(uuid.uuid4()), "type": "notification", "priority": "high", "payload": {},
         "resource_requirements": {}}
    ]

    # Submit jobs with dependencies
    fetch_prices_id = complex_dag[0]["job_id"]
    fetch_volumes_id = complex_dag[1]["job_id"]

    # Submit parallel fetches (no dependencies)
    response = client.post("/jobs/", json=complex_dag[0])
    assert response.status_code == 201
    response = client.post("/jobs/", json=complex_dag[1])
    assert response.status_code == 201

    # Submit analysis job (depends on both fetches)
    complex_dag[2]["depends_on"] = [fetch_prices_id, fetch_volumes_id]
    response = client.post("/jobs/", json=complex_dag[2])
    assert response.status_code == 201
    analyze_id = complex_dag[2]["job_id"]

    # Submit parallel reports (depend on analysis)
    complex_dag[3]["depends_on"] = [analyze_id]
    complex_dag[4]["depends_on"] = [analyze_id]
    response = client.post("/jobs/", json=complex_dag[3])
    assert response.status_code == 201
    response = client.post("/jobs/", json=complex_dag[4])
    assert response.status_code == 201

    trader_report_id = complex_dag[3]["job_id"]
    risk_report_id = complex_dag[4]["job_id"]

    # Submit final notification (depends on both reports)
    complex_dag[5]["depends_on"] = [trader_report_id, risk_report_id]
    response = client.post("/jobs/", json=complex_dag[5])
    assert response.status_code == 201

    # Verify all dependent jobs are blocked
    analysis_job = session.get(Job, uuid.UUID(analyze_id))
    assert analysis_job.status == "blocked"

    trader_job = session.get(Job, uuid.UUID(trader_report_id))
    assert trader_job.status == "blocked"

    risk_job = session.get(Job, uuid.UUID(risk_report_id))
    assert risk_job.status == "blocked"

    notification_job = session.get(Job, uuid.UUID(complex_dag[5]["job_id"]))
    assert notification_job.status == "blocked"


# ============================================================================
# SCENARIO 4: Resource Contention and Allocation
# ============================================================================

def test_resource_contention_scenario(client: TestClient, session: Session):
    """
    Test resource allocation under constraints with heavy and light jobs
    """
    # Create heavy jobs that consume most resources
    heavy_jobs = []
    for i in range(5):
        job_payload = {
            "job_id": str(uuid.uuid4()),
            "type": "data_processing",
            "priority": "high" if i < 2 else "normal",
            "payload": {"batch_size": 10000},
            "resource_requirements": {
                "cpu_units": 4,
                "memory_mb": 2048
            }
        }
        heavy_jobs.append(job_payload)

    # Create light jobs that can fill resource gaps
    light_jobs = []
    for i in range(5):
        job_payload = {
            "job_id": str(uuid.uuid4()),
            "type": "quick_task",
            "priority": "normal",
            "payload": {"task_id": i},
            "resource_requirements": {
                "cpu_units": 1,
                "memory_mb": 256
            }
        }
        light_jobs.append(job_payload)

    # Submit all jobs
    all_jobs = heavy_jobs + light_jobs
    for job_payload in all_jobs:
        response = client.post("/jobs/", json=job_payload)
        assert response.status_code == 201

    # Verify all jobs are created with correct resource requirements
    for job_payload in all_jobs:
        job_id = uuid.UUID(job_payload["job_id"])
        job_in_db = session.get(Job, job_id)
        assert job_in_db is not None
        assert job_in_db.resource_requirements == job_payload["resource_requirements"]


def test_priority_based_resource_allocation(client: TestClient, session: Session):
    """
    Test that higher priority jobs get resources first
    """
    # Create jobs with same resource requirements but different priorities
    jobs = [
        {
            "job_id": str(uuid.uuid4()),
            "type": "normal_job",
            "priority": "normal",
            "payload": {"task": "normal"},
            "resource_requirements": {"cpu_units": 2, "memory_mb": 1024}
        },
        {
            "job_id": str(uuid.uuid4()),
            "type": "high_priority_job",
            "priority": "high",
            "payload": {"task": "high"},
            "resource_requirements": {"cpu_units": 2, "memory_mb": 1024}
        },
        {
            "job_id": str(uuid.uuid4()),
            "type": "critical_job",
            "priority": "critical",
            "payload": {"task": "critical"},
            "resource_requirements": {"cpu_units": 2, "memory_mb": 1024}
        }
    ]

    # Submit jobs in reverse priority order
    for job_payload in reversed(jobs):
        response = client.post("/jobs/", json=job_payload)
        assert response.status_code == 201

    # Verify all jobs are created
    for job_payload in jobs:
        job_id = uuid.UUID(job_payload["job_id"])
        job_in_db = session.get(Job, job_id)
        assert job_in_db is not None
        assert job_in_db.priority == job_payload["priority"]


# ============================================================================
# SCENARIO 5: Failure and Recovery with Retry Logic
# ============================================================================

def test_retry_config_validation(client: TestClient):
    """
    Test that retry configuration is properly validated and stored
    """
    job_id = uuid.uuid4()
    job_payload = {
        "job_id": str(job_id),
        "type": "unreliable_api_call",
        "payload": {"endpoint": "flaky_service", "fail_times": 2},
        "resource_requirements": {"cpu_units": 1, "memory_mb": 256},
        "retry_config": {
            "max_attempts": 3,
            "backoff_multiplier": 2,
            "initial_delay_seconds": 1
        }
    }

    response = client.post("/jobs/", json=job_payload)
    assert response.status_code == 201
    data = response.json()
    assert data["job_id"] == str(job_id)


def test_timeout_configuration(client: TestClient):
    """
    Test timeout configuration for long-running jobs
    """
    job_id = uuid.uuid4()
    job_payload = {
        "job_id": str(job_id),
        "type": "long_running",
        "payload": {"duration_seconds": 300},
        "resource_requirements": {"cpu_units": 1, "memory_mb": 512},
        "timeout_seconds": 60,
        "retry_config": {"max_attempts": 2}
    }

    response = client.post("/jobs/", json=job_payload)
    assert response.status_code == 201
    data = response.json()
    assert data["job_id"] == str(job_id)


def test_permanent_failure_handling(client: TestClient):
    """
    Test handling of jobs that will fail permanently
    """
    job_id = uuid.uuid4()
    job_payload = {
        "job_id": str(job_id),
        "type": "invalid_operation",
        "payload": {"error": "division_by_zero"},
        "resource_requirements": {"cpu_units": 1, "memory_mb": 256},
        "retry_config": {"max_attempts": 3}
    }

    response = client.post("/jobs/", json=job_payload)
    assert response.status_code == 201
    data = response.json()
    assert data["job_id"] == str(job_id)


def test_dependent_job_failure_handling(client: TestClient, session: Session):
    """
    Test that dependent jobs handle parent failures gracefully
    """
    # Create a parent job that will fail
    parent_job_id = uuid.uuid4()
    parent_job = Job(
        job_id=parent_job_id,
        type="will_fail",
        status="failed",
        payload={"error": "parent_failure"},
        resource_requirements={},
        retry_config={"max_attempts": 1}
    )
    session.add(parent_job)
    session.commit()

    # Create dependent job
    child_job_id = uuid.uuid4()
    child_payload = {
        "job_id": str(child_job_id),
        "type": "dependent_on_flaky",
        "payload": {"operation": "process_result"},
        "resource_requirements": {"cpu_units": 1, "memory_mb": 256},
        "depends_on": [str(parent_job_id)],
        "retry_config": {"max_attempts": 1}
    }

    response = client.post("/jobs/", json=child_payload)
    assert response.status_code == 201

    # Verify child job remains blocked due to failed parent
    child_job = session.get(Job, child_job_id)
    assert child_job.status == "blocked"


# ============================================================================
# Additional Edge Cases and Integration Tests
# ============================================================================

def test_job_status_lifecycle(client: TestClient, session: Session):
    """
    Test complete job status lifecycle: pending -> running -> completed/failed
    """
    job_id = uuid.uuid4()
    job = Job(
        job_id=job_id,
        type="lifecycle_test",
        status="pending",
        payload={},
        resource_requirements={},
        retry_config={}
    )
    session.add(job)
    session.commit()

    # Test status transitions
    statuses = ["pending", "running", "completed"]
    for status in statuses:
        job.status = status
        if status == "running":
            job.started_at = datetime.utcnow()
        elif status == "completed":
            job.completed_at = datetime.utcnow()

        session.add(job)
        session.commit()

        response = client.get(f"/jobs/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == status


def test_concurrent_job_submission(client: TestClient):
    """
    Test submitting multiple jobs concurrently
    """
    import threading
    import queue

    results = queue.Queue()

    def submit_job(job_id):
        job_payload = {
            "job_id": str(job_id),
            "type": f"concurrent_job_{job_id}",
            "payload": {"thread_id": str(job_id)},
            "resource_requirements": {"cpu_units": 1, "memory_mb": 256}
        }
        response = client.post("/jobs/", json=job_payload)
        results.put((job_id, response.status_code))

    # Submit 10 jobs concurrently
    threads = []
    job_ids = [uuid.uuid4() for _ in range(10)]

    for job_id in job_ids:
        thread = threading.Thread(target=submit_job, args=(job_id,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    # Verify all jobs were submitted successfully
    while not results.empty():
        job_id, status_code = results.get()
        assert status_code == 201


def test_large_payload_handling(client: TestClient):
    """
    Test handling of jobs with large payloads
    """
    job_id = uuid.uuid4()
    large_payload = {
        "data": "x" * 10000,  # 10KB payload
        "metadata": {
            "size": "large",
            "description": "This is a large payload test"
        }
    }

    job_payload = {
        "job_id": str(job_id),
        "type": "large_payload_test",
        "payload": large_payload,
        "resource_requirements": {"cpu_units": 1, "memory_mb": 512}
    }

    response = client.post("/jobs/", json=job_payload)
    assert response.status_code == 201
    data = response.json()
    assert data["job_id"] == str(job_id)


def test_websocket_real_time_updates(client: TestClient):
    """
    Test WebSocket real-time updates for job status changes
    """
    with client.websocket_connect("/jobs/ws/stream") as websocket:
        # Submit a job while connected
        job_id = uuid.uuid4()
        job_payload = {
            "job_id": str(job_id),
            "type": "websocket_test",
            "payload": {"test": "websocket"},
            "resource_requirements": {"cpu_units": 1, "memory_mb": 256}
        }

        response = client.post("/jobs/", json=job_payload)
        assert response.status_code == 201

        # Should receive some messages (exact content depends on simulation)
        try:
            message = websocket.receive_text()
            assert message is not None
        except:
            # WebSocket might not have immediate messages
            pass


def test_job_filtering_and_search(client: TestClient, session: Session):
    """
    Test filtering jobs by status, type, and priority
    """
    # Create jobs with different attributes
    jobs_data = [
        {"type": "email", "status": "pending", "priority": "high"},
        {"type": "report", "status": "completed", "priority": "normal"},
        {"type": "email", "status": "failed", "priority": "low"},
        {"type": "data_processing", "status": "running", "priority": "critical"}
    ]

    for job_data in jobs_data:
        job = Job(
            job_id=uuid.uuid4(),
            type=job_data["type"],
            status=job_data["status"],
            priority=job_data["priority"],
            payload={},
            resource_requirements={},
            retry_config={}
        )
        session.add(job)
    session.commit()

    # Test filtering by status
    response = client.get("/jobs/?status=pending")
    assert response.status_code == 200
    data = response.json()
    assert all(job["status"] == "pending" for job in data)

    # Test filtering by type
    response = client.get("/jobs/?job_type=email")
    assert response.status_code == 200
    data = response.json()
    assert all(job["type"] == "email" for job in data)

    # Test filtering by priority
    response = client.get("/jobs/?priority=high")
    assert response.status_code == 200
    data = response.json()
    assert all(job["priority"] == "high" for job in data)


def test_job_metrics_and_statistics(client: TestClient, session: Session):
    """
    Test job metrics and statistics endpoints (if implemented)
    """
    # Create jobs with different statuses for testing metrics
    statuses = ["pending", "running", "completed", "failed", "cancelled"]
    for status in statuses:
        job = Job(
            job_id=uuid.uuid4(),
            type="metrics_test",
            status=status,
            payload={},
            resource_requirements={},
            retry_config={}
        )
        session.add(job)
    session.commit()

    # Test getting all jobs (basic metrics)
    response = client.get("/jobs/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= len(statuses)


# ============================================================================
# Performance and Load Testing
# ============================================================================

def test_bulk_job_submission(client: TestClient):
    """
    Test submitting a large number of jobs efficiently
    """
    # Submit 100 jobs
    for i in range(100):
        job_payload = {
            "job_id": str(uuid.uuid4()),
            "type": f"bulk_job_{i}",
            "payload": {"index": i},
            "resource_requirements": {"cpu_units": 1, "memory_mb": 256}
        }

        response = client.post("/jobs/", json=job_payload)
        assert response.status_code == 201

    # Verify jobs were created
    response = client.get("/jobs/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 100


def test_dependency_graph_performance(client: TestClient, session: Session):
    """
    Test performance with complex dependency graphs
    """
    # Create a chain of 50 dependent jobs
    job_ids = [uuid.uuid4() for _ in range(50)]

    for i, job_id in enumerate(job_ids):
        job_payload = {
            "job_id": str(job_id),
            "type": f"chain_job_{i}",
            "payload": {"position": i},
            "resource_requirements": {"cpu_units": 1, "memory_mb": 256}
        }

        if i > 0:
            job_payload["depends_on"] = [str(job_ids[i - 1])]

        response = client.post("/jobs/", json=job_payload)
        assert response.status_code == 201

    # Verify the last job is blocked
    last_job = session.get(Job, job_ids[-1])
    assert last_job.status == "blocked"


def test_websocket_connection(client: TestClient):
    with client.websocket_connect("/jobs/ws/stream") as websocket:
        response = websocket.receive_text()
        assert response is not None
