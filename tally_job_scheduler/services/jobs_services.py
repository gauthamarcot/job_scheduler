from sqlmodel import Session

from tally_job_scheduler.models.jobs import Job, JobDep
from tally_job_scheduler.schema.job import JobSubmission


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


def get_job_by_id(session: Session, job_id):
    job = session.query(Job).filter(Job.job_id == job_id).first()
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
    new_job = Job.validate(job_for_db)
    session.add(new_job)
    session.commit()
    session.refresh(new_job)

    return new_job
