"""Distributed lease manager for worker task ownership and crash recovery.

Prevents split-brain worker collisions and enables automated lease expiration
and re-queueing if a worker host terminates unexpectedly.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from reposage.db.models import Task, utc_now
from reposage.observability.logging import logger


class TaskLeaseManager:
    """Manages heartbeat leases on task records in the database."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def acquire(
        self,
        task_id: uuid.UUID,
        owner: str,
        ttl_seconds: int = 60,
    ) -> bool:
        """Attempt to acquire or renew task execution lease."""
        now = utc_now()
        new_expiry = now + timedelta(seconds=ttl_seconds)

        # Condition: unleased, lease expired, or already owned by caller
        stmt = (
            update(Task)
            .where(
                Task.id == task_id,
                (Task.lease_owner.is_(None))
                | (Task.lease_expires_at < now)
                | (Task.lease_owner == owner),
            )
            .values(
                lease_owner=owner,
                lease_expires_at=new_expiry,
                updated_at=now,
            )
            .returning(Task.id)
        )

        res = await self.db.execute(stmt)
        acquired_id = res.scalar_one_or_none()
        await self.db.commit()

        return acquired_id is not None

    async def release(self, task_id: uuid.UUID, owner: str) -> None:
        """Release lease ownership upon task completion or pause."""
        stmt = (
            update(Task)
            .where(Task.id == task_id, Task.lease_owner == owner)
            .values(
                lease_owner=None,
                lease_expires_at=None,
                updated_at=utc_now(),
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def renew_loop(
        self,
        task_id: uuid.UUID,
        owner: str,
        interval_seconds: int = 20,
        ttl_seconds: int = 60,
    ) -> None:
        """Background periodic heartbeat loop renewing lease."""
        from reposage.db.session import async_session_factory

        while True:
            await asyncio.sleep(interval_seconds)
            try:
                async with async_session_factory() as session:
                    mgr = TaskLeaseManager(session)
                    ok = await mgr.acquire(task_id, owner, ttl_seconds=ttl_seconds)
                    if not ok:
                        logger.warning(
                            f"Failed to renew lease for task {task_id}. Another worker may have claimed it."
                        )
                        break
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    f"Error in lease renewal heartbeat for task {task_id}: {exc}"
                )
