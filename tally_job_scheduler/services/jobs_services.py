from sqlmodel import Session

from tally_job_scheduler.schema.job import JobSubmission


def create_new_job(job: JobSubmission, session: Session):
    pass