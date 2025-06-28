"""
the table i am thinking
jobs table:
job_id, job_type, status, priority, job_payload, retry_config, job_timeout, resource_requirements, created_at, updated_at, started_at, finished_at


jobs_logs
to store the logs
schema inspired from aws cloudwatch metrics
id, job_id, timestamps log_level, message

job_dep

"""

import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel


class Job(SQLModel, table=True):
    job_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True
    )
    type: str = Field(sa_column=Column(String, index=True))
    status: str = Field(sa_column=Column(String, index=True), default="pending")
    priority: str = Field(sa_column=Column(String, index=True), default="normal")

    payload: Dict[str, Any] = Field(sa_column=Column(JSONB), default_factory=dict)
    resource_requirements: Dict[str, Any] = Field(sa_column=Column(JSONB), default_factory=dict)
    retry_config: Dict[str, Any] = Field(sa_column=Column(JSONB), default_factory=dict)
    timeout_seconds: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False,
                                 sa_column_kwargs={"onupdate": datetime.utcnow})
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    logs: List["JobLog"] = Relationship(back_populates="job")
    dependencies: List["JobDep"] = Relationship(
        back_populates="job",
        sa_relationship_kwargs={"primaryjoin": "Job.job_id==JobDep.job_id"}
    )
    dependents: List["JobDep"] = Relationship(
        back_populates="dependent_job",
        sa_relationship_kwargs={"primaryjoin": "Job.job_id==JobDep.depends_on_job_id"}
    )


class JobDep(SQLModel, table=True):
    job_id: uuid.UUID = Field(
        foreign_key="job.job_id",
        primary_key=True
    )
    depends_on_job_id: uuid.UUID = Field(
        foreign_key="job.job_id",
        primary_key=True
    )
    job: Job = Relationship(
        back_populates="dependencies",
        sa_relationship_kwargs={"primaryjoin": "JobDep.job_id==Job.job_id"}
    )
    dependent_job: Job = Relationship(
        back_populates="dependents",
        sa_relationship_kwargs={"primaryjoin": "JobDep.depends_on_job_id==Job.job_id"}
    )


class JobLog(SQLModel, table=True):
    log_id: Optional[int] = Field(default=None, primary_key=True)
    job_id: uuid.UUID = Field(foreign_key="job.job_id", index=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    log_level: str = Field(default="INFO")
    message: str
    job: Job = Relationship(back_populates="logs")
