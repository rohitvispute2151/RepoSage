"""API request and response schemas for RepoSage REST endpoints."""

from datetime import datetime
from typing import Any, Literal, Optional
import uuid

from pydantic import BaseModel, Field


class RepoCreate(BaseModel):
    """Payload to register and index a repository at a pinned commit."""

    name: str = Field(min_length=1, max_length=255)
    source_uri: str = Field(min_length=1)
    commit_sha: str = Field(min_length=7, max_length=40)


class RepoSnapshotResponse(BaseModel):
    """Status and metadata for a repository snapshot."""

    id: uuid.UUID
    repo_id: uuid.UUID
    commit_sha: str
    status: str
    mirror_path: str
    repo_map: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime


class Budgets(BaseModel):
    """Resource limits allocated to an individual task."""

    max_steps: int = Field(default=30, ge=1, le=60)
    max_tokens: int = Field(default=250_000, ge=1_000, le=1_000_000)
    max_usd: float = Field(default=1.0, gt=0, le=5.0)
    max_seconds: int = Field(default=900, ge=30, le=3600)


class QARequest(BaseModel):
    """Parameters for code-explanation and navigation questions."""

    question: str = Field(min_length=3, max_length=2_000)


class FixRequest(BaseModel):
    """Parameters for automated bug fix and regression repair."""

    description: str = Field(default="", max_length=4_000)
    failing_tests: list[str] = Field(min_length=1, max_length=20)


class TaskCreate(BaseModel):
    """Task creation payload initiating QA or Fix workflows."""

    snapshot_id: uuid.UUID
    mode: Literal["qa", "fix"]
    qa: Optional[QARequest] = None
    fix: Optional[FixRequest] = None
    budgets: Budgets = Budgets()
    idempotency_key: Optional[str] = None


class Citation(BaseModel):
    """Verifiable code location citation pointer."""

    path: str
    start_line: int
    end_line: int
    symbol: str


class TaskResult(BaseModel):
    """Structured outcome report for a completed or terminated task."""

    outcome: str
    answer: Optional[str] = None
    citations: list[Citation] = Field(default_factory=list)
    patch_diff: Optional[str] = None
    test_summary: Optional[dict[str, Any]] = None
    budget_report: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class TaskResponse(BaseModel):
    """Task record representation returned by query endpoints."""

    id: uuid.UUID
    snapshot_id: uuid.UUID
    mode: str
    status: str
    outcome: Optional[str] = None
    budgets: dict[str, Any]
    result: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class ApprovalDecision(BaseModel):
    """Human-in-the-loop decision payload."""

    decision: Literal["approve", "reject", "edit"]
    patch_sha256: str
    edited_diff: Optional[str] = None
    comment: Optional[str] = None
