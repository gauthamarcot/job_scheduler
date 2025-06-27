from typing import List

from fastapi import APIRouter, Depends, HTTPException
from schemas import job
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


@router.post("/")
async def submit_jobs():
    pass


@router.patch("/{job_id}/cancel")
async def cancel_job(job_id: str):
    pass