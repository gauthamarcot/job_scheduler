from typing import List
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from starlette import status

from ..schema import job
from ..schema.job import JobSubmission, JobDetails
from ..services.jobs_services import create_new_job, get_jobs, get_job_by_id, patch_job, get_logs_job
from ..utils import get_session

router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
    responses={404: {"description": "Not found"}},
)


@router.get("/", response_model=List[JobDetails])
async def get_all_jobs(session: Session = Depends(get_session)):
    jobs_data = get_jobs(session)
    if not jobs_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="jobs not found")
    return jobs_data


@router.get("/{job_id}", response_model=JobDetails)
async def get_job(job_id: str, session: Session = Depends(get_session)):
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    
    job_data = get_job_by_id(session, job_uuid)
    if job_data is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_data


@router.get("/{job_id}/logs")
async def get_job_logs(job_id: str, session: Session = Depends(get_session)):
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    
    logs = get_logs_job(session, job_uuid)
    return {"logs": logs}


@router.post("/", response_model=job.JobSubmissionResponse, status_code=201)
async def submit_jobs(job_sub: JobSubmission, session: Session = Depends(get_session)):
    created_job = create_new_job(job_sub, session)
    return created_job


@router.patch("/{job_id}/cancel")
async def cancel_job(job_id: str, session: Session = Depends(get_session)):
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    
    cancelled_job = patch_job(job_uuid, session)
    return {"message": "Job cancelled successfully", "job_id": str(cancelled_job.job_id)}
