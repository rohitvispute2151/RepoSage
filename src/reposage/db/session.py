"""Database session management, connection pooling, and atomic state transitions.

Enforces task state machine invariants and provides async session dependencies for FastAPI.
"""

from collections.abc import AsyncGenerator
from typing import Set
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from reposage.config import settings
from reposage.db.models import Base, Task, utc_now

# Explicit task state machine transitions allowed by system policy
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "cancelled"},
    "running": {
        "awaiting_approval",
        "completed",
        "failed",
        "budget_exceeded",
        "cancelled",
    },
    "awaiting_approval": {"running", "approval_timeout", "cancelled"},
}


class IllegalTransitionError(Exception):
    """Raised when an illegal or raced task status transition is attempted."""

    def __init__(self, task_id: uuid.UUID, from_status: str, to_status: str):
        super().__init__(
            f"Cannot transition task {task_id} from '{from_status}' to '{to_status}'"
        )
        self.task_id = task_id
        self.from_status = from_status
        self.to_status = to_status


from sqlalchemy.pool import NullPool

# Global async SQLAlchemy engine
engine = create_async_engine(
    settings.database_url,
    echo=False,
    poolclass=NullPool,
)

# Asynchronous session factory
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session per request."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Create database tables and required extensions."""
    async with engine.begin() as conn:
        # Create extension if supported (PostgreSQL)
        if "postgresql" in settings.database_url:
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector;")
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
        await conn.run_sync(Base.metadata.create_all)


async def transition_task_status(
    db: AsyncSession,
    task_id: uuid.UUID,
    new_status: str,
    *,
    expect_from: Set[str],
    outcome: str | None = None,
) -> Task:
    """Atomically transition task status verifying valid source status.

    Uses a single conditional update statement to guarantee race-safe transitions.
    """
    # Verify the proposed destination status is legally reachable from at least one source
    for src in expect_from:
        if new_status not in ALLOWED_TRANSITIONS.get(src, set()):
            raise IllegalTransitionError(task_id, src, new_status)

    stmt = (
        update(Task)
        .where(Task.id == task_id, Task.status.in_(expect_from))
        .values(
            status=new_status,
            outcome=outcome if outcome is not None else Task.outcome,
            updated_at=utc_now(),
        )
        .returning(Task)
    )
    res = await db.execute(stmt)
    updated_task = res.scalar_one_or_none()

    if updated_task is None:
        # Fetch current status to report helpful error
        cur = await db.scalar(select(Task.status).where(Task.id == task_id))
        raise IllegalTransitionError(task_id, cur or "unknown", new_status)

    await db.commit()
    return updated_task
