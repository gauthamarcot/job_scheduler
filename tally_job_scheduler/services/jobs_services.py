from sqlmodel import Session

from tally_job_scheduler.models.jobs import Job, JobDep
from tally_job_scheduler.schema.job import JobSubmission


def create_new_job(job: JobSubmission, session: Session):

    new_job = Job.from_orm(job)
    new_job.status = "blocked" if job.depends_on else "pending"

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
