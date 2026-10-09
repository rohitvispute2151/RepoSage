"""REST routes managing task execution, SSE event streaming, and HITL approvals."""

import asyncio
from collections.abc import AsyncGenerator
import json
from typing import Any, Optional
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reposage.api.deps import verify_api_key
from reposage.api.schemas import (
    ApprovalDecision,
    TaskCreate,
    TaskResponse,
)
from reposage.db.models import Approval, Patch, RepoSnapshot, Task, TaskEvent
from reposage.db.session import (
    ALLOWED_TRANSITIONS,
    get_db,
    transition_task_status,
)
from reposage.llm.prompts import compute_config_fingerprint
from reposage.workers.tasks import run_task

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_api_key)],
)
async def create_task(
    body: TaskCreate,
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """Create a new QA or Fix task and enqueue background execution."""
    # 1. Verify snapshot exists and is ready
    snap = await db.scalar(
        select(RepoSnapshot).where(RepoSnapshot.id == body.snapshot_id)
    )
    if not snap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot {body.snapshot_id} not found",
        )

    # 2. Extract task request payload
    req_dict: dict[str, Any] = {}
    if body.mode == "qa":
        if not body.qa:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="qa field is required when mode is 'qa'",
            )
        req_dict = body.qa.model_dump()
    elif body.mode == "fix":
        if not body.fix:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="fix field is required when mode is 'fix'",
            )
        req_dict = body.fix.model_dump()

    # 3. Create Task record
    task_id = uuid.uuid4()
    fingerprint = compute_config_fingerprint()

    new_task = Task(
        id=task_id,
        snapshot_id=body.snapshot_id,
        mode=body.mode,
        request=req_dict,
        status="queued",
        budgets=body.budgets.model_dump(),
        config_fingerprint=fingerprint,
    )
    db.add(new_task)
    await db.commit()

    # 4. Enqueue worker task
    try:
        run_task.apply_async(args=[str(task_id)], retry=False)
    except Exception:
        # If Celery worker daemon is offline in dev, task remains queued
        pass

    return TaskResponse.model_validate(new_task, from_attributes=True)


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """Retrieve task execution status, results, and resource budget report."""
    task = await db.scalar(select(Task).where(Task.id == task_id))
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )
    return TaskResponse.model_validate(task, from_attributes=True)


@router.get(
    "/{task_id}/events",
    dependencies=[Depends(verify_api_key)],
)
async def get_task_events(
    task_id: uuid.UUID,
    last_event_id: Optional[int] = Header(None, alias="Last-Event-ID"),
    db: AsyncSession = Depends(get_db),
):
    """Server-Sent Events (SSE) stream delivering real-time agent lifecycle and tool events."""
    task = await db.scalar(select(Task).where(Task.id == task_id))
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )

    async def event_generator() -> AsyncGenerator[str, None]:
        last_seq = last_event_id or 0
        terminal_statuses = {
            "completed",
            "failed",
            "budget_exceeded",
            "cancelled",
            "approval_timeout",
        }

        while True:
            # Poll for events strictly greater than last_seq
            stmt = (
                select(TaskEvent)
                .where(TaskEvent.task_id == task_id, TaskEvent.seq > last_seq)
                .order_by(TaskEvent.seq.asc())
            )
            events = (await db.execute(stmt)).scalars().all()

            for ev in events:
                last_seq = ev.seq
                data_json = json.dumps(ev.payload)
                yield f"id: {ev.seq}\nevent: {ev.type}\ndata: {data_json}\n\n"

            # Check if task reached terminal status
            cur_task = await db.scalar(select(Task).where(Task.id == task_id))
            if cur_task and cur_task.status in terminal_statuses:
                yield f"event: done\ndata: {json.dumps({'status': cur_task.status})}\n\n"
                break

            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{task_id}/approval",
    dependencies=[Depends(verify_api_key)],
)
async def submit_approval(
    task_id: uuid.UUID,
    body: ApprovalDecision,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Submit human review decision (approve, reject, or edit) for a pending patch."""
    # 1. Fetch task row and check status
    stmt = select(Task).where(Task.id == task_id).with_for_update()
    task = await db.scalar(stmt)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    if task.status != "awaiting_approval":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task is in status '{task.status}', not 'awaiting_approval'",
        )

    # 2. Fetch latest patch and verify SHA-256 match
    stmt_patch = (
        select(Patch)
        .where(Patch.task_id == task_id)
        .order_by(Patch.attempt.desc())
    )
    latest_patch = await db.scalar(stmt_patch)
    if not latest_patch or latest_patch.diff_sha256 != body.patch_sha256:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Patch changed or hash mismatch; refetch before deciding",
        )

    if body.decision == "edit" and not body.edited_diff:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="edited_diff is required when decision is 'edit'",
        )

    # 3. Create Approval record
    approval_rec = Approval(
        task_id=task_id,
        patch_id=latest_patch.id,
        decision=body.decision,
        approver="api_user",
        approved_diff_sha256=(
            body.patch_sha256 if body.decision == "approve" else None
        ),
        comment=body.comment,
    )
    db.add(approval_rec)
    await db.commit()

    # 4. Trigger Celery task resumption
    try:
        run_task.apply_async(args=[str(task_id)], kwargs={"approval_id": str(approval_rec.id)}, retry=False)
    except Exception:
        pass

    return {"status": "accepted"}


@router.post(
    "/{task_id}/cancel",
    dependencies=[Depends(verify_api_key)],
)
async def cancel_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Cancel an active or queued task."""
    try:
        await transition_task_status(
            db=db,
            task_id=task_id,
            new_status="cancelled",
            expect_from={"queued", "running", "awaiting_approval"},
            outcome="cancelled_by_user",
        )
        return {"status": "cancelled"}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
