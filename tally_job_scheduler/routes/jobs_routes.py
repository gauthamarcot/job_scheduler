from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from starlette import status

from ..schema import job
from ..schema.job import JobSubmission
from ..utils import get_session

router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
    responses={404: {"description": "Not found"}},
)


@router.get("/", response_model=List[job.JobList])
async def get_all_jobs():
    pass


@router.get("/{job_id}", response_model=job.JobDetails)
async def get_job(job_id: str):
    pass


@router.get("/{job_id}/logs")
async def get_job_logs(job_id: str):
    pass


@router.post("/", response_model=job.JobSubmissionResponse, status_code=201)
async def submit_jobs(job_sub: JobSubmission, session: Session = Depends(get_session)):
    try:
        created_job = create_new_job(job_sub, session)
        return created_job
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.patch("/{job_id}/cancel")
async def cancel_job(job_id: str):
    pass
