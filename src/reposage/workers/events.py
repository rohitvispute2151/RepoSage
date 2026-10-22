"""Durable, ordered task event log feeding the SSE endpoint.

Graph nodes emit events synchronously; this recorder queues them and a single writer coroutine persists them in order
through its own DB session, so event writes never interleave with the graph's transactions. Sequence numbers continue
from the last stored event, so a task resumed after approval (or a crash) keeps one monotonic stream.
"""

import asyncio
import json
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import func, select

from reposage.db.models import TaskEvent
from reposage.db.session import async_session_factory
from reposage.observability.logging import logger

Writer = Callable[[str, int, str, dict[str, Any]], Awaitable[None]]
_STOP = object()


async def _db_write(task_id: str, seq: int, etype: str, payload: dict[str, Any]) -> None:
    async with async_session_factory() as session:
        session.add(TaskEvent(task_id=task_id, seq=seq, type=etype, payload=payload))
        await session.commit()


async def _db_last_seq(task_id: str) -> int:
    async with async_session_factory() as session:
        return int(await session.scalar(select(func.coalesce(func.max(TaskEvent.seq), 0)).where(TaskEvent.task_id == task_id)) or 0)


def _jsonable(payload: dict[str, Any]) -> dict[str, Any]:
    """Payloads may carry UUIDs, datetimes or Paths; the JSON column and the SSE wire need plain data."""
    return json.loads(json.dumps(payload, default=str))


class EventRecorder:
    def __init__(self, task_id: str, *, write: Writer = _db_write, last_seq: Optional[Callable[[str], Awaitable[int]]] = None) -> None:
        self.task_id = task_id
        self._write = write
        self._last_seq = last_seq or _db_last_seq
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._seq = 0
        self._worker: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        self._seq = await self._last_seq(self.task_id)
        self._worker = asyncio.create_task(self._drain())

    def sink(self, task_id: str, etype: str, payload: dict[str, Any]) -> None:
        """Synchronous entry point handed to AgentDependencies.event_sink."""
        self._queue.put_nowait((etype, payload))

    async def _drain(self) -> None:
        while True:
            item = await self._queue.get()
            if item is _STOP:
                return
            etype, payload = item
            self._seq += 1
            try:
                await self._write(self.task_id, self._seq, etype, _jsonable(payload))
            except Exception as exc:  # an event we could not store must not kill the task
                logger.warning(f"Dropping event {etype} (seq {self._seq}) for task {self.task_id}: {exc}")

    async def close(self) -> None:
        """Flush everything queued so far, then stop. Call before the task is marked finished or its lease released."""
        if self._worker is None:
            return
        self._queue.put_nowait(_STOP)
        await self._worker
        self._worker = None
