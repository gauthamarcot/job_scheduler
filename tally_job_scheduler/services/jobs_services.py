import uuid
from datetime import datetime
from typing import List

from fastapi import HTTPException
from sqlmodel import Session

from tally_job_scheduler.models.jobs import Job, JobDep, JobLog
from tally_job_scheduler.schema.job import JobSubmission


def _check_for_job_dep(new_job_id: uuid.UUID, dep: List[uuid.UUID], session: Session):
    pass


def create_new_job(job: JobSubmission, session: Session):
    job_status = "blocked" if job.depends_on else "pending"
    job_db = {
        "job_id": job.job_id,
        "type": job.type,
        "status": job_status,
        "payload": job.payload,
        "resource_requirement": job.resource_requirements.model_dump(),
        "retry_config": job.retry_config.model_dump(),

    }
    new_job = Job.validate(job_db)
    session.add(new_job)
    session.commit()
    session.refresh(new_job)

    if job.depends_on:
        for dependency in job.depends_on:
            dep_link = JobDep(
                job_id=new_job.id,
                depends_on_job_id=dependency
            )
            session.add(dep_link)
        session.commit()
    session.refresh(new_job)
    return new_job


def get_jobs(session: Session):
    jobs = session.query(Job).all()
    return jobs


def get_job_by_filters(session: Session, status, job_type, priority) -> List[Job]:
    query = session.query(Job)
    if status:
        query = query.filter(Job.status == status)
    if job_type:
        query = query.filter(Job.type == job_type)
    if priority:
        query = query.filter(Job.priority == priority)
    jobs = query.all()
    return jobs


def get_job_by_id(session: Session, job_id: uuid.UUID) -> Job:
    job = session.query(Job).filter(Job.id == job_id).first()
    return job


def patch_job(job: JobSubmission, session: Session):
    job_status = "cancelled"
    job_for_db = {
        "job_id": job.job_id,
        "type": job.type,
        "status": job_status,
        "payload": job.payload,
        "resource_requirement": job.resource_requirements.model_dump(),
        "retry_config": job.retry_config.model_dump(),
    }
    cancellable_states = ["pending", "queued", "blocked"]
    if job.status not in cancellable_states:
        raise HTTPException(
            status_code=400,
            detail=f"Job in status '{job.status}' cannot be cancelled."
        )

    job.status = "cancelled"
    job.updated_at = datetime.utcnow()
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def get_logs_job(session: Session, job_id: uuid.UUID) -> List[JobLog]:
    pass
