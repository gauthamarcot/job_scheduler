import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class ResourceRequirements(BaseModel):
    cpu_units: int
    memory_mb: int


class RetryConfig(BaseModel):
    max_attempts: int
    backoff_multiplier: int


class JobDetails(BaseModel):
    job_id: uuid.UUID
    type: str
    status: str
    priority: str
    payload: Dict[str, Any]
    resource_requirements: ResourceRequirements
    depends_on: List[str]
    retry_config: RetryConfig
    timeout_seconds: Optional[int]
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class JobSubmission(BaseModel):
    type: Optional[str]
    job_id: uuid.UUID
    payload: Dict[str, Any]
    resource_requirements: ResourceRequirements
    depends_on: Optional[List[uuid.UUID]] = Field(default_factory=list)
    retry_config: Optional[RetryConfig] = Field(default_factory=RetryConfig)


class JobSubmissionResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    created_at: datetime
    priority: str
    position_in_queue: Optional[int] = None


class JobList(BaseModel):
    jobs: List[JobDetails]
