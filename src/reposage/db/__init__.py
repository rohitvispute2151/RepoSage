"""Database persistence package for RepoSage.

Provides SQLAlchemy models, asynchronous session providers, and atomic task transitions.
"""

from reposage.db.models import (
    Approval,
    Base,
    Chunk,
    EmbeddingCache,
    EvalCase,
    EvalResult,
    EvalRun,
    EvalSuite,
    File,
    LLMCall,
    Patch,
    Repo,
    RepoSnapshot,
    Task,
    TaskEvent,
    ToolCall,
)
from reposage.db.session import (
    ALLOWED_TRANSITIONS,
    IllegalTransitionError,
    async_session_factory,
    get_db,
    init_db,
    transition_task_status,
)

__all__ = [
    "Base",
    "Repo",
    "RepoSnapshot",
    "File",
    "Chunk",
    "EmbeddingCache",
    "Task",
    "TaskEvent",
    "ToolCall",
    "LLMCall",
    "Patch",
    "Approval",
    "EvalSuite",
    "EvalCase",
    "EvalRun",
    "EvalResult",
    "get_db",
    "async_session_factory",
    "init_db",
    "ALLOWED_TRANSITIONS",
    "IllegalTransitionError",
    "transition_task_status",
]
