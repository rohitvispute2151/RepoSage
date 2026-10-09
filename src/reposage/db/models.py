"""SQLAlchemy ORM models for RepoSage.

Defines schemas for repositories, code chunks, execution tasks, audit logs,
HITL approvals, and evaluation results.
"""

from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Return current timestamp in UTC timezone."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base declarative class for RepoSage database tables."""
    pass


class Repo(Base):
    """Registered code repository metadata."""

    __tablename__ = "repos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    snapshots: Mapped[list["RepoSnapshot"]] = relationship("RepoSnapshot", back_populates="repo", cascade="all, delete-orphan")


class RepoSnapshot(Base):
    """Immutable snapshot of a repository checked out at a specific commit SHA."""

    __tablename__ = "repo_snapshots"
    __table_args__ = (
        UniqueConstraint("repo_id", "commit_sha", name="uq_repo_snapshot_commit"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    # Status progression: 'queued' -> 'ingesting' -> 'ready' or 'failed'
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    mirror_path: Mapped[str] = mapped_column(Text, nullable=False)
    repo_map: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True) # Outline of modules & symbols
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    repo: Mapped["Repo"] = relationship("Repo", back_populates="snapshots")
    files: Mapped[list["File"]] = relationship("File", back_populates="snapshot", cascade="all, delete-orphan")
    chunks: Mapped[list["Chunk"]] = relationship("Chunk", back_populates="snapshot", cascade="all, delete-orphan")
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="snapshot")


class File(Base):
    """Tracked source file inside a repository snapshot."""

    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "path", name="uq_snapshot_file_path"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repo_snapshots.id", ondelete="CASCADE"), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False)

    snapshot: Mapped["RepoSnapshot"] = relationship("RepoSnapshot", back_populates="files")
    chunks: Mapped[list["Chunk"]] = relationship("Chunk", back_populates="file", cascade="all, delete-orphan")


class Chunk(Base):
    """Syntactic code chunk (function, method, class) extracted for hybrid retrieval."""

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "path", "qualname", "content_hash", name="uq_chunk_identity"),
        Index("idx_chunks_snapshot", "snapshot_id"),
        Index("idx_chunks_path", "path"),
        Index("idx_chunks_qualname", "qualname"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repo_snapshots.id", ondelete="CASCADE"), nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    qualname: Mapped[str] = mapped_column(Text, nullable=False) # e.g. pkg.module.Class.method
    kind: Mapped[str] = mapped_column(String(32), nullable=False) # 'function', 'method', 'class', 'module_header'
    signature: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    docstring: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False) # Header + body embedded text
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False) # Content + identifier expansions for FTS
    # Embeddings stored as JSON array in SQLite/generic DB, or native vector in PostgreSQL pgvector
    embedding: Mapped[Optional[list[float]]] = mapped_column(JSON, nullable=True)

    snapshot: Mapped["RepoSnapshot"] = relationship("RepoSnapshot", back_populates="chunks")
    file: Mapped["File"] = relationship("File", back_populates="chunks")


class EmbeddingCache(Base):
    """Content-hash deduplication cache for vector embeddings across tasks and runs."""

    __tablename__ = "embedding_cache"

    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    model: Mapped[str] = mapped_column(String(64), primary_key=True)
    embedding: Mapped[list[float]] = mapped_column(JSON, nullable=False)


class Task(Base):
    """Orchestration task running QA or fix workflows against a pinned snapshot."""

    __tablename__ = "tasks"
    __table_args__ = (
        Index("idx_tasks_status_lease", "status", "lease_expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repo_snapshots.id"), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False) # 'qa' or 'fix'
    request: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    # State transitions governed by ALLOWED_TRANSITIONS
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    outcome: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    budgets: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    config_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    lease_owner: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    snapshot: Mapped["RepoSnapshot"] = relationship("RepoSnapshot", back_populates="tasks")
    events: Mapped[list["TaskEvent"]] = relationship("TaskEvent", back_populates="task", cascade="all, delete-orphan")
    tool_calls: Mapped[list["ToolCall"]] = relationship("ToolCall", back_populates="task", cascade="all, delete-orphan")
    llm_calls: Mapped[list["LLMCall"]] = relationship("LLMCall", back_populates="task", cascade="all, delete-orphan")
    patches: Mapped[list["Patch"]] = relationship("Patch", back_populates="task", cascade="all, delete-orphan")
    approvals: Mapped[list["Approval"]] = relationship("Approval", back_populates="task", cascade="all, delete-orphan")


class TaskEvent(Base):
    """Chronological event log emitted during graph node steps for SSE streaming."""

    __tablename__ = "task_events"
    __table_args__ = (
        UniqueConstraint("task_id", "seq", name="uq_task_event_seq"),
        Index("idx_task_events_task_seq", "task_id", "seq"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False) # e.g. 'node_started', 'tool_call', 'approval_requested'
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    task: Mapped["Task"] = relationship("Task", back_populates="events")


class ToolCall(Base):
    """Audit log and idempotency replay ledger for tool executions."""

    __tablename__ = "tool_calls"
    __table_args__ = (
        Index("idx_tool_calls_task_step", "task_id", "step_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    step_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    args: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    args_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False) # 'allowed', 'denied', 'ok', 'error', 'timeout'
    denial_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_summary: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    task: Mapped["Task"] = relationship("Task", back_populates="tool_calls")


class LLMCall(Base):
    """Usage and cost accounting record for each model request."""

    __tablename__ = "llm_calls"
    __table_args__ = (
        Index("idx_llm_calls_task", "task_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    node: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    prompt_hash: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False) # 'ok', 'schema_error', 'provider_error', 'timeout'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    task: Mapped["Task"] = relationship("Task", back_populates="llm_calls")


class Patch(Base):
    """Candidate bug fix diff generated during fix workflows."""

    __tablename__ = "patches"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    diff: Mapped[str] = mapped_column(Text, nullable=False)
    diff_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    validation: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False) # Deterministic policy checks
    test_results: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True) # Sandbox test run results
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    task: Mapped["Task"] = relationship("Task", back_populates="patches")
    approvals: Mapped[list["Approval"]] = relationship("Approval", back_populates="patch", cascade="all, delete-orphan")


class Approval(Base):
    """Human-in-the-loop decision record governing patch application."""

    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    patch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patches.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False) # 'approve', 'reject', 'edit'
    approver: Mapped[str] = mapped_column(String(128), nullable=False)
    approved_diff_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    task: Mapped["Task"] = relationship("Task", back_populates="approvals")
    patch: Mapped["Patch"] = relationship("Patch", back_populates="approvals")


# Evaluation framework tables

class EvalSuite(Base):
    """Versioned evaluation test suite."""

    __tablename__ = "eval_suites"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_eval_suite_name_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False) # 'retrieval', 'qa', 'fix', 'adversarial'
    version: Mapped[str] = mapped_column(String(32), nullable=False)

    cases: Mapped[list["EvalCase"]] = relationship("EvalCase", back_populates="suite", cascade="all, delete-orphan")
    runs: Mapped[list["EvalRun"]] = relationship("EvalRun", back_populates="suite", cascade="all, delete-orphan")


class EvalCase(Base):
    """Individual test case with input and ground truth."""

    __tablename__ = "eval_cases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    suite_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eval_suites.id", ondelete="CASCADE"), nullable=False)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repo_snapshots.id"), nullable=False)
    input: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    ground_truth: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    suite: Mapped["EvalSuite"] = relationship("EvalSuite", back_populates="cases")


class EvalRun(Base):
    """Batch execution run of an evaluation suite."""

    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    suite_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eval_suites.id", ondelete="CASCADE"), nullable=False)
    config_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    suite: Mapped["EvalSuite"] = relationship("EvalSuite", back_populates="runs")
    results: Mapped[list["EvalResult"]] = relationship("EvalResult", back_populates="run", cascade="all, delete-orphan")


class EvalResult(Base):
    """Outcome and metric scores for an evaluation case."""

    __tablename__ = "eval_results"
    __table_args__ = (
        UniqueConstraint("run_id", "case_id", "repeat_idx", name="uq_eval_result_case_repeat"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eval_cases.id"), nullable=False)
    repeat_idx: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    run: Mapped["EvalRun"] = relationship("EvalRun", back_populates="results")
