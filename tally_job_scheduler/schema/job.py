import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class ResourceRequirements(BaseModel):
    cpu_units: int = 1
    memory_mb: int = 512
    gpu_units: Optional[int] = None
    disk_gb: Optional[int] = None
    additional_resources: Optional[Dict[str, Any]] = Field(default_factory=dict)


class RetryConfig(BaseModel):
    max_attempts: int = 2
    backoff_multiplier: int = 1


class JobDetails(BaseModel):
    job_id: uuid.UUID
    type: Optional[str] = None
    status: str
    priority: str
    payload: Dict[str, Any]
    resource_requirements: Dict[str, Any]
    retry_config: Dict[str, Any]
    timeout_seconds: Optional[int]
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class JobSubmission(BaseModel):
    type: str
    job_id: uuid.UUID
    payload: Dict[str, Any]
    resource_requirements: ResourceRequirements
    priority: str = "normal"
    depends_on: Optional[List[uuid.UUID]] = Field(default_factory=list)
    retry_config: Optional[RetryConfig] = Field(default_factory=RetryConfig)
    timeout_seconds: Optional[int] = None


class JobSubmissionResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    created_at: datetime
    priority: str
    position_in_queue: Optional[int] = None

    class Config:
        from_attributes = True


class JobList(BaseModel):
    jobs: List[JobDetails]
